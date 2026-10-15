"""A 17Lands draft link into a `DraftLog` (development plan 3.1 and 3.5).

The fixture is a real HOB Premier Draft (3-3), fetched once on 2026-10-14
and trimmed to the pick structure: 17Lands' own statistics and advice in the
payload are removed, since ADR 0002 rules them out and the parser never
reads them.
"""

import copy
import json
import uuid
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from boostertutor import drafts
from boostertutor.ingest.fetching import FetchError, HTTPStatusError
from boostertutor.parsing import seventeen_lands as sl
from boostertutor.parsing.errors import DraftInputError
from boostertutor.parsing.names import name_key
from boostertutor.schemas import DraftLog, Pick

FIXTURES = Path(__file__).parent / "fixtures" / "seventeen_lands_draft"
DRAFT_ID = "d9ac6765edeb499fb4084e4d018f8cee"


def _load(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((FIXTURES / f"{name}.json").read_text())
    return data


def oracle(name: str) -> uuid.UUID:
    """A stable stand-in oracle id per card name, so no database is needed."""
    return uuid.uuid5(uuid.NAMESPACE_URL, name_key(name))


def _names(draft: dict[str, Any]) -> dict[str, uuid.UUID]:
    every = {c["name"] for p in draft["picks"] for c in [p["pick"], *p["available"]]}
    return {name_key(n): oracle(n) for n in every}


@pytest.fixture
def draft() -> dict[str, Any]:
    return _load("draft")


@pytest.fixture
def metadata() -> dict[str, Any]:
    return _load("event_metadata")


def _parse(draft: dict[str, Any], metadata: dict[str, Any]) -> DraftLog:
    return sl.parse_draft(draft, metadata, _names(draft), draft_id=DRAFT_ID)


# --------------------------------------------------------------------------
# The draft id
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        DRAFT_ID,
        f"  {DRAFT_ID.upper()}\n",
        f"https://www.17lands.com/draft/{DRAFT_ID}",
        f"https://www.17lands.com/draft/{DRAFT_ID}/1/1",
        f"17lands.com/draft/{DRAFT_ID}?tab=picks",
    ],
)
def test_the_draft_id_is_found_in_whatever_was_pasted(text: str) -> None:
    assert sl.parse_draft_id(text) == DRAFT_ID


@pytest.mark.parametrize("text", ["", "https://www.17lands.com/", "d9ac6765"])
def test_text_without_a_draft_id_is_invalid_input(text: str) -> None:
    with pytest.raises(DraftInputError) as err:
        sl.parse_draft_id(text)
    assert err.value.kind == "invalid_input"


# --------------------------------------------------------------------------
# The real draft
# --------------------------------------------------------------------------


def test_a_real_draft_parses_into_three_packs_of_fourteen(
    draft: dict[str, Any], metadata: dict[str, Any]
) -> None:
    log = _parse(draft, metadata)
    assert (log.set_code, log.event_type, log.source, log.source_id) == (
        "hob",
        "PremierDraft",
        "17lands",
        DRAFT_ID,
    )
    assert (log.wins, log.losses) == (3, 3)
    assert len(log.picks) == 42
    assert log.pack_size == 14  # read from the log, not assumed
    first = log.picks[0]
    assert (first.pack_number, first.pick_number) == (1, 1)
    assert first.picked == oracle("Dwarven Mauler")
    assert (log.picks[-1].pack_number, log.picks[-1].pick_number) == (3, 14)


def test_every_pick_holds_the_properties_of_a_draft(
    draft: dict[str, Any], metadata: dict[str, Any]
) -> None:
    """Development plan 3.5's property tests, on real data.

    The picked card is in its own pack, the pack shrinks by one card a pick,
    and the pool grows by exactly the card taken.
    """
    log = _parse(draft, metadata)
    for i, pick in enumerate(log.picks):
        assert pick.picked in pick.pack_cards
        assert len(pick.pack_cards) == log.pack_size - (pick.pick_number - 1)
        assert pick.pool_before == [p.picked for p in log.picks[:i]]


