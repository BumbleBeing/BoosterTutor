"""Draft Review without accounts: import a draft, review it, rate a deck.

`ReviewService` is the one thing the `/api/drafts` routes call (ADR 0031).
It owns every rule its three operations share, so no route repeats them:

- a draft id is checked, and a draft not in the Replay Cache is a 404
- Traditional and Open drafts are rated with the Premier statistics
- a format with no statistics yet is a 503
- 17Lands is asked only on a cache miss, and only after the rate limit
- verdicts and Deck Ratings are recomputed on every request: the parsed log
  is the only thing ever stored

Every failure is a `ReviewError` (`errors.py`).

Phase 5d adds Claude's prose for a `Coached` caller (`access.py`; until
Phase 6, a request with the Admin Key): a Pick Note written lazily when a
Noted Pick is opened, and a Draft Summary on the first deck. Both are
stored, since they cost money, with the Stats Snapshot they were written
against. Nothing is ever stored for an anonymous caller.

The service's collaborators are small interfaces: the Replay Cache, the
`Catalog` of what the database knows about a set, the 17Lands fetch, the
rate limiter, the `SavedReviews` that hold the prose, and the `Coach` that
writes it. `postgres.py` builds the real ones; the tests build
in-memory ones, so the whole service runs with no network and no database.
"""

import re
import uuid
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

from ..analysis.deck import deck_metrics
from ..analysis.deck_rating import DeckRatingModel, rate_deck
from ..analysis.draft import FormatInputs, analyze_draft
from ..analysis.mana import colour_sources
from ..briefing import CardFacts, PickBrief, pick_brief
from ..briefing.summary import SummaryBrief, summary_brief
from ..card_facts import analysis_cards
from ..format_inputs import FormatNotReady, stats_event_type
from ..llm import pick_note
from ..llm.draft_summary import DraftSummary, DraftSummaryFailed
from ..llm.pick_note import PickNote, PickNoteFailed
from ..llm.spending import SpendingCapReached
from ..parsing import seventeen_lands
from ..parsing.errors import DraftInputError
from ..schemas import DraftLog
from ..schemas.coach import (
    CoachedDeckReview,
    CoachNote,
    CoachReview,
    CoachSummary,
    ProseUnavailable,
    SavedNote,
    SavedReview,
    SavedSummary,
    SummaryKeyPick,
)
from ..schemas.deck import DeckError, DeckMetrics, deck_from_pool
from ..schemas.deck_submission import SubmittedDeck
from ..schemas.draft_analysis import DraftAnalysis
from ..schemas.draft_review import CardInfo, DraftReview, ImportResponse
from .access import Coached
from .errors import ReviewError
from .rate_limit import Bucket, RateLimited, RateLimiter

# A 17Lands draft id: 32 lowercase hex characters.
DRAFT_ID_RE = re.compile(r"^[0-9a-f]{32}$")


class ReplayStore(Protocol):
    """The Replay Cache: parsed logs by 17Lands draft id."""

    def get(self, draft_id: str) -> DraftLog | None: ...
    def has(self, draft_id: str) -> bool: ...
    def add(self, log: DraftLog) -> None: ...


class Catalog(Protocol):
    """What the database knows about a set: its cards, statistics and models."""

    def names(self, set_code: str) -> dict[str, uuid.UUID]:
        """`name_key` -> oracle id, for matching a draft's card names."""
        ...

    def format_inputs(self, set_code: str, event_type: str) -> FormatInputs:
        """The statistics a verdict is computed from, or `FormatNotReady`."""
        ...

    def deck_model(self, set_code: str, event_type: str) -> DeckRatingModel | None:
        """The fitted Deck Ratings, or None when the format has none yet."""
        ...

    def card_infos(
        self, set_code: str, ids: Iterable[uuid.UUID]
    ) -> dict[uuid.UUID, CardInfo]:
        """How to show each card: name, cost, image."""
        ...

    def basic_lands(self, set_code: str) -> dict[str, CardInfo]:
        """The set's own basic lands by colour letter; a missing one is absent."""
        ...

    def card_facts(
        self, set_code: str, ids: Iterable[uuid.UUID]
    ) -> dict[uuid.UUID, CardFacts]:
        """What a brief names each card with: name, cost, rarity, text."""
        ...

    def primer(self, set_code: str, event_type: str) -> str:
        """The format's Format Primer, the Draft Summary's second cached block."""
        ...


