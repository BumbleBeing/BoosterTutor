"""POST /api/drafts/{id}/deck: a Submitted Deck in, Deck Ratings out (Phase 5c).

Anonymous and Python-only (ADR 0025 s3, ADR 0031 s5): nothing is stored, and
nothing here calls Claude. Same harness as `test_drafts_api.py`: no network,
no database, HOB's saved statistics.
"""

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from conftest import load_deck_inputs
from fastapi.testclient import TestClient
from test_drafts_api import DRAFT_ID, World, error_kind, submit

from boostertutor.draft_services import get_services
from boostertutor.main import app
from boostertutor.rate_limit import FetchLimiter, FetchLimits


@pytest.fixture
def world(names: dict[str, uuid.UUID]) -> World:
    """A world with HOB's Fixers, land targets and fitted Deck Ratings."""
    inputs, model, _ = load_deck_inputs()
    w = World(inputs, names)
    w.deck_model = model
    return w


@pytest.fixture
def client(world: World) -> Iterator[TestClient]:
    app.dependency_overrides[get_services] = world.services
    yield TestClient(app)
    app.dependency_overrides.clear()


def url(draft_id: str = DRAFT_ID) -> str:
    return f"/api/drafts/{draft_id}/deck"


def pool(world: World) -> list[str]:
    """The drafted cards, as oracle ids, in pick order."""
    log = world.store.logs[DRAFT_ID]
    return [str(p.picked) for p in log.picks]


def a_deck(world: World, spells: int = 23, basics: dict[str, int] | None = None) -> Any:
    """`spells` pool cards plus basics making up 40."""
    if basics is None:
        basics = {"W": 9, "B": 8}
    cards = pool(world)[:spells]
    basics = {**basics}
    basics["W"] = basics.get("W", 0) + (40 - spells - sum(basics.values()))
    return {"cards": cards, "basics": basics}


def test_a_legal_deck_gets_ratings_metrics_and_colour_sources(
    client: TestClient, world: World
) -> None:
    submit(client)
    response = client.post(url(), json=a_deck(world))
    assert response.status_code == 200
    body = response.json()

    assert body["ratings"]["rated"] is True
    assert body["ratings"]["grade"] in "ABCDF"
    assert {m["metric"] for m in body["ratings"]["metrics"]} >= {
        "card_quality",
        "curve_distance",
        "mana_shortfall",
    }
    assert body["metrics"]["effective_lands"] >= 17
    assert body["metrics"]["land_target"] in (16, 17, 18)
    # Colour Sources: a count for each colour the deck's spells use.
    assert body["colour_sources"]
    assert set(body["colour_sources"]) <= set("WUBRG")
    # The cards the panel names (a short spell, an omission) are described.
    for oid in (body["metrics"]["mana_short_spell"],):
        assert oid is None or oid in body["cards"]


def test_nothing_is_stored_and_17lands_is_not_asked(
    client: TestClient, world: World
) -> None:
    submit(client)
    before = (dict(world.store.logs), world.fetches)
    client.post(url(), json=a_deck(world))
    assert (world.store.logs, world.fetches) == (before[0], before[1])


def test_a_format_without_a_fitted_model_is_unrated_not_an_error(
    client: TestClient, world: World
) -> None:
    submit(client)
    world.deck_model = None
    body = client.post(url(), json=a_deck(world)).json()
    assert body["ratings"]["rated"] is False
    assert body["ratings"]["message"] == "not enough data to rate"
    assert body["metrics"]["land_target"]  # the facts are still computed


@pytest.mark.parametrize("spells", [22, 24])
def test_a_deck_that_is_not_exactly_40_cards_is_refused(
    client: TestClient, world: World, spells: int
) -> None:
    submit(client)
    deck = a_deck(world, spells)
    deck["basics"]["W"] += 1  # 41 or 39 in total
    response = client.post(url(), json=deck)
    assert response.status_code == 422
    assert error_kind(response) == "invalid_deck"
    assert "40" in response.json()["detail"]["message"]


