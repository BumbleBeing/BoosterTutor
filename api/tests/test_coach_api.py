"""Claude's prose behind the Admin Key (ADR 0031 s2, s5; Phase 5d).

`POST /api/drafts/{id}/picks/{n}/note`, `GET /api/drafts/{id}/coach`, and
the Draft Summary on a coached caller's first deck. Claude is the
`FakeCoach` in `review_world.py`, so nothing here calls the API or spends
money; `coach.calls` counts what would have been paid for. The last tests
run the real `ClaudeCoach` over a fake SDK client, to show the spending cap
and the `llm_calls` row apply to an admin-key call too.
"""

import uuid
from collections.abc import Iterator
from decimal import Decimal
from typing import Any

import pytest
from conftest import load_deck_inputs
from fastapi.testclient import TestClient
from pydantic import SecretStr
from review_world import DRAFT_ID, World, error_kind, new_stats, submit
from test_pick_note import FakeClient, Ledger, good

from boostertutor.analysis.fitness import FitnessConfig
from boostertutor.briefing import CardFacts, pick_brief
from boostertutor.config import settings
from boostertutor.llm.coach import ClaudeCoach
from boostertutor.llm.pick_note import PickNoteFailed, load_prompt
from boostertutor.llm.spending import SpendingCapReached
from boostertutor.review.access import admin_key_matches
from boostertutor.schemas.draft_analysis import DraftAnalysis

KEY = "a-long-random-admin-key-for-the-tests-only"
ADMIN = {"X-Admin-Key": KEY}


@pytest.fixture(autouse=True)
def admin_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """The API is configured with `KEY`; tests that need admin off unset it."""
    monkeypatch.setattr(settings, "admin_key", SecretStr(KEY))


@pytest.fixture
def world(names: dict[str, uuid.UUID]) -> World:
    inputs, model, _ = load_deck_inputs()
    w = World(inputs, names)
    w.fitted_model = model
    return w


@pytest.fixture
def client(world: World) -> Iterator[TestClient]:
    for c in world.client():
        submit(c)
        yield c


def noted(client: TestClient) -> list[int]:
    """Every Noted Pick of the draft as `n`, its place in the draft (1 = P1p1)."""
    review = client.get(f"/api/drafts/{DRAFT_ID}").json()
    size = review["pack_size"]
    return [(pack - 1) * size + pick for pack, pick in review["noted_picks"]]


def note_url(n: int) -> str:
    return f"/api/drafts/{DRAFT_ID}/picks/{n}/note"


def a_deck(world: World, spells: int = 23) -> dict[str, Any]:
    log = world.store.logs[DRAFT_ID]
    cards = [str(p.picked) for p in log.picks][:spells]
    return {"cards": cards, "basics": {"W": 40 - spells - 8, "B": 8}}


# --------------------------------------------------------------------------
# The Admin Key
# --------------------------------------------------------------------------


def test_the_key_must_match_exactly_and_no_key_configured_lets_nobody_in() -> None:
    assert admin_key_matches(KEY, KEY)
    assert not admin_key_matches(KEY + "x", KEY)
    assert not admin_key_matches("", KEY)
    assert not admin_key_matches(KEY, None)
    assert not admin_key_matches("", "")


@pytest.mark.parametrize(
    "headers",
    [{}, {"X-Admin-Key": "wrong"}, {"X-Admin-Key": ""}],
    ids=["no key", "wrong key", "empty key"],
)
def test_without_the_key_neither_endpoint_calls_claude(
    client: TestClient, world: World, headers: dict[str, str]
) -> None:
    n = noted(client)[0]
    response = client.post(note_url(n), headers=headers)
    assert response.status_code == 401
    assert error_kind(response) == "not_authorised"
    assert (
        client.get(f"/api/drafts/{DRAFT_ID}/coach", headers=headers).status_code == 401
    )

    deck = client.post(
        f"/api/drafts/{DRAFT_ID}/deck", json=a_deck(world), headers=headers
    )
    if headers:
        # A wrong key is refused, not quietly treated as anonymous.
        assert deck.status_code == 401
    else:
        assert deck.status_code == 200
        assert deck.json()["summary"] is None
    assert world.coach.calls == 0
    assert world.saved.reviews == {}


