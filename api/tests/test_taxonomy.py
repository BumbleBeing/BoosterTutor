"""Loading the hand-authored tag taxonomy (ingest/taxonomy.py, models/tags.py)."""

import copy
import json
import uuid
from typing import Any

import pytest

from boostertutor.config import settings
from boostertutor.ingest import taxonomy as tx
from boostertutor.models import Base
from boostertutor.parsing.names import name_key


def oracle(name: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, name_key(name))


def _names(*cards: str) -> dict[str, uuid.UUID]:
    return {name_key(c): oracle(c) for c in cards}


def payload(**changes: Any) -> dict[str, Any]:
    """A small valid taxonomy: one ordinary edge and one self-payoff."""
    base: dict[str, Any] = {
        "format_version": 1,
        "set_code": "hob",
        "tags": [
            {"name": "artifact", "kind": "enabler", "notes": None},
            {"name": "artifact_payoff", "kind": "payoff", "notes": None},
            {"name": "seven_dwarves", "kind": "self_payoff", "notes": None},
        ],
        "tag_pairs": [
            {
                "enabler": "artifact",
                "payoff": "artifact_payoff",
                "coefficient": 0.3,
                "decay": 0.5,
                "notes": None,
            },
            {
                "enabler": "seven_dwarves",
                "payoff": "seven_dwarves",
                "coefficient": 0.5,
                "decay": 1.0,
                "notes": None,
            },
        ],
        "card_tags": {
            "Thrór's Map": ["artifact"],
            "Front Face // Back Face": ["artifact_payoff", "artifact"],
            "Seven Dwarves": ["seven_dwarves"],
        },
    }
    base.update(changes)
    return base


NAMES = _names("Thrór's Map", "Front Face // Back Face", "Seven Dwarves")


def _problems(p: dict[str, Any], names: dict[str, uuid.UUID] = NAMES) -> list[str]:
    with pytest.raises(tx.TaxonomyError) as err:
        tx.rows_for(p, names)
    return err.value.problems


def test_a_valid_taxonomy_becomes_rows() -> None:
    rows = tx.rows_for(payload(), NAMES)
    assert [t["name"] for t in rows["tags"]] == [
        "artifact",
        "artifact_payoff",
        "seven_dwarves",
    ]
    assert len(rows["tag_pairs"]) == 2
    assert {(r["oracle_id"], r["tag"]) for r in rows["card_tags"]} == {
        (oracle("Thrór's Map"), "artifact"),
        (oracle("Front Face"), "artifact_payoff"),  # matched by its front face
        (oracle("Front Face"), "artifact"),
        (oracle("Seven Dwarves"), "seven_dwarves"),
    }


def test_a_pair_without_decay_takes_the_default() -> None:
    p = payload()
    del p["tag_pairs"][0]["decay"]
    assert tx.rows_for(p, NAMES)["tag_pairs"][0]["decay"] == 0.5


def test_every_problem_is_reported_at_once() -> None:
    p = payload()
    p["tags"].append({"name": "odd", "kind": "sideways", "notes": None})
    p["tag_pairs"].append(
        {"enabler": "artifact", "payoff": "missing", "coefficient": 1.0, "decay": 2.0}
    )
    p["card_tags"]["Nobody Knows Me"] = ["artifact"]
    p["card_tags"]["Thrór's Map"] = ["no_such_tag"]
    assert _problems(p) == [
        "tag 'odd' has unknown kind 'sideways'",
        "pair artifact -> missing: no tag named 'missing'",
        "pair artifact -> missing: decay must be between 0 and 1",
        "card \"Thrór's Map\": no tag named 'no_such_tag'",
        "card 'Nobody Knows Me' is not in hob's card list",
    ]


def test_only_a_self_payoff_tag_sits_on_the_diagonal() -> None:
    p = payload()
    p["tag_pairs"].append(
        {"enabler": "artifact", "payoff": "artifact", "coefficient": 1.0, "decay": 0.5}
    )
    assert _problems(p) == [
        "pair artifact -> artifact: only a self_payoff tag may pair with itself"
    ]


def test_a_self_payoff_tag_sits_nowhere_else() -> None:
    p = payload()
    p["tag_pairs"].append(
        {
            "enabler": "artifact",
            "payoff": "seven_dwarves",
            "coefficient": 1.0,
            "decay": 0.5,
        }
    )
    assert _problems(p) == [
        "pair artifact -> seven_dwarves: a self_payoff tag pairs only with itself"
    ]


def test_a_file_in_another_layout_is_refused() -> None:
    assert _problems(payload(format_version=2)) == ["format_version is 2, expected 1"]


def test_the_committed_hob_taxonomy_is_valid() -> None:
    """The real file passes every check, given every card name it uses.

    Whether those names are all HOB cards is checked against the database
    when it loads; here every name is assumed known.
    """
    real = json.loads(tx.taxonomy_path("hob").read_text())
    rows = tx.rows_for(real, _names(*real["card_tags"]))
    assert (len(rows["tags"]), len(rows["tag_pairs"])) == (30, 16)
    assert len({r["oracle_id"] for r in rows["card_tags"]}) == 153
    assert "hob" in tx.available_sets()
    assert tx.taxonomy_path("hob").parent == settings.taxonomy_dir


def test_rows_for_does_not_change_its_input() -> None:
    p = payload()
    before = copy.deepcopy(p)
    tx.rows_for(p, NAMES)
    assert p == before


def test_tag_pairs_foreign_keys_have_distinct_names() -> None:
    """The naming convention reads only the first column, so both keys would
    have been `fk_tag_pairs_set_code_tags`, and Postgres refuses a duplicate."""
    names = [
        fk.name for fk in Base.metadata.tables["tag_pairs"].foreign_key_constraints
    ]
    assert sorted(str(n) for n in names) == [
        "fk_tag_pairs_enabler_tags",
        "fk_tag_pairs_payoff_tags",
    ]
