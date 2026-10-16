"""POST and GET /api/drafts: import a 17Lands draft once, review it any time.

No network and no database. The 17Lands fetch is replaced by the saved
payloads, the Replay Cache by a dict, the statistics by the HOB snapshot in
`fixtures/format_inputs`. What is under test is the wiring: what is fetched,
what is cached, what is recomputed, and what each failure says.
"""

import json
import uuid
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from boostertutor.analysis.draft import FormatInputs
from boostertutor.draft_services import CardInfo, DraftServices, get_services
from boostertutor.format_inputs import FormatNotReady
from boostertutor.main import app
from boostertutor.parsing.errors import DraftInputError
from boostertutor.rate_limit import FetchLimiter, FetchLimits
from boostertutor.schemas import DraftLog

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
        self.rows: list[tuple[str, Any]] = []

    def count_since(self, key: str, since: Any) -> int:
        return sum(1 for k, at in self.rows if k == key and at > since)

    def record(self, key: str, at: Any) -> None:
        self.rows.append((key, at))

    def prune(self, before: Any) -> None:
        pass


class World:
    """Everything the endpoints touch, with a count of how often 17Lands was asked."""

    def __init__(
        self,
        inputs: FormatInputs,
        names: dict[str, uuid.UUID],
        per_minute: int = 5,
    ) -> None:
        self.inputs = inputs
        self.names = names
        self.store = MemoryStore()
        self.fetches = 0
        self.inputs_loads = 0
        self.fetch_error: Exception | None = None
        self.not_ready = False
        self.supported = frozenset({"hob"})
        self.limits = FetchLimits(per_minute=per_minute, per_day=50)
        self.ledger = MemoryLedger()
        self.limiter = FetchLimiter(self.ledger, self.limits)

    def fetch(self, draft_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
        self.fetches += 1
        if self.fetch_error is not None:
            raise self.fetch_error
        return (
            json.loads((FIXTURES / "draft.json").read_text()),
            json.loads((FIXTURES / "event_metadata.json").read_text()),
        )

    def inputs_for(self, set_code: str, event_type: str) -> FormatInputs:
        self.inputs_loads += 1
        if self.not_ready:
            raise FormatNotReady("no statistics yet")
        return self.inputs

    def card_infos_for(
        self, set_code: str, ids: Iterable[uuid.UUID]
    ) -> dict[uuid.UUID, CardInfo]:
        return {
            oid: CardInfo(
                name=f"card {oid.hex[:6]}",
                mana_cost=self.inputs.cards[oid].get("mana_cost"),
                type_line=self.inputs.cards[oid]["type_line"],
                cmc=self.inputs.cards[oid]["cmc"],
                colors=self.inputs.cards[oid]["colors"],
                rarity="common",
                image_normal=None,
                image_art_crop=None,
            )
            for oid in ids
            if oid in self.inputs.cards
        }

    def services(self) -> DraftServices:
        return DraftServices(
            store=self.store,
            limiter=self.limiter,
            names_for=lambda set_code: self.names,
            inputs_for=self.inputs_for,
            card_infos_for=self.card_infos_for,
            fetch=self.fetch,
            supported_sets=self.supported,
        )


@pytest.fixture
def world(inputs: FormatInputs, names: dict[str, uuid.UUID]) -> World:
    return World(inputs, names)


@pytest.fixture
def client(world: World) -> Iterator[TestClient]:
    app.dependency_overrides[get_services] = world.services
    yield TestClient(app)
    app.dependency_overrides.clear()


def submit(client: TestClient, link: str = URL) -> Any:
    return client.post("/api/drafts", json={"link": link})


def error_kind(response: Any) -> str:
    kind: str = response.json()["detail"]["kind"]
    return kind


# --------------------------------------------------------------------------
# POST: import
# --------------------------------------------------------------------------


def test_a_link_is_fetched_cached_and_its_id_returned(
    client: TestClient, world: World
) -> None:
    response = submit(client)
    assert response.status_code == 200
    assert response.json() == {"draft_id": DRAFT_ID, "cached": False}
    assert world.fetches == 1
    assert list(world.store.logs) == [DRAFT_ID]


def test_a_bare_draft_id_works_too(client: TestClient) -> None:
    assert submit(client, DRAFT_ID.upper()).json()["draft_id"] == DRAFT_ID


def test_a_second_submit_of_the_same_link_makes_no_17lands_request(
    client: TestClient, world: World
) -> None:
    submit(client)
    again = submit(client, DRAFT_ID)  # the id alone is the same draft
    assert again.json() == {"draft_id": DRAFT_ID, "cached": True}
    assert world.fetches == 1


def test_a_cache_hit_does_not_count_against_the_limit(world: World) -> None:
    world.limiter = FetchLimiter(world.ledger, FetchLimits(per_minute=1, per_day=1))
    app.dependency_overrides[get_services] = world.services
    client = TestClient(app)
    for _ in range(3):
        assert submit(client).status_code == 200
    assert len(world.ledger.rows) == 1
    app.dependency_overrides.clear()


def test_text_with_no_draft_id_is_rejected_before_anything_is_fetched(
    client: TestClient, world: World
) -> None:
    response = submit(client, "https://example.com/not-a-draft")
    assert response.status_code == 422
    assert error_kind(response) == "invalid_input"
    assert world.fetches == 0


def test_a_missing_link_field_is_rejected(client: TestClient) -> None:
    assert client.post("/api/drafts", json={}).status_code == 422
    # The pasted-log input was dropped (ADR 0031 s3).
    assert client.post("/api/drafts", json={"log_text": "x"}).status_code == 422


def test_a_private_or_unknown_draft_is_a_404(client: TestClient, world: World) -> None:
    world.fetch_error = DraftInputError("draft_not_found", "17Lands can't find that")
    response = submit(client)
    assert response.status_code == 404
    assert error_kind(response) == "draft_not_found"
    assert world.store.logs == {}


def test_an_upstream_failure_is_a_502_and_is_not_cached(
    client: TestClient, world: World
) -> None:
    world.fetch_error = DraftInputError("upstream_failure", "17Lands didn't answer")
    response = submit(client)
    assert response.status_code == 502
    assert error_kind(response) == "upstream_failure"
    assert world.store.logs == {}


def test_a_set_we_do_not_support_is_refused_and_not_cached(
    client: TestClient, world: World
) -> None:
    world.supported = frozenset({"msh"})
    response = submit(client)
    assert response.status_code == 422
    assert error_kind(response) == "unsupported_set"
    assert "HOB" in response.json()["detail"]["message"]
    assert world.store.logs == {}


def test_a_failed_fetch_still_counts_against_the_limit(
    client: TestClient, world: World
) -> None:
    # Otherwise a client could hammer 17Lands with ids that fail.
    world.fetch_error = DraftInputError("draft_not_found", "no")
    submit(client)
    assert len(world.ledger.rows) == 1


def test_over_the_limit_is_a_429_with_retry_after_and_no_fetch(
    inputs: FormatInputs, names: dict[str, uuid.UUID]
) -> None:
    world = World(inputs, names, per_minute=1)
    app.dependency_overrides[get_services] = world.services
    client = TestClient(app)
    assert submit(client, "a" * 32).status_code in (200, 404, 422)
    response = submit(client, "b" * 32)
    app.dependency_overrides.clear()
    assert response.status_code == 429
    assert error_kind(response) == "rate_limited"
    assert response.headers["Retry-After"] == "60"
    assert world.fetches == 1


# --------------------------------------------------------------------------
# GET: the review
# --------------------------------------------------------------------------


def test_an_imported_draft_returns_its_verdicts(
    client: TestClient,
) -> None:
    submit(client)
    response = client.get(f"/api/drafts/{DRAFT_ID}")
    assert response.status_code == 200
    body = response.json()

    assert body["draft_id"] == DRAFT_ID
    assert (body["set_code"], body["event_type"]) == ("hob", "PremierDraft")
    assert (body["wins"], body["losses"]) == (3, 3)
    assert body["pack_size"] == 14

    picks = body["analysis"]["picks"]
    assert len(picks) == 42
    assert {p["verdict"] for p in picks} <= {
        "indifferent",
        "solid",
        "questionable",
        "mistake",
    }
    assert sum(body["verdict_counts"].values()) == 42
    # Noted Pick markers ride on each pick, as the analysis decided them.
    assert body["noted_picks"] == [
        [p["pack_number"], p["pick_number"]] for p in picks if p["noted"]
    ]
    # Fitness scores are on every card in every pack.
    assert all(c["scored"] is not None for c in picks[0]["cards"])


def test_the_review_names_every_card_it_mentions(client: TestClient) -> None:
    submit(client)
    body = client.get(f"/api/drafts/{DRAFT_ID}").json()
    mentioned = {
        card["oracle_id"]
        for pick in body["analysis"]["picks"]
        for card in pick["cards"]
    } | {pick["picked"] for pick in body["analysis"]["picks"]}
    assert mentioned <= set(body["cards"])
    some = next(iter(body["cards"].values()))
    assert set(some) == {
        "name",
        "mana_cost",
        "type_line",
        "cmc",
        "colors",
        "rarity",
        "image_normal",
        "image_art_crop",
    }


def test_the_review_carries_no_prose_and_no_claude_fields(
    client: TestClient,
) -> None:
    submit(client)
    body = client.get(f"/api/drafts/{DRAFT_ID}").json()
    assert not {"pick_notes", "summary", "note"} & set(body)


def test_verdicts_are_recomputed_on_every_get_never_stored(
    client: TestClient, world: World
) -> None:
    submit(client)
    client.get(f"/api/drafts/{DRAFT_ID}")
    client.get(f"/api/drafts/{DRAFT_ID}")
    assert world.inputs_loads == 2
    # All the cache holds is the parsed log.
    assert all(isinstance(v, DraftLog) for v in world.store.logs.values())


def test_a_get_never_asks_17lands(client: TestClient, world: World) -> None:
    submit(client)
    client.get(f"/api/drafts/{DRAFT_ID}")
    assert world.fetches == 1


def test_a_draft_that_was_never_imported_is_a_404_and_is_not_fetched(
    client: TestClient, world: World
) -> None:
    response = client.get(f"/api/drafts/{DRAFT_ID}")
    assert response.status_code == 404
    assert error_kind(response) == "draft_not_found"
    assert world.fetches == 0


def test_a_malformed_id_is_a_422(client: TestClient) -> None:
    response = client.get("/api/drafts/not-an-id")
    assert response.status_code == 422
    assert error_kind(response) == "invalid_input"


def test_a_format_without_statistics_is_a_503(client: TestClient, world: World) -> None:
    submit(client)
    world.not_ready = True
    response = client.get(f"/api/drafts/{DRAFT_ID}")
    assert response.status_code == 503
    assert error_kind(response) == "format_not_ready"