def test_with_admin_off_even_a_key_is_refused(
    client: TestClient, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "admin_key", None)
    response = client.post(note_url(noted(client)[0]), headers=ADMIN)
    assert response.status_code == 401
    assert world.coach.calls == 0


# --------------------------------------------------------------------------
# Pick Notes
# --------------------------------------------------------------------------


def test_a_noted_pick_gets_a_note_written_once_and_stored(
    client: TestClient, world: World
) -> None:
    n = noted(client)[0]
    first = client.post(note_url(n), headers=ADMIN)
    assert first.status_code == 200
    body = first.json()
    assert body["note"].startswith("A note on P")
    assert body["stale"] is False
    assert body["stats_snapshot"] == world.inputs.stats_snapshot.isoformat()
    assert body["model"] == "claude-haiku-5-5"
    # An admin-key call belongs to no user, and names its draft.
    assert world.coach.user_ids == [None]
    assert world.coach.draft_keys == [f"17lands:{DRAFT_ID}"]

    again = client.post(note_url(n), headers=ADMIN)
    assert again.json() == body
    assert world.coach.calls == 1  # the stored note, not a second call


def test_a_note_from_older_statistics_is_tagged_not_rewritten(
    client: TestClient, world: World
) -> None:
    n = noted(client)[0]
    client.post(note_url(n), headers=ADMIN)
    new_stats(world)
    later = client.post(note_url(n), headers=ADMIN).json()
    assert later["stale"] is True
    assert world.coach.calls == 1


def test_a_pick_that_is_not_noted_gets_no_note(
    client: TestClient, world: World
) -> None:
    plain = next(n for n in range(1, 43) if n not in noted(client))
    response = client.post(note_url(plain), headers=ADMIN)
    assert response.status_code == 422
    assert error_kind(response) == "not_noted"
    for n in (0, 999):
        assert error_kind(client.post(note_url(n), headers=ADMIN)) == "invalid_input"
    assert world.coach.calls == 0


def test_a_note_for_a_draft_not_imported_is_a_404(client: TestClient) -> None:
    response = client.post(f"/api/drafts/{'0' * 32}/picks/1/note", headers=ADMIN)
    assert response.status_code == 404


def test_the_spending_cap_and_a_failed_note_are_errors_the_page_can_read(
    client: TestClient, world: World
) -> None:
    n = noted(client)[0]
    world.coach.fail = SpendingCapReached()
    capped = client.post(note_url(n), headers=ADMIN)
    assert capped.status_code == 503
    assert error_kind(capped) == "coach_retired"
    assert "retired for the day" in capped.json()["detail"]["message"]

    world.coach.fail = PickNoteFailed("no valid note after 2 tries")
    failed = client.post(note_url(n), headers=ADMIN)
    assert failed.status_code == 502
    assert error_kind(failed) == "prose_failed"
    # Nothing was stored, so the next request tries again.
    world.coach.fail = None
    assert client.post(note_url(n), headers=ADMIN).status_code == 200


# --------------------------------------------------------------------------
# The Draft Summary
# --------------------------------------------------------------------------


def test_an_anonymous_deck_is_rated_and_forgotten(
    client: TestClient, world: World
) -> None:
    response = client.post(f"/api/drafts/{DRAFT_ID}/deck", json=a_deck(world))
    assert response.status_code == 200
    body = response.json()
    assert body["ratings"]["rated"] is True
    assert body["summary"] is None and body["summary_unavailable"] is None
    assert world.coach.calls == 0
    assert world.saved.reviews == {}


def test_the_first_coached_deck_gets_a_summary_and_later_ones_only_ratings(
    client: TestClient, world: World
) -> None:
    deck_url = f"/api/drafts/{DRAFT_ID}/deck"
    first_deck = a_deck(world)
    first = client.post(deck_url, json=first_deck, headers=ADMIN).json()
    assert first["ratings"]["rated"] is True
    assert first["summary"]["lesson"] == "The lesson."
    assert first["summary"]["stale"] is False
    assert len(world.coach.summary_briefs) == 1
    # The brief is about this deck, and every number in it came from Python.
    assert "Deck" in world.coach.summary_briefs[0].text

    second_deck = a_deck(world, spells=22)
    second = client.post(deck_url, json=second_deck, headers=ADMIN).json()
    assert second["summary"] is None
    assert len(world.coach.summary_briefs) == 1

    stored = client.get(f"/api/drafts/{DRAFT_ID}/coach", headers=ADMIN).json()
    assert stored["summary"]["lesson"] == "The lesson."
    assert len(stored["reviewed_deck"]["cards"]) == 23
    assert len(stored["current_deck"]["cards"]) == 22


