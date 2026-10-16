"""Write the Draft Summary for a saved draft and a deck, with Claude Sonnet 5.5.

    uv run python scripts/write_draft_summary.py DRAFT DECK [--metadata META]
        [--model claude-haiku-5-5] [--dry-run]

DRAFT is a saved `DraftLog` (as in `tests/fixtures/drafts/`) or a 17Lands
draft payload with its event metadata as `--metadata` (as in
`tests/fixtures/seventeen_lands_draft/`), exactly as for
`write_pick_notes.py`. DECK is a deck file as in `tests/fixtures/decks/`:
JSON whose `deck` is the 40 card names, one per copy, basics included.

The draft is analysed and the deck rated against the database's format
inputs, and the summary is written from the brief, with the format's
Format Primer as the second cached block (ADR 0030). `--dry-run` prints the
primer and the brief and calls nothing. `--model` swaps in another model,
for comparison (ADR 0024 s4).

The call is recorded in `llm_calls` with no user (a CLI run), and the
daily spending cap applies. Needs `ANTHROPIC_API_KEY` in api/.env.
"""

import argparse
import json
from pathlib import Path

from sqlalchemy.orm import Session

from boostertutor.analysis.deck import deck_metrics
from boostertutor.analysis.deck_rating import rate_deck
from boostertutor.analysis.draft import analyze_draft
from boostertutor.briefing.primer import format_primer
from boostertutor.briefing.summary import summary_brief
from boostertutor.card_facts import analysis_cards, load_card_facts
from boostertutor.config import settings
from boostertutor.db import SessionLocal
from boostertutor.format_inputs import (
    load_deck_rating_model,
    load_format_inputs,
    name_index,
)
from boostertutor.format_primer import load_primer_facts
from boostertutor.llm.client import anthropic_client
from boostertutor.llm.draft_summary import (
    MODEL,
    PROMPT_VERSION,
    DraftSummaryFailed,
    load_prompt,
    write_draft_summary,
)
from boostertutor.llm.spending import DbLedger, SpendingCapReached
from boostertutor.models import LlmCall
from boostertutor.parsing import seventeen_lands
from boostertutor.schemas import DraftLog
from boostertutor.schemas.deck import deck_from_names, drafted_pool


class CountingLedger(DbLedger):
    """`llm_calls`, plus a tally of this run's calls for the summary line."""

    def __init__(self, session: Session) -> None:
        super().__init__(session)
        self.calls: list[LlmCall] = []

    def record(self, call: LlmCall) -> None:
        super().record(call)
        self.calls.append(call)


def load_log(session: Session, draft: Path, metadata: Path | None) -> DraftLog:
    payload = json.loads(draft.read_text())
    if metadata is None:
        return DraftLog.model_validate(payload)
    meta = json.loads(metadata.read_text())
    names = name_index(session, seventeen_lands.draft_set_code(meta))
    draft_id = meta.get("metadata", {}).get("id")
    return seventeen_lands.parse_draft(payload, meta, names, draft_id=draft_id)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("draft", type=Path)
    parser.add_argument("deck", type=Path, help="a deck file of 40 card names")
    parser.add_argument("--metadata", type=Path, help="17Lands event metadata")
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--dry-run", action="store_true", help="print the brief")
    args = parser.parse_args()

    with SessionLocal() as session:
        log = load_log(session, args.draft, args.metadata)
        inputs = load_format_inputs(session, log.set_code, log.event_type)
        analysis = analyze_draft(log, inputs)
        facts = load_card_facts(session, log.set_code, analysis_cards(analysis))
        names = json.loads(args.deck.read_text())["deck"]
        deck = deck_from_names(
            drafted_pool(analysis, facts),
            names,
            {f.name: oid for oid, f in facts.items()},
        )
        metrics = deck_metrics(deck, inputs)
        model = load_deck_rating_model(session, log.set_code, log.event_type)
        ratings = rate_deck(metrics, model)
        brief = summary_brief(analysis, deck, metrics, ratings, facts, inputs)
        primer = format_primer(load_primer_facts(session, log.set_code, log.event_type))

        if args.dry_run:
            print(f"{primer}\n-----\n{brief.text}")
            return

        ledger = CountingLedger(session)
        draft_key = f"{log.source}:{log.source_id}" if log.source_id else None
        try:
            summary = write_draft_summary(
                anthropic_client(),
                ledger,
                brief,
                prompt=load_prompt(PROMPT_VERSION),
                primer=primer,
                cap=settings.daily_spend_cap_usd,
                draft_key=draft_key,
                user_id=None,
                model=args.model,
            )
        except DraftSummaryFailed as exc:
            print(f"No summary. {exc}")
        except SpendingCapReached as exc:
            print(exc)
        else:
            keys = ", ".join(
                f"P{k.pack_number}p{k.pick_number}" for k in summary.key_picks
            )
            print(
                f"Draft arc\n{summary.draft_arc}\n\nDeck\n{summary.deck}\n\n"
                f"Lesson\n{summary.lesson}\n\nKey picks: {keys or 'none'}"
                f"\n(written by {summary.model})"
            )
        for call in ledger.calls:
            print(
                f"{call.status}: ${call.cost_usd}, {call.input_tokens:,} in, "
                f"{call.cache_read_tokens:,} cache read, {call.cache_write_tokens:,} "
                f"cache write, {call.output_tokens:,} out, {call.latency_ms:,} ms"
                + (f" ({call.error})" if call.error else "")
            )


if __name__ == "__main__":
    main()
