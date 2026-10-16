"""The Draft Summary eval harness (ADR 0030 s5).

The cases are the two decks Jackson built from the HOB golden draft
(hob.d9ac6765), in `tests/fixtures/decks/`: the deck he would have played,
and a deliberately flawed copy whose file names its flaw. A deck file is:

    {"draft": "hob.d9ac6765",
     "about": "what this deck is",
     "flaw": null, or {"what": "...", "named_by_any_of": ["...", ...]},
     "deck": [40 card names, one per copy, basics included]}

Two parts:

- **Offline**, in every test run: the cases are what they should be, and
  the prompt's own examples pass the checks a live summary must pass
  against the full briefs they were drafted from. That the cached blocks
  are byte-identical across drafts is tested in `test_draft_summary.py`.
- **Live**, only when asked: each case is sent to Claude, and the summary
  must validate as JSON, state no number its brief does not, keep each
  field within its cap, name Key Picks that exist, and, for the flawed
  deck, name its flaw. A few cents on Sonnet, and needs
  `ANTHROPIC_API_KEY` in api/.env:

      DRAFT_SUMMARY_EVAL=1 uv run pytest tests/test_draft_summary_eval.py -s

  `DRAFT_SUMMARY_MODEL=claude-haiku-5-5` runs the same eval on Haiku, for
  comparison (ADR 0024 s4). Summaries, with each call's tokens, cost and latency,
  are written to `data/evals/`. Calls are not recorded in `llm_calls`.
"""

import datetime as dt
import json
import os
import re
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from conftest import FIXTURES, _json, load_card_facts, load_deck_inputs, load_inputs
from eval_report import call_totals
from test_summary_brief import brief_for

from boostertutor.analysis.draft import analyze_draft
from boostertutor.briefing.card_facts import CardFacts
from boostertutor.briefing.primer import format_primer
from boostertutor.briefing.summary import SummaryBrief
from boostertutor.llm.checks import summary_problems
from boostertutor.llm.client import anthropic_client
from boostertutor.llm.draft_summary import (
    MODEL,
    PROMPT_VERSION,
    DraftSummaryOutput,
    load_prompt,
    write_draft_summary,
)
from boostertutor.models import LlmCall
from boostertutor.parsing import seventeen_lands as sl
from boostertutor.schemas.draft_analysis import DraftAnalysis

LIVE = bool(os.environ.get("DRAFT_SUMMARY_EVAL"))
EVAL_MODEL = os.environ.get("DRAFT_SUMMARY_MODEL", MODEL)
REPORTS = Path(__file__).resolve().parents[1] / "data" / "evals"
DECKS = FIXTURES / "decks"
EVAL_DRAFT = "hob.d9ac6765"
PROMPT = load_prompt(PROMPT_VERSION)
PRIMER = format_primer(load_deck_inputs()[2])


