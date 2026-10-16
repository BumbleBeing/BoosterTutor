"""In-memory stand-ins for everything `ReviewService` touches.

No network and no database. The 17Lands fetch is replaced by the saved
payloads, the Replay Cache by a dict, the statistics by the HOB snapshot in
`fixtures/format_inputs`, the stored prose by a dict, and Claude by a
`FakeCoach`. A `World` counts how often 17Lands, the statistics and Claude
were asked, so tests can check what is fetched, what is cached, what is
recomputed and what is paid for.
"""

import dataclasses
import datetime as dt
import json
import uuid
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

from conftest import load_card_facts, load_deck_inputs
from fastapi.testclient import TestClient

from boostertutor.analysis.deck_rating import DeckRatingModel
from boostertutor.analysis.draft import FormatInputs
from boostertutor.briefing import CardFacts, PickBrief
from boostertutor.briefing.primer import format_primer
from boostertutor.briefing.summary import SummaryBrief
from boostertutor.format_inputs import FormatNotReady
from boostertutor.llm.draft_summary import DraftSummary, KeyPick
from boostertutor.llm.pick_note import PickNote
from boostertutor.main import app
from boostertutor.review.postgres import get_review_service
from boostertutor.review.rate_limit import Bucket, Limits, RateLimiter
from boostertutor.review.service import ReviewService
from boostertutor.schemas import DraftLog
from boostertutor.schemas.coach import SavedNote, SavedReview, SavedSummary
from boostertutor.schemas.deck_submission import SubmittedDeck
from boostertutor.schemas.draft_review import CardInfo

FIXTURES = Path(__file__).parent / "fixtures" / "seventeen_lands_draft"
DRAFT_ID = "d9ac6765edeb499fb4084e4d018f8cee"
URL = f"https://www.17lands.com/draft/{DRAFT_ID}"


class MemoryStore:
    """The Replay Cache: parsed logs by draft id."""

    def __init__(self) -> None:
        self.logs: dict[str, DraftLog] = {}

    def get(self, draft_id: str) -> DraftLog | None:
        return self.logs.get(draft_id)

    def has(self, draft_id: str) -> bool:
        return draft_id in self.logs

    def add(self, log: DraftLog) -> None:
        assert log.source_id is not None
        self.logs[log.source_id] = log


class MemoryLedger:
    def __init__(self) -> None:
        self.rows: list[tuple[Bucket, str, dt.datetime]] = []

    def count_since(self, bucket: Bucket, client: str, since: dt.datetime) -> int:
        return sum(
            1 for b, c, at in self.rows if (b, c) == (bucket, client) and at > since
        )

    def record(self, bucket: Bucket, client: str, at: dt.datetime) -> None:
        self.rows.append((bucket, client, at))

    def prune(self, before: dt.datetime) -> None:
        self.rows = [row for row in self.rows if row[2] >= before]

    def count(self, bucket: Bucket) -> int:
        return sum(1 for b, _, _ in self.rows if b == bucket)


class MemorySavedReviews:
    """Claude's stored prose, by (draft id, owner)."""

    def __init__(self) -> None:
        self.reviews: dict[tuple[str, uuid.UUID | None], SavedReview] = {}

    def get(self, draft_id: str, user_id: uuid.UUID | None) -> SavedReview | None:
        return self.reviews.get((draft_id, user_id))

    def _review(self, draft_id: str, user_id: uuid.UUID | None) -> SavedReview:
        return self.reviews.setdefault(
            (draft_id, user_id),
            SavedReview(notes=[], summary=None, reviewed_deck=None, current_deck=None),
        )

    def add_note(
        self, draft_id: str, user_id: uuid.UUID | None, note: SavedNote
    ) -> SavedNote:
        review = self._review(draft_id, user_id)
        for stored in review.notes:
            if (stored.pack_number, stored.pick_number) == (
                note.pack_number,
                note.pick_number,
            ):
                return stored
        review.notes.append(note)
        return note

    def save_deck(
        self,
        draft_id: str,
        user_id: uuid.UUID | None,
        deck: SubmittedDeck,
        summary: SavedSummary | None,
    ) -> None:
        review = self._review(draft_id, user_id)
        review.current_deck = deck
        if summary is not None:
            review.reviewed_deck = deck
            review.summary = summary


class FakeCoach:
    """Claude, answering every brief at once with canned prose.

    Set `fail` to an exception (`SpendingCapReached()`, `PickNoteFailed(...)`)
    to make the next calls raise it, as the real coach would.
    """

    def __init__(self) -> None:
        self.note_briefs: list[PickBrief] = []
        self.summary_briefs: list[SummaryBrief] = []
        self.draft_keys: list[str] = []
        self.user_ids: list[uuid.UUID | None] = []
        self.fail: Exception | None = None

    @property
    def calls(self) -> int:
        return len(self.note_briefs) + len(self.summary_briefs)

    def pick_note(
        self, brief: PickBrief, *, draft_key: str, user_id: uuid.UUID | None
    ) -> PickNote:
        self.note_briefs.append(brief)
        self.draft_keys.append(draft_key)
        self.user_ids.append(user_id)
        if self.fail is not None:
            raise self.fail
        return PickNote(
            pack_number=brief.pack_number,
            pick_number=brief.pick_number,
            kind=brief.kind,
            note=f"A note on P{brief.pack_number}p{brief.pick_number}.",
            prompt_version="pick_note.v1",
        )

    def draft_summary(
        self,
        brief: SummaryBrief,
        primer: str,
        *,
        draft_key: str,
        user_id: uuid.UUID | None,
    ) -> DraftSummary:
        self.summary_briefs.append(brief)
        self.draft_keys.append(draft_key)
        self.user_ids.append(user_id)
        if self.fail is not None:
            raise self.fail
        first = brief.picks[0]
        return DraftSummary(
            draft_arc="The arc.",
            deck="The deck.",
            lesson="The lesson.",
            key_picks=[KeyPick(pack_number=first[0], pick_number=first[1])],
            prompt_version="draft_summary.v1",
            model="claude-sonnet-5-5",
        )