def test_the_ninth_pick_is_the_first_pack_coming_back(
    draft: dict[str, Any], metadata: dict[str, Any]
) -> None:
    """Eight drafters: pick 9 is the pick-1 pack, eight cards lighter.

    Worked out by hand from the payload. The eight cards that did not come
    back are this drafter's own pick (Dwarven Mauler) and seven taken by the
    other drafters, the same seven 17Lands lists as missing at that pick.
    What comes back (the wheel) is what wheel analysis will read.
    """
    log = _parse(draft, metadata)
    p1, p9 = log.picks[0], log.picks[8]
    assert set(p9.pack_cards) <= set(p1.pack_cards)
    assert set(p9.pack_cards) == {
        oracle(n)
        for n in (
            "Elven Raft-Steerer",
            "Front Porch Sentries",
            "Ordinary Bear",
            "Old Thrush",
            "Goblin-town",
            "Hobbit Hole",
        )
    }
    assert oracle("Dwarven Mauler") not in p9.pack_cards


def test_picks_are_put_in_order_whatever_order_they_arrive_in(
    draft: dict[str, Any], metadata: dict[str, Any]
) -> None:
    shuffled = copy.deepcopy(draft)
    shuffled["picks"].reverse()
    assert _parse(shuffled, metadata) == _parse(draft, metadata)


def test_17lands_own_statistics_are_ignored(
    draft: dict[str, Any], metadata: dict[str, Any]
) -> None:
    """The live payload carries 17Lands' site statistics. They change nothing."""
    with_stats = copy.deepcopy(draft)
    with_stats["card_performance_data"] = {
        "Dwarven Mauler": {"game_in_hand_win_rate": 0.6}
    }
    for entry in with_stats["picks"]:
        entry["suggested_pick"] = {"name": "Large Bear"}
        entry["sections"] = []
    assert _parse(with_stats, metadata) == _parse(draft, metadata)


def test_a_double_faced_card_matches_by_its_front_face(
    draft: dict[str, Any], metadata: dict[str, Any]
) -> None:
    """17Lands writes "Bilbo Baggins, Burglar"; Scryfall "A // B" (here, invented)."""
    names = _names(draft)
    names[name_key("Bilbo Baggins, Burglar // Some Back Face")] = oracle("Bilbo")
    log = sl.parse_draft(draft, metadata, names)
    assert any(oracle("Bilbo") in p.pack_cards for p in log.picks)


# --------------------------------------------------------------------------
# Failures, each with a kind the UI can explain
# --------------------------------------------------------------------------


def _kind(draft: dict[str, Any], metadata: dict[str, Any], names: Any = None) -> str:
    with pytest.raises(DraftInputError) as err:
        sl.parse_draft(draft, metadata, _names(draft) if names is None else names)
    return err.value.kind


def test_a_set_we_have_no_cards_for_is_unsupported(
    draft: dict[str, Any], metadata: dict[str, Any]
) -> None:
    assert _kind(draft, metadata, names={}) == "unsupported_set"


def test_every_unknown_name_is_reported_at_once(
    draft: dict[str, Any], metadata: dict[str, Any]
) -> None:
    names = _names(draft)
    del names[name_key("Large Bear")], names[name_key("Troop of Ponies")]
    with pytest.raises(DraftInputError) as err:
        sl.parse_draft(draft, metadata, names)
    assert err.value.kind == "unresolved_cards"
    assert err.value.detail == ["Large Bear", "Troop of Ponies"]


def test_an_unfinished_draft_is_malformed(
    draft: dict[str, Any], metadata: dict[str, Any]
) -> None:
    unfinished = copy.deepcopy(draft)
    unfinished["picks"] = unfinished["picks"][:30]  # stopped at P3p2
    assert _kind(unfinished, metadata) == "malformed_draft"