def deck_file(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def flaw_named(text: str, flaw: dict[str, Any]) -> bool:
    """Whether the summary names the deck's flaw, by any of its file's terms."""
    return any(term.lower() in text.lower() for term in flaw["named_by_any_of"])


def golden_analysis() -> DraftAnalysis:
    names = load_inputs()[1]
    log = sl.parse_draft(
        _json(FIXTURES / "seventeen_lands_draft" / "draft.json"),
        _json(FIXTURES / "seventeen_lands_draft" / "event_metadata.json"),
        names,
    )
    return analyze_draft(log, load_deck_inputs()[0])


def eval_cases() -> list[tuple[str, dict[str, Any], SummaryBrief]]:
    """(case id, deck file, brief) for each of the golden draft's deck files."""
    analysis, facts = golden_analysis(), load_card_facts()
    return [
        (
            path.stem,
            deck_file(path),
            brief_for(analysis, facts, deck_file(path)["deck"]),
        )
        for path in sorted(DECKS.glob(f"{EVAL_DRAFT}.*.json"))
    ]


CASES = eval_cases()


# --------------------------------------------------------------------------
# Offline
# --------------------------------------------------------------------------


def test_the_eval_has_a_played_deck_and_a_flawed_copy() -> None:
    assert len(CASES) == 2, f"expected two deck files for {EVAL_DRAFT} in {DECKS}"
    flaws = [deck["flaw"] for _, deck, _ in CASES]
    assert sum(f is None for f in flaws) == 1
    (flaw,) = [f for f in flaws if f is not None]
    assert flaw["what"] and flaw["named_by_any_of"]


def prompt_examples() -> list[DraftSummaryOutput]:
    return [
        DraftSummaryOutput.model_validate_json(line)
        for line in re.findall(r'^(\{"draft_arc".*\})$', PROMPT.text, re.MULTILINE)
    ]


def test_the_prompt_has_two_examples_with_one_deck_file_each() -> None:
    assert len(prompt_examples()) == 2
    files = sorted(DECKS.glob("hob.5d9123f8.example*.json"))
    assert [f.name for f in files] == [
        "hob.5d9123f8.example1.json",
        "hob.5d9123f8.example2.json",
    ]


def test_the_prompt_s_examples_obey_its_own_rules(
    examples_analysis: DraftAnalysis, card_facts: dict[uuid.UUID, CardFacts]
) -> None:
    """Each example, against the full brief of the deck it was drafted from."""
    for n, example in enumerate(prompt_examples(), start=1):
        deck = deck_file(DECKS / f"hob.5d9123f8.example{n}.json")
        brief = brief_for(examples_analysis, card_facts, deck["deck"])
        assert summary_problems(example, brief.text, brief.picks) == [], n
        if deck["flaw"] is not None:
            assert flaw_named(example.deck, deck["flaw"]), n


# --------------------------------------------------------------------------
# Live: calls Claude, so only with DRAFT_SUMMARY_EVAL=1
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
REPORT = (
    REPORTS
    / f"{PROMPT_VERSION}.{EVAL_MODEL}.{dt.datetime.now(dt.UTC):%Y%m%dT%H%M%SZ}.jsonl"
)
live = pytest.mark.skipif(not LIVE, reason="set DRAFT_SUMMARY_EVAL=1 to call Claude")


@live
@pytest.mark.parametrize(("case", "deck", "brief"), CASES, ids=[c for c, _, _ in CASES])
def test_claude_writes_a_valid_summary(
    case: str, deck: dict[str, Any], brief: SummaryBrief
) -> None:
    before = len(LEDGER.calls)
    summary = write_draft_summary(
        anthropic_client(),
        LEDGER,
        brief,
        prompt=PROMPT,
        primer=PRIMER,
        cap=Decimal("1.00"),  # the whole eval costs a few cents
        draft_key=None,
        user_id=None,
        model=EVAL_MODEL,
    )
    calls = LEDGER.calls[before:]
    REPORTS.mkdir(parents=True, exist_ok=True)
    with REPORT.open("a") as report:
        report.write(
            json.dumps(
                {
                    "case": case,
                    "model": summary.model,
                    "draft_arc": summary.draft_arc,
                    "deck": summary.deck,
                    "lesson": summary.lesson,
                    "key_picks": [k.model_dump() for k in summary.key_picks],
                    "words": {
                        f: len(getattr(summary, f).split())
                        for f in ("draft_arc", "deck", "lesson")
                    },
                    **call_totals(calls),
                },
                ensure_ascii=False,
            )
            + "\n"
        )
    # write_draft_summary already refuses a summary that fails these;
    # asserting them again keeps the harness honest if that code changes.
    assert summary_problems(summary, brief.text, brief.picks) == []
    if deck["flaw"] is not None:
        assert flaw_named(summary.deck, deck["flaw"]), deck["flaw"]["what"]


@live
def test_the_cached_blocks_are_read_from_the_cache() -> None:
    """After the first call writes them, the next reads them (ADR 0024 s6)."""
    assert LEDGER.calls, "run the whole file, not this test alone"
    assert sum(c.cache_read_tokens for c in LEDGER.calls[1:]) > 0
    spent = sum((c.cost_usd for c in LEDGER.calls), Decimal(0))
    print(
        f"\n{len(LEDGER.calls)} calls on {EVAL_MODEL}, ${spent}, "
        f"{sum(c.status != 'succeeded' for c in LEDGER.calls)} retried; "
        f"summaries in {REPORT}"
    )
