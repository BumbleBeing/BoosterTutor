"""Fixtures shared by the analysis tests: the real HOB draft and its inputs.

The draft is the saved HOB Premier Draft from `test_seventeen_lands_draft.py`.
Its inputs are a snapshot of HOB's real data (win rates, ALSA, tags, synergy
baseline, format constants), trimmed to the draft's cards by
`scripts/snapshot_format_inputs.py`, so no database is needed.

Two more HOB drafts come from the 17Lands public dataset
(`scripts/snapshot_public_drafts.py`): `hob.9f353fcb` is the Pick Note
eval's second draft, and `hob.5d9123f8` is where the prompt's few-shot
examples were drafted from, so the eval never grades a pick an example
already answers. Both have Narrow Picks, which the saved draft does not.
"""

import json
import uuid
from pathlib import Path
from typing import Any

import pytest

from boostertutor.analysis import fitness as fx
from boostertutor.analysis.draft import FormatInputs, analyze_draft
from boostertutor.briefing.card_facts import CardFacts
from boostertutor.parsing import seventeen_lands as sl
from boostertutor.schemas import DraftLog
from boostertutor.schemas.draft_analysis import DraftAnalysis

FIXTURES = Path(__file__).parent / "fixtures"
INPUTS = FIXTURES / "format_inputs" / "hob.PremierDraft.json"
CARD_FACTS = FIXTURES / "card_facts" / "hob.json"
EVAL_DRAFT = "hob.9f353fcb"  # the eval's second draft
EXAMPLES_DRAFT = "hob.5d9123f8"  # the few-shot examples' draft


def _json(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text())
    return data


def load_inputs() -> tuple[FormatInputs, dict[str, uuid.UUID]]:
    """The snapshot back into a `FormatInputs`, and its name index."""
    raw = _json(INPUTS)
    cfg = dict(raw["cfg"])
    cfg["target_curve"] = {int(k): v for k, v in cfg["target_curve"].items()}
    inputs = FormatInputs(
        set_code=raw["set_code"],
        event_type=raw["event_type"],
        stats_snapshot=raw["stats_snapshot"],
        cards={
            uuid.UUID(oid): {**card, "oracle_id": uuid.UUID(oid)}
            for oid, card in raw["cards"].items()
        },
        stats=fx.Stats(
            format_avg_wr=raw["format_avg_wr"],
            overall={
                uuid.UUID(k): (wr, games) for k, (wr, games) in raw["overall"].items()
            },
        ),
        edges=raw["edges"],
        baseline={
            (uuid.UUID(oid), pack, enabler, payoff, on_card): expected
            for oid, pack, enabler, payoff, on_card, expected in raw["baseline"]
        },
        alsa={uuid.UUID(k): v for k, v in raw["alsa"].items()},
        cfg=fx.FitnessConfig(**cfg),
    )
    return inputs, {k: uuid.UUID(v) for k, v in raw["names"].items()}


@pytest.fixture(scope="module")
def inputs() -> FormatInputs:
    return load_inputs()[0]


@pytest.fixture(scope="module")
def names() -> dict[str, uuid.UUID]:
    return load_inputs()[1]


@pytest.fixture(scope="module")
def log(names: dict[str, uuid.UUID]) -> DraftLog:
    draft = _json(FIXTURES / "seventeen_lands_draft" / "draft.json")
    metadata = _json(FIXTURES / "seventeen_lands_draft" / "event_metadata.json")
    return sl.parse_draft(draft, metadata, names)


@pytest.fixture(scope="module")
def analysis(log: DraftLog, inputs: FormatInputs) -> DraftAnalysis:
    return analyze_draft(log, inputs)


def load_card_facts() -> dict[uuid.UUID, CardFacts]:
    return {
        uuid.UUID(oid): CardFacts(**facts) for oid, facts in _json(CARD_FACTS).items()
    }


def load_public_draft(name: str) -> DraftLog:
    path = FIXTURES / "drafts" / f"{name}.draft_log.json"
    return DraftLog.model_validate_json(path.read_text())


@pytest.fixture(scope="module")
def card_facts() -> dict[uuid.UUID, CardFacts]:
    return load_card_facts()


@pytest.fixture(scope="module")
def eval_analysis(inputs: FormatInputs) -> DraftAnalysis:
    return analyze_draft(load_public_draft(EVAL_DRAFT), inputs)


@pytest.fixture(scope="module")
def examples_analysis(inputs: FormatInputs) -> DraftAnalysis:
    return analyze_draft(load_public_draft(EXAMPLES_DRAFT), inputs)