def test_two_cards_a_pick_is_an_unsupported_format(
    draft: dict[str, Any], metadata: dict[str, Any]
) -> None:
    pick_two = copy.deepcopy(draft)
    first = pick_two["picks"][0]
    first["picks"] = [first["pick"], first["available"][0]]
    assert _kind(pick_two, metadata) == "unsupported_format"


def test_a_payload_in_another_shape_is_an_upstream_failure(
    draft: dict[str, Any], metadata: dict[str, Any]
) -> None:
    assert _kind({"picks": [{"pack": 0}]}, metadata, names=_names(draft)) == (
        "upstream_failure"
    )
    assert _kind({}, metadata, names=_names(draft)) == "upstream_failure"
    assert _kind(draft, {"metadata": {}}) == "upstream_failure"


# --------------------------------------------------------------------------
# The canonical model's own checks, which every future parser inherits
# --------------------------------------------------------------------------

A, B, C = (uuid.UUID(int=i) for i in (1, 2, 3))


def _log(picks: list[Pick]) -> DraftLog:
    return DraftLog(
        set_code="hob",
        event_type="PremierDraft",
        drafted_at=None,
        source="arena",
        picks=picks,
    )


def _one_card_packs() -> list[Pick]:
    """The smallest valid draft: three packs of one card each."""
    return [
        Pick(
            pack_number=n,
            pick_number=1,
            pack_cards=[c],
            picked=c,
            pool_before=list(pool),
        )
        for n, c, pool in ((1, A, []), (2, B, [A]), (3, C, [A, B]))
    ]


def test_the_smallest_draft_is_valid() -> None:
    assert _log(_one_card_packs()).pack_size == 1


def test_the_model_rejects_a_pick_not_in_its_pack() -> None:
    picks = _one_card_packs()
    picks[1] = picks[1].model_copy(update={"pack_cards": [C]})
    with pytest.raises(ValidationError, match="not in the pack"):
        _log(picks)


def test_the_model_rejects_a_pool_that_is_not_the_picks_so_far() -> None:
    picks = _one_card_packs()
    picks[2] = picks[2].model_copy(update={"pool_before": [A]})
    with pytest.raises(ValidationError, match="pool_before"):
        _log(picks)


def test_the_model_rejects_zero_indexed_picks() -> None:
    picks = [p.model_copy(update={"pick_number": 0}) for p in _one_card_packs()]
    with pytest.raises(ValidationError, match="expected P1p1"):
        _log(picks)


# --------------------------------------------------------------------------
# The fetch's failures (no network: `fetch_json_bytes` is replaced)
# --------------------------------------------------------------------------


def _fetch_raising(monkeypatch: pytest.MonkeyPatch, result: Any) -> str:
    def fake(url: str, **_: Any) -> bytes:
        if isinstance(result, Exception):
            raise result
        return bytes(result)

    monkeypatch.setattr(drafts, "fetch_json_bytes", fake)
    with pytest.raises(DraftInputError) as err:
        drafts.fetch_seventeen_lands_draft(DRAFT_ID)
    return err.value.kind


def test_a_404_means_the_draft_is_private_or_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = b'{"message": "We can\'t seem to find that draft...", "status": "error"}'
    error = HTTPStatusError("https://www.17lands.com/data/x", 404, body)
    assert _fetch_raising(monkeypatch, error) == "draft_not_found"


def test_other_failures_are_upstream_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    assert (
        _fetch_raising(monkeypatch, HTTPStatusError("u", 429, b""))
        == "upstream_failure"
    )
    assert _fetch_raising(monkeypatch, FetchError("timed out")) == "upstream_failure"
    assert _fetch_raising(monkeypatch, b"<html>busy</html>") == "upstream_failure"
    assert _fetch_raising(monkeypatch, b"[1, 2]") == "upstream_failure"