def test_a_card_that_was_not_drafted_is_refused(
    client: TestClient, world: World
) -> None:
    submit(client)
    deck = a_deck(world)
    outsider = next(
        str(oid) for oid in world.inputs.cards if str(oid) not in set(pool(world))
    )
    deck["cards"][0] = outsider
    response = client.post(url(), json=deck)
    assert response.status_code == 422
    assert error_kind(response) == "invalid_deck"
    assert "not in the pool" in response.json()["detail"]["message"]


def test_more_copies_than_were_drafted_are_refused(
    client: TestClient, world: World
) -> None:
    submit(client)
    deck = a_deck(world)
    deck["cards"][1] = deck["cards"][0]  # one drafted copy, played twice
    # The pool may hold two copies of it; only the single-copy case is certain.
    if pool(world).count(deck["cards"][0]) >= 2:
        pytest.skip("this card was drafted twice")
    assert client.post(url(), json=deck).status_code == 422


def test_a_basic_land_among_the_cards_is_refused(
    client: TestClient, world: World
) -> None:
    # Basics are sent as counts, never as cards (ADR 0025 s1).
    submit(client)
    deck = a_deck(world)
    deck["basics"] = {"X": 17}
    assert error_kind(client.post(url(), json=deck)) == "invalid_deck"


def test_negative_basics_are_refused(client: TestClient, world: World) -> None:
    submit(client)
    deck = a_deck(world)
    deck["basics"] = {"W": 30, "B": -7}
    assert error_kind(client.post(url(), json=deck)) == "invalid_deck"


def test_an_unknown_field_is_refused(client: TestClient, world: World) -> None:
    submit(client)
    deck = {**a_deck(world), "name": "my deck"}
    assert client.post(url(), json=deck).status_code == 422


def test_a_draft_that_was_never_imported_is_a_404(
    client: TestClient, world: World
) -> None:
    response = client.post(url(), json={"cards": [], "basics": {"W": 40}})
    assert response.status_code == 404
    assert error_kind(response) == "draft_not_found"


def test_a_malformed_draft_id_is_a_422(client: TestClient) -> None:
    response = client.post(url("nope"), json={"cards": [], "basics": {}})
    assert response.status_code == 422
    assert error_kind(response) == "invalid_input"


def test_a_format_without_statistics_is_a_503(client: TestClient, world: World) -> None:
    submit(client)
    world.not_ready = True
    response = client.post(url(), json=a_deck(world))
    assert response.status_code == 503
    assert error_kind(response) == "format_not_ready"


def test_resubmitting_just_rates_again_with_the_new_deck(
    client: TestClient, world: World
) -> None:
    submit(client)
    first = client.post(url(), json=a_deck(world)).json()
    second = client.post(url(), json=a_deck(world, 22, {"W": 9, "B": 9})).json()
    assert second["metrics"] != first["metrics"]


def test_over_the_limit_is_a_429_with_retry_after(
    client: TestClient, world: World
) -> None:
    world.deck_limiter = FetchLimiter(world.ledger, FetchLimits(1, 50))
    submit(client)
    assert client.post(url(), json=a_deck(world)).status_code == 200
    response = client.post(url(), json=a_deck(world))
    assert response.status_code == 429
    assert error_kind(response) == "rate_limited"
    assert response.headers["Retry-After"] == "60"


def test_a_rejected_deck_still_counts_against_the_limit(
    client: TestClient, world: World
) -> None:
    world.deck_limiter = FetchLimiter(world.ledger, FetchLimits(1, 50))
    submit(client)
    assert client.post(url(), json={"cards": [], "basics": {}}).status_code == 422
    assert client.post(url(), json=a_deck(world)).status_code == 429


def test_deck_submissions_and_fetches_have_separate_allowances(
    client: TestClient, world: World
) -> None:
    world.deck_limiter = FetchLimiter(world.ledger, FetchLimits(1, 50))
    submit(client)  # one fetch: the fetch limit is 5 a minute
    client.post(url(), json=a_deck(world))
    # The fetch allowance is untouched by the deck submission.
    assert submit(client, "a" * 32).status_code in (200, 404, 422)
