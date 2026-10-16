"""Write the Pick Notes for a saved draft, with Claude Haiku 5.5.

    uv run python scripts/write_pick_notes.py DRAFT [--metadata META] [--pick P1p12] [--dry-run]

DRAFT is either a saved `DraftLog` (as in `tests/fixtures/drafts/`) or a
17Lands draft payload, with its event metadata as `--metadata` (as in
`tests/fixtures/seventeen_lands_draft/`). The draft is analysed against the
database's format inputs, and every Noted Pick gets a note. `--pick` limits
it to some picks; `--dry-run` prints the briefs and calls nothing.

Every call is recorded in `llm_calls` with no user (a CLI run), and the
daily spending cap applies. Needs `ANTHROPIC_API_KEY` in api/.env and the
`llm_calls` migration applied (`uv run alembic upgrade head`).
"""

import argparse
import json
from decimal import Decimal
from pathlib import Path

from sqlalchemy.orm import Session

from boostertutor.analysis.draft import analyze_draft
from boostertutor.briefing import noted_pick_briefs
from boostertutor.card_facts import analysis_cards, load_card_facts
from boostertutor.config import settings
from boostertutor.db import SessionLocal
from boostertutor.format_inputs import load_format_inputs, name_index
from boostertutor.llm.client import anthropic_client
from boostertutor.llm.pick_note import (
    PROMPT_VERSION,
    PickNoteFailed,
    load_prompt,
    write_pick_note,
)
from boostertutor.llm.spending import DbLedger, SpendingCapReached
from boostertutor.models import LlmCall
from boostertutor.parsing import seventeen_lands
from boostertutor.schemas import DraftLog


class CountingLedger(DbLedger):
    """`llm_calls`, plus a tally of this run's calls for the summary."""

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
    parser.add_argument("--metadata", type=Path, help="17Lands event metadata")
    parser.add_argument("--pick", action="append", help="only this pick: P1p12")
    parser.add_argument("--dry-run", action="store_true", help="print the briefs")
    args = parser.parse_args()

    with SessionLocal() as session:
        log = load_log(session, args.draft, args.metadata)
        inputs = load_format_inputs(session, log.set_code, log.event_type)
        analysis = analyze_draft(log, inputs)
        facts = load_card_facts(session, log.set_code, analysis_cards(analysis))
        briefs = noted_pick_briefs(analysis, facts, inputs.cfg)
        if args.pick:
            wanted = {p.upper() for p in args.pick}
            briefs = [
                b for b in briefs if f"P{b.pack_number}P{b.pick_number}" in wanted
            ]
        print(f"{len(briefs)} Noted Pick(s) in {log.source}:{log.source_id}")

        if args.dry_run:
            for brief in briefs:
                print(f"\n----- P{brief.pack_number}p{brief.pick_number}\n{brief.text}")
            return

        client = anthropic_client()
        prompt = load_prompt(PROMPT_VERSION)
        ledger = CountingLedger(session)
        draft_key = f"{log.source}:{log.source_id}" if log.source_id else None
        for brief in briefs:
            label = f"P{brief.pack_number}p{brief.pick_number} ({brief.kind})"
            try:
                note = write_pick_note(
                    client,
                    ledger,
                    brief,
                    prompt=prompt,
                    cap=settings.daily_spend_cap_usd,
                    draft_key=draft_key,
                    user_id=None,
                )
            except PickNoteFailed as exc:
                print(f"\n{label}: no note. {exc}")
                continue
            except SpendingCapReached as exc:
                print(f"\n{exc} Stopping.")
                break
            print(f"\n{label}\n{note.note}")

        spent = sum((c.cost_usd for c in ledger.calls), Decimal(0))
        cache_reads = sum(c.cache_read_tokens for c in ledger.calls)
        print(
            f"\n{len(ledger.calls)} call(s), ${spent} in all, "
            f"{cache_reads:,} cache-read tokens."
        )


if __name__ == "__main__":
    main()