class SavedReviews(Protocol):
    """Claude's stored prose, by draft and owner (`draft_reviews`, `pick_notes`)."""

    def get(self, draft_id: str, user_id: uuid.UUID | None) -> SavedReview | None: ...

    def add_note(
        self, draft_id: str, user_id: uuid.UUID | None, note: SavedNote
    ) -> SavedNote:
        """Store a note unless one is already stored for its pick, and return
        whichever is stored: when two requests race, the first one wins."""
        ...

    def save_deck(
        self,
        draft_id: str,
        user_id: uuid.UUID | None,
        deck: SubmittedDeck,
        summary: SavedSummary | None,
    ) -> None:
        """Make `deck` the current deck. With a summary, it is also the
        Reviewed Deck and the summary is stored beside it."""
        ...


class Coach(Protocol):
    """Claude, writing prose from a brief (`llm/coach.py`).

    Raises `SpendingCapReached`, `PickNoteFailed` or `DraftSummaryFailed`.
    """

    def pick_note(
        self, brief: PickBrief, *, draft_key: str, user_id: uuid.UUID | None
    ) -> PickNote: ...

    def draft_summary(
        self,
        brief: SummaryBrief,
        primer: str,
        *,
        draft_key: str,
        user_id: uuid.UUID | None,
    ) -> DraftSummary: ...


# draft id -> (draft payload, event metadata), or `DraftInputError`.
Fetch = Callable[[str], tuple[dict[str, Any], dict[str, Any]]]


@dataclass(frozen=True)
class _Loaded:
    """A cached draft, ready to analyse.

    `log.event_type` is the event type whose statistics rate it, which is
    what `analyze_draft` checks against `inputs`. `event_type` is what the
    draft really was, which is what the person is shown.
    """

    log: DraftLog
    event_type: str
    inputs: FormatInputs

    @property
    def draft_key(self) -> str:
        """How `llm_calls` names the draft: "17lands:<draft id>"."""
        return f"{self.log.source}:{self.log.source_id}"


T = TypeVar("T")