def test_a_failed_summary_still_rates_the_deck_and_the_next_deck_tries_again(
    client: TestClient, world: World
) -> None:
    deck_url = f"/api/drafts/{DRAFT_ID}/deck"
    world.coach.fail = SpendingCapReached()
    first = client.post(deck_url, json=a_deck(world), headers=ADMIN)
    assert first.status_code == 200
    body = first.json()
    assert body["ratings"]["rated"] is True
    assert body["summary"] is None
    assert body["summary_unavailable"]["kind"] == "coach_retired"
    stored = client.get(f"/api/drafts/{DRAFT_ID}/coach", headers=ADMIN).json()
    assert stored["reviewed_deck"] is None
    assert stored["current_deck"] is not None

    world.coach.fail = None
    second = client.post(deck_url, json=a_deck(world), headers=ADMIN).json()
    assert second["summary"] is not None


def test_the_coach_review_lists_notes_in_pick_order_and_tags_stale_ones(
    client: TestClient, world: World
) -> None:
    empty = client.get(f"/api/drafts/{DRAFT_ID}/coach", headers=ADMIN).json()
    assert empty == {
        "notes": [],
        "summary": None,
        "reviewed_deck": None,
        "current_deck": None,
    }

    picks = noted(client)
    for n in reversed(picks):
        client.post(note_url(n), headers=ADMIN)
    client.post(f"/api/drafts/{DRAFT_ID}/deck", json=a_deck(world), headers=ADMIN)
    new_stats(world)

    stored = client.get(f"/api/drafts/{DRAFT_ID}/coach", headers=ADMIN).json()
    order = [(n["pack_number"], n["pick_number"]) for n in stored["notes"]]
    assert order == sorted(order) and len(order) == len(picks)
    assert all(n["stale"] for n in stored["notes"])
    assert stored["summary"]["stale"] is True
    assert world.coach.calls == len(picks) + 1  # reading calls no Claude


# --------------------------------------------------------------------------
# The real coach: capped and recorded like any other call (ADR 0027 s3)
# --------------------------------------------------------------------------


def _coach(client: FakeClient, ledger: Ledger) -> ClaudeCoach:
    return ClaudeCoach(
        client,  # type: ignore[arg-type]  # the SDK's shape, faked
        ledger,
        cap=Decimal("5.00"),
        pick_note_prompt=load_prompt("pick_note.v1"),
        summary_prompt=load_prompt("draft_summary.v1"),
    )


def _p1p1_brief(analysis: DraftAnalysis, card_facts: dict[uuid.UUID, CardFacts]) -> Any:
    return pick_brief(
        analysis, card_facts, FitnessConfig(), pack_number=1, pick_number=1
    )


def test_an_admin_call_is_recorded_with_no_user(
    analysis: DraftAnalysis, card_facts: dict[uuid.UUID, CardFacts]
) -> None:
    fake, ledger = FakeClient(good()), Ledger()
    _coach(fake, ledger).pick_note(
        _p1p1_brief(analysis, card_facts), draft_key=f"17lands:{DRAFT_ID}", user_id=None
    )
    [row] = ledger.calls
    assert row.user_id is None
    assert row.draft_key == f"17lands:{DRAFT_ID}"
    assert row.status == "succeeded"


def test_the_spending_cap_stops_an_admin_call_before_it_is_made(
    analysis: DraftAnalysis, card_facts: dict[uuid.UUID, CardFacts]
) -> None:
    fake, ledger = FakeClient(good()), Ledger(spent="5.00")
    with pytest.raises(SpendingCapReached):
        _coach(fake, ledger).pick_note(
            _p1p1_brief(analysis, card_facts), draft_key="17lands:x", user_id=None
        )
    assert fake.requests == []
    assert ledger.calls == []