def _basic(name: str) -> CardInfo:
    return CardInfo(
        name=name,
        mana_cost=None,
        type_line=f"Basic Land — {name}",
        cmc=0.0,
        colors="",
        rarity="common",
        image_normal=f"https://example.test/{name}.jpg",
        image_art_crop=None,
    )


class World:
    """The Replay Cache, the `Catalog`, 17Lands and the rate limits, in memory.

    Change an attribute to change the world: `fetch_error` makes 17Lands
    fail, `not_ready` empties the statistics, `limits` sets the allowances.
    """

    def __init__(self, inputs: FormatInputs, names: dict[str, uuid.UUID]) -> None:
        # The fixture writes its snapshot as text; the database gives a date.
        self.inputs = dataclasses.replace(
            inputs, stats_snapshot=dt.date.fromisoformat(str(inputs.stats_snapshot))
        )
        self.name_index = names
        self.store = MemoryStore()
        self.saved = MemorySavedReviews()
        self.coach = FakeCoach()
        self.facts: dict[uuid.UUID, CardFacts] = load_card_facts()
        self.ledger = MemoryLedger()
        self.limits: dict[Bucket, Limits] = {
            "fetch": Limits(per_minute=5, per_day=50),
            "deck": Limits(per_minute=5, per_day=50),
        }
        self.supported = frozenset({"hob"})
        self.event_type = "PremierDraft"  # what 17Lands calls the event
        self.fetch_error: Exception | None = None
        self.not_ready = False
        self.fitted_model: DeckRatingModel | None = None
        self.basics = {
            colour: _basic(name)
            for colour, name in zip(
                "WUBRG",
                ["Plains", "Island", "Swamp", "Mountain", "Forest"],
                strict=True,
            )
        }
        # What was asked of the outside world.
        self.fetches = 0
        self.stats_asked: list[str] = []  # event types statistics were loaded for

    # -- the 17Lands fetch -------------------------------------------------

    def fetch(self, draft_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
        self.fetches += 1
        if self.fetch_error is not None:
            raise self.fetch_error
        metadata = json.loads((FIXTURES / "event_metadata.json").read_text())
        # The event's name sits in the nested `metadata` block when there is one.
        metadata.get("metadata", metadata)["format"] = self.event_type
        return json.loads((FIXTURES / "draft.json").read_text()), metadata

    # -- the Catalog -------------------------------------------------------

    def names(self, set_code: str) -> dict[str, uuid.UUID]:
        return self.name_index

    def format_inputs(self, set_code: str, event_type: str) -> FormatInputs:
        self.stats_asked.append(event_type)
        if self.not_ready:
            raise FormatNotReady("no statistics yet")
        return self.inputs

    def deck_model(self, set_code: str, event_type: str) -> DeckRatingModel | None:
        return self.fitted_model

    def card_infos(
        self, set_code: str, ids: Iterable[uuid.UUID]
    ) -> dict[uuid.UUID, CardInfo]:
        cards = self.inputs.cards
        return {
            oid: CardInfo(
                name=f"card {oid.hex[:6]}",
                mana_cost=cards[oid].get("mana_cost"),
                type_line=cards[oid]["type_line"],
                cmc=cards[oid]["cmc"],
                colors=cards[oid]["colors"],
                rarity="common",
                image_normal=None,
                image_art_crop=None,
            )
            for oid in ids
            if oid in cards
        }

    def basic_lands(self, set_code: str) -> dict[str, CardInfo]:
        return self.basics

    def card_facts(
        self, set_code: str, ids: Iterable[uuid.UUID]
    ) -> dict[uuid.UUID, CardFacts]:
        return {oid: self.facts[oid] for oid in ids if oid in self.facts}

    def primer(self, set_code: str, event_type: str) -> str:
        return format_primer(load_deck_inputs()[2])

    # -- wiring ------------------------------------------------------------

    def service(self) -> ReviewService:
        """A fresh service per request, as in production, over this world."""
        return ReviewService(
            store=self.store,
            catalog=self,
            fetch=self.fetch,
            limiter=RateLimiter(self.ledger, self.limits),
            supported_sets=self.supported,
            saved=self.saved,
            coach=lambda: self.coach,
        )

    def client(self) -> Iterator[TestClient]:
        """A test client whose requests all run in this world."""
        app.dependency_overrides[get_review_service] = self.service
        yield TestClient(app)
        app.dependency_overrides.clear()


def new_stats(world: World, days: int = 1) -> None:
    """Move the world's statistics on to a newer Stats Snapshot."""
    world.inputs = dataclasses.replace(
        world.inputs,
        stats_snapshot=world.inputs.stats_snapshot + dt.timedelta(days=days),
    )


def submit(client: TestClient, link: str = URL) -> Any:
    return client.post("/api/drafts", json={"link": link})


def error_kind(response: Any) -> str:
    kind: str = response.json()["detail"]["kind"]
    return kind