class ReviewService:
    def __init__(
        self,
        store: ReplayStore,
        catalog: Catalog,
        fetch: Fetch,
        limiter: RateLimiter,
        supported_sets: frozenset[str],
        saved: SavedReviews,
        coach: Callable[[], Coach],
    ) -> None:
        self.store = store
        self.catalog = catalog
        self.fetch = fetch
        self.limiter = limiter
        self.supported_sets = supported_sets
        self.saved = saved
        # Built only when prose is written, so an anonymous request never
        # makes an Anthropic client.
        self._coach = coach

    # ----------------------------------------------------------------------
    # The Python operations: anyone may call them
    # ----------------------------------------------------------------------

    def import_draft(self, link: str, client: str) -> ImportResponse:
        """Whatever the user pasted (a 17Lands URL or a draft id) into a
        cached draft.

        The order matters. A draft already in the Replay Cache is answered at
        once, with no 17Lands request and no use of the caller's allowance.
        Only a miss is charged, and it is charged before the fetch, so a
        failed fetch still counts.
        """
        try:
            draft_id = seventeen_lands.parse_draft_id(link)
            if self.store.has(draft_id):
                return ImportResponse(draft_id=draft_id, cached=True)

            self._charge("fetch", client)
            draft, metadata = self.fetch(draft_id)

            # Refuse an unsupported set before matching any cards: we may hold
            # no card data for it, and a log of it must not be cached.
            set_code = seventeen_lands.draft_set_code(metadata)
            if set_code not in self.supported_sets:
                raise ReviewError(
                    "unsupported_set",
                    f"BoosterTutor reviews {self._supported_names()} drafts for "
                    "now. More sets are coming.",
                    {"set_code": set_code},
                )

            log = seventeen_lands.parse_draft(
                draft, metadata, self.catalog.names(set_code), draft_id=draft_id
            )
        except DraftInputError as exc:
            raise ReviewError.from_input(exc) from exc
        self.store.add(log)
        return ImportResponse(draft_id=draft_id, cached=False)

    def review(self, draft_id: str) -> DraftReview:
        """Every pick of a cached draft graded against today's statistics."""
        loaded = self._load(draft_id)
        log = loaded.log
        analysis = analyze_draft(log, loaded.inputs)
        return DraftReview(
            draft_id=draft_id,
            set_code=log.set_code,
            event_type=loaded.event_type,
            drafted_at=log.drafted_at,
            wins=log.wins,
            losses=log.losses,
            pack_size=log.pack_size,
            analysis=analysis,
            verdict_counts=dict(Counter(p.verdict for p in analysis.picks)),
            noted_picks=[
                (p.pack_number, p.pick_number) for p in analysis.picks if p.noted
            ],
            cards=self.catalog.card_infos(log.set_code, _cards_named_in(analysis)),
            basic_lands=self.catalog.basic_lands(log.set_code),
        )

    def rate_deck(
        self,
        draft_id: str,
        submitted: SubmittedDeck,
        client: str,
        caller: Coached | None = None,
    ) -> CoachedDeckReview:
        """Deck Ratings for 40 cards built from a cached draft's pool.

        An anonymous deck is rated and forgotten (ADR 0031 s5). A coached
        caller's deck is stored, and their first one gets a Draft Summary.
        """
        _check_draft_id(draft_id)
        # Charged before the deck is checked, so a stream of bad decks runs
        # out of allowance too.
        self._charge("deck", client)
        loaded = self._load(draft_id)
        inputs = loaded.inputs
        try:
            deck = deck_from_pool(
                _pool(loaded.log, inputs),
                main=submitted.cards,
                basics=submitted.basics,
            )
        except DeckError as exc:
            raise ReviewError("invalid_deck", str(exc)) from exc

        metrics = deck_metrics(deck, inputs)
        model = self.catalog.deck_model(loaded.log.set_code, inputs.event_type)
        ratings = rate_deck(metrics, model)
        rated = CoachedDeckReview(
            ratings=ratings,
            metrics=metrics,
            colour_sources=colour_sources(
                [inputs.cards[oid] for oid in deck.main],
                deck.basics,
                inputs.mana_sources,
            ),
            cards=self.catalog.card_infos(
                loaded.log.set_code, _cards_named_in_metrics(metrics)
            ),
        )
        if caller is None:
            return rated

        saved = self.saved.get(draft_id, caller.user_id)
        if saved is not None and saved.summary is not None:
            # The summary is written once, about the Reviewed Deck. Later
            # decks are kept as the current deck and get ratings only.
            self.saved.save_deck(draft_id, caller.user_id, submitted, None)
            return rated

        analysis = analyze_draft(loaded.log, inputs)
        facts = self.catalog.card_facts(loaded.log.set_code, analysis_cards(analysis))
        brief = summary_brief(analysis, deck, metrics, ratings, facts, inputs)
        primer = self.catalog.primer(loaded.log.set_code, inputs.event_type)
        try:
            written = self._write(
                lambda: self._coach().draft_summary(
                    brief,
                    primer,
                    draft_key=loaded.draft_key,
                    user_id=caller.user_id,
                )
            )
        except ReviewError as exc:
            # The ratings still stand. Without a summary this deck is only
            # the current deck, so the next one tries again.
            self.saved.save_deck(draft_id, caller.user_id, submitted, None)
            rated.summary_unavailable = ProseUnavailable(
                kind=exc.kind, message=exc.message
            )
            return rated

        summary = SavedSummary(
            draft_arc=written.draft_arc,
            deck=written.deck,
            lesson=written.lesson,
            key_picks=[
                SummaryKeyPick(pack_number=k.pack_number, pick_number=k.pick_number)
                for k in written.key_picks
            ],
            prompt_version=written.prompt_version,
            model=written.model,
            stats_snapshot=inputs.stats_snapshot,
        )
        self.saved.save_deck(draft_id, caller.user_id, submitted, summary)
        rated.summary = CoachSummary(**summary.model_dump(), stale=False)
        return rated

    # ----------------------------------------------------------------------
    # Claude's prose: a coached caller only (ADR 0031 s2)
    # ----------------------------------------------------------------------

    def pick_note(self, draft_id: str, n: int, caller: Coached) -> CoachNote:
        """The Pick Note for the draft's `n`th pick (1 is P1p1), written if new.

        A stored note is returned as it is, even when the statistics have
        moved on since: it is tagged `stale` rather than paid for twice.
        """
        loaded = self._load(draft_id)
        inputs = loaded.inputs
        analysis = analyze_draft(loaded.log, inputs)
        if not 1 <= n <= len(analysis.picks):
            raise ReviewError(
                "invalid_input", f"this draft has picks 1 to {len(analysis.picks)}"
            )
        pick = analysis.picks[n - 1]
        if not pick.noted:
            raise ReviewError(
                "not_noted",
                "Only a Noted Pick gets a coach's note, and this isn't one.",
            )

        saved = self.saved.get(draft_id, caller.user_id)
        for stored in saved.notes if saved else []:
            if (stored.pack_number, stored.pick_number) == (
                pick.pack_number,
                pick.pick_number,
            ):
                return _coach_note(stored, inputs)

        facts = self.catalog.card_facts(loaded.log.set_code, analysis_cards(analysis))
        brief = pick_brief(
            analysis,
            facts,
            inputs.cfg,
            pack_number=pick.pack_number,
            pick_number=pick.pick_number,
        )
        written = self._write(
            lambda: self._coach().pick_note(
                brief, draft_key=loaded.draft_key, user_id=caller.user_id
            )
        )
        stored = self.saved.add_note(
            draft_id,
            caller.user_id,
            SavedNote(
                pack_number=written.pack_number,
                pick_number=written.pick_number,
                kind=written.kind,
                note=written.note,
                prompt_version=written.prompt_version,
                model=pick_note.MODEL,
                stats_snapshot=inputs.stats_snapshot,
            ),
        )
        return _coach_note(stored, inputs)

    def coach_review(self, draft_id: str, caller: Coached) -> CoachReview:
        """Everything stored for this caller about the draft, tagged against
        today's Stats Snapshot. Calls no Claude."""
        loaded = self._load(draft_id)
        saved = self.saved.get(draft_id, caller.user_id)
        if saved is None:
            return CoachReview(
                notes=[], summary=None, reviewed_deck=None, current_deck=None
            )
        notes = sorted(saved.notes, key=lambda n: (n.pack_number, n.pick_number))
        summary = saved.summary
        return CoachReview(
            notes=[_coach_note(n, loaded.inputs) for n in notes],
            summary=(
                CoachSummary(
                    **summary.model_dump(),
                    stale=summary.stats_snapshot != loaded.inputs.stats_snapshot,
                )
                if summary is not None
                else None
            ),
            reviewed_deck=saved.reviewed_deck,
            current_deck=saved.current_deck,
        )

    # ----------------------------------------------------------------------
    # The shared steps
    # ----------------------------------------------------------------------

    def _load(self, draft_id: str) -> _Loaded:
        """A cached draft and the statistics that rate it."""
        _check_draft_id(draft_id)
        log = self.store.get(draft_id)
        if log is None:
            raise ReviewError(
                "draft_not_found",
                "That draft hasn't been imported yet. Submit its 17Lands link first.",
            )
        try:
            inputs = self.catalog.format_inputs(
                log.set_code, stats_event_type(log.event_type)
            )
        except FormatNotReady as exc:
            raise ReviewError(
                "format_not_ready",
                f"There are no statistics for {log.set_code.upper()} "
                f"{log.event_type} yet. Please try again later.",
            ) from exc
        # A Traditional or Open draft is rated with the Premier statistics,
        # so it is analysed as a Premier draft.
        analysed = log.model_copy(update={"event_type": inputs.event_type})
        return _Loaded(log=analysed, event_type=log.event_type, inputs=inputs)

    def _charge(self, bucket: Bucket, client: str) -> None:
        try:
            self.limiter.check_and_record(bucket, client)
        except RateLimited as exc:
            what = (
                "drafts imported from 17Lands"
                if bucket == "fetch"
                else "decks submitted"
            )
            raise ReviewError(
                "rate_limited",
                f"Too many {what} just now. Please try again in a little while.",
                retry_after=exc.retry_after,
            ) from exc

    def _write(self, write: Callable[[], T]) -> T:
        """Call Claude, with its failures as `ReviewError`s."""
        try:
            return write()
        except SpendingCapReached as exc:
            raise ReviewError("coach_retired", str(exc)) from exc
        except (PickNoteFailed, DraftSummaryFailed) as exc:
            raise ReviewError(
                "prose_failed",
                "The coach couldn't write this just now. Please try again.",
                str(exc),
            ) from exc

    def _supported_names(self) -> str:
        """ "HOB", or "HOB and MSH": the sets a review is offered for."""
        return " and ".join(sorted(s.upper() for s in self.supported_sets))


