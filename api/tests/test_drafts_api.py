"""POST and GET /api/drafts: import a 17Lands draft once, review it any time.

No network and no database (`review_world.py`). What is under test is the
rules: what is fetched, what is cached, what is recomputed, and what each
failure says.
"""

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from review_world import DRAFT_ID, World, error_kind, submit

from boostertutor.analysis.draft import FormatInputs
from boostertutor.parsing.errors import DraftInputError
from boostertutor.review.rate_limit import Limits
from boostertutor.schemas import DraftLog


@pytest.fixture
def world(inputs: FormatInputs, names: dict[str, uuid.UUID]) -> World:
    return World(inputs, names)


@pytest.fixture
def client(world: World) -> Iterator[TestClient]:
    yield from world.client()


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


def test_a_cache_hit_does_not_count_against_the_limit(
    client: TestClient, world: World
) -> None:
    world.limits["fetch"] = Limits(per_minute=1, per_day=1)
    for _ in range(3):
        assert submit(client).status_code == 200
    assert world.ledger.count("fetch") == 1


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
    world.supported = frozenset({"msh", "fra"})
    response = submit(client)
    assert response.status_code == 422
    assert error_kind(response) == "unsupported_set"
    # The message names the sets that are supported, from config.
    assert "FRA and MSH" in response.json()["detail"]["message"]
    assert world.store.logs == {}


def test_a_failed_fetch_still_counts_against_the_limit(
    client: TestClient, world: World
) -> None:
    # Otherwise a client could hammer 17Lands with ids that fail.
    world.fetch_error = DraftInputError("draft_not_found", "no")
    submit(client)
    assert world.ledger.count("fetch") == 1


def test_over_the_limit_is_a_429_with_retry_after_and_no_fetch(
    client: TestClient, world: World
) -> None:
    world.limits["fetch"] = Limits(per_minute=1, per_day=50)
    assert submit(client, "a" * 32).status_code == 200
    response = submit(client, "b" * 32)
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


def test_the_review_carries_the_sets_basic_lands_for_the_deck_builder(
    client: TestClient,
) -> None:
    submit(client)
    basics = client.get(f"/api/drafts/{DRAFT_ID}").json()["basic_lands"]
    assert set(basics) == set("WUBRG")
    assert basics["R"]["name"] == "Mountain"
    assert basics["R"]["image_normal"].endswith("Mountain.jpg")


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
    assert len(world.stats_asked) == 2
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


@pytest.mark.parametrize("event", ["TradDraft", "OpenDraft_HOB_20261001"])
def test_traditional_and_open_drafts_are_rated_with_the_premier_statistics(
    client: TestClient, world: World, event: str
) -> None:
    world.event_type = event
    submit(client)
    response = client.get(f"/api/drafts/{DRAFT_ID}")
    assert response.status_code == 200
    assert world.stats_asked == ["PremierDraft"]
    # The review still says what kind of draft it really was.
    assert response.json()["event_type"] == event


def test_a_pick_two_draft_is_refused_as_an_unsupported_format(
    client: TestClient, world: World
) -> None:
    world.event_type = "PickTwoDraft"
    assert error_kind(submit(client)) == "unsupported_format"
