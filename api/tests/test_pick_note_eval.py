"""The Pick Note eval harness (ADR 0024 s9; development plan, Phase 4a).

The cases are every Noted Pick of the saved HOB draft and of the public-
dataset draft `hob.9f353fcb`. Two parts:

- **Offline**, in every test run: the cases are what they should be, and
  the prompt's own few-shot examples pass the checks a live note must pass,
  so a rewrite of them cannot quietly teach Claude to break the rules. That
  the cached block is byte-identical across drafts is tested in
  `test_pick_note.py`.
- **Live**, only when asked: each case is sent to Claude Haiku 5.5, and the
  note must validate as JSON, use no number missing from its brief, and
  stay under the length cap. It costs well under a cent, and needs
  `ANTHROPIC_API_KEY` in api/.env:

      PICK_NOTE_EVAL=1 uv run pytest tests/test_pick_note_eval.py -s

  The notes, with each call's tokens and cost, are written to
  `data/evals/` for reading. Calls are not recorded in `llm_calls`: the
  eval keeps its own ledger, so it runs without a database.
"""

import datetime as dt
import json
import os
import re
import uuid
from decimal import Decimal
from pathlib import Path

import pytest

# The tests directory is on sys.path (pytest's default import mode), so the
# fixtures' loaders can be shared rather than copied.
from conftest import FIXTURES, _json, load_card_facts, load_inputs, load_public_draft

from boostertutor.analysis.draft import analyze_draft
from boostertutor.analysis.fitness import FitnessConfig
from boostertutor.briefing import PickBrief, noted_pick_briefs, pick_brief
from boostertutor.briefing.card_facts import CardFacts
from boostertutor.llm.checks import MAX_NOTE_CHARS, invented_numbers, note_problems
from boostertutor.llm.client import anthropic_client
from boostertutor.llm.pick_note import (
    PROMPT_VERSION,
    PickNoteOutput,
    load_prompt,
    write_pick_note,
)
from boostertutor.models import LlmCall
from boostertutor.parsing import seventeen_lands as sl
from boostertutor.schemas.draft_analysis import DraftAnalysis

LIVE = bool(os.environ.get("PICK_NOTE_EVAL"))
REPORTS = Path(__file__).resolve().parents[1] / "data" / "evals"
PROMPT = load_prompt(PROMPT_VERSION)
CFG = FitnessConfig()


def eval_cases() -> list[tuple[str, PickBrief]]:
    """(case id, brief) for every Noted Pick in the two eval drafts."""
    inputs, names = load_inputs()
    facts = load_card_facts()
    saved = sl.parse_draft(
        _json(FIXTURES / "seventeen_lands_draft" / "draft.json"),
        _json(FIXTURES / "seventeen_lands_draft" / "event_metadata.json"),
        names,
    )
    drafts = {"hob.d9ac6765": saved, "hob.9f353fcb": load_public_draft("hob.9f353fcb")}
    return [
        (f"{name}/P{b.pack_number}p{b.pick_number}", b)
        for name, log in drafts.items()
        for b in noted_pick_briefs(analyze_draft(log, inputs), facts, inputs.cfg)
    ]


CASES = eval_cases()


# --------------------------------------------------------------------------
# Offline
# --------------------------------------------------------------------------


def test_the_eval_covers_both_drafts_and_both_kinds_of_note() -> None:
    ids = [case for case, _ in CASES]
    assert ids[:3] == ["hob.d9ac6765/P1p1", "hob.d9ac6765/P1p12", "hob.d9ac6765/P2p7"]
    assert len(ids) == 20  # 3 from the saved draft, 17 from the public one
    assert {b.kind for _, b in CASES} == {"critical", "narrow"}


def prompt_examples() -> list[PickNoteOutput]:
    return [
        PickNoteOutput.model_validate_json(line)
        for line in re.findall(r'^(\{"pack_number".*\})$', PROMPT.text, re.MULTILINE)
    ]


def test_the_prompt_has_three_examples_and_one_is_narrow(
    examples_analysis: DraftAnalysis,
) -> None:
    examples = prompt_examples()
    assert len(examples) == 3
    picks = {(p.pack_number, p.pick_number): p for p in examples_analysis.picks}
    assert any(picks[(e.pack_number, e.pick_number)].narrow for e in examples)


def test_the_prompt_s_examples_obey_its_own_rules(
    examples_analysis: DraftAnalysis, card_facts: dict[uuid.UUID, CardFacts]
) -> None:
    """Each example, against the full brief of the real pick it was drafted from."""
    for example in prompt_examples():
        pick = (example.pack_number, example.pick_number)
        brief = pick_brief(
            examples_analysis,
            card_facts,
            CFG,
            pack_number=pick[0],
            pick_number=pick[1],
        )
        assert note_problems(example, brief.text, pick) == [], pick


# --------------------------------------------------------------------------
# Live: calls Claude, so only with PICK_NOTE_EVAL=1
# --------------------------------------------------------------------------


class EvalLedger:
    """Remembers this run's calls; nothing is written to a database."""

    def __init__(self) -> None:
        self.calls: list[LlmCall] = []

    def spent_today(self) -> Decimal:
        return sum((c.cost_usd for c in self.calls), Decimal(0))

    def record(self, call: LlmCall) -> None:
        self.calls.append(call)


LEDGER = EvalLedger()
REPORT = REPORTS / f"{PROMPT_VERSION}.{dt.datetime.now(dt.UTC):%Y%m%dT%H%M%SZ}.jsonl"
live = pytest.mark.skipif(not LIVE, reason="set PICK_NOTE_EVAL=1 to call Claude")


@live
@pytest.mark.parametrize(("case", "brief"), CASES, ids=[c for c, _ in CASES])
def test_claude_writes_a_valid_note(case: str, brief: PickBrief) -> None:
    before = len(LEDGER.calls)
    note = write_pick_note(
        anthropic_client(),
        LEDGER,
        brief,
        prompt=PROMPT,
        cap=Decimal("0.50"),  # the whole eval costs well under a cent
        draft_key=None,
        user_id=None,
    )
    calls = LEDGER.calls[before:]
    REPORTS.mkdir(parents=True, exist_ok=True)
    with REPORT.open("a") as report:
        report.write(
            json.dumps(
                {
                    "case": case,
                    "kind": brief.kind,
                    "note": note.note,
                    "attempts": [c.status for c in calls],
                    "errors": [c.error for c in calls if c.error],
                    "cost_usd": str(sum((c.cost_usd for c in calls), Decimal(0))),
                    "cache_read_tokens": sum(c.cache_read_tokens for c in calls),
                    "cache_write_tokens": sum(c.cache_write_tokens for c in calls),
                }
            )
            + "\n"
        )
    # write_pick_note already refuses a note that fails these; asserting
    # them again keeps the harness honest if that code changes.
    assert invented_numbers(note.note, brief.text) == []
    assert len(note.note) <= MAX_NOTE_CHARS


@live
def test_the_cached_block_is_read_from_the_cache() -> None:
    """After the first call writes it, later calls read it (ADR 0024 s6)."""
    assert LEDGER.calls, "run the whole file, not this test alone"
    assert sum(c.cache_read_tokens for c in LEDGER.calls[1:]) > 0
    spent = sum((c.cost_usd for c in LEDGER.calls), Decimal(0))
    print(
        f"\n{len(LEDGER.calls)} calls, ${spent}, "
        f"{sum(c.status != 'succeeded' for c in LEDGER.calls)} retried; "
        f"notes in {REPORT}"
    )