# --------------------------------------------------------------------------
# Pure helpers
# --------------------------------------------------------------------------


def _check_draft_id(draft_id: str) -> None:
    if not DRAFT_ID_RE.match(draft_id):
        raise ReviewError("invalid_input", "that isn't a 17Lands draft id")


def _coach_note(note: SavedNote, inputs: FormatInputs) -> CoachNote:
    """A stored note, tagged if today's statistics are not the ones it read."""
    return CoachNote(
        **note.model_dump(), stale=note.stats_snapshot != inputs.stats_snapshot
    )


def _pool(log: DraftLog, inputs: FormatInputs) -> list[uuid.UUID]:
    """The cards a deck can be built from: every pick but the basic lands.

    A basic land drafted is pruned (ADR 0025 s1); the deck builder's own
    buttons add basics instead.
    """
    return [
        p.picked
        for p in log.picks
        if not inputs.cards.get(p.picked, {})
        .get("type_line", "")
        .startswith("Basic Land")
    ]


def _cards_named_in(analysis: DraftAnalysis) -> set[uuid.UUID]:
    """Every card the review page can show: each pack, and the wheel tables."""
    named = {
        oid
        for p in analysis.picks
        for oid in (p.picked, *(c.oracle_id for c in p.cards))
    }
    for wheel in analysis.wheels:
        for lap in wheel.laps:
            named.update(c.oracle_id for c in (*lap.wheeled, *lap.taken_by_table))
        named.update(c.best_wheeled for c in wheel.colors if c.best_wheeled is not None)
    return named


def _cards_named_in_metrics(metrics: DeckMetrics) -> set[uuid.UUID]:
    """Every card the Deck Ratings panel names: the short spell, the notable
    omission and the synergy firings."""
    named: set[uuid.UUID] = set()
    if metrics.mana_short_spell is not None:
        named.add(metrics.mana_short_spell)
    for firing in metrics.synergy_firings:
        named.add(firing.oracle_id)
        named.update(firing.contributing)
    if metrics.notable_omission is not None:
        named.add(metrics.notable_omission.oracle_id)
        named.add(metrics.notable_omission.instead_of)
    return named
