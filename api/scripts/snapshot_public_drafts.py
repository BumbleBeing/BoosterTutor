"""Save real drafts from the 17Lands public draft dataset as test fixtures.

    uv run python scripts/snapshot_public_drafts.py PATH/TO/draft_data_public.HOB.PremierDraft.csv.gz

The eval harness for Pick Notes (ADR 0024 s9) needs a second draft beside
the saved HOB draft link, and the few-shot examples want a third, so that
no example is written from a pick the eval then grades. The public dataset
holds many whole drafts, one row per pick, so they come from there: a
cached file, never a request (ADR 0002).

The script reads drafts until it has scanned `--scan` complete ones,
analyses each against the database's format inputs, and keeps the first
drafts that have both a Narrow Pick and at least two critical Noted Picks.
Each is written to `tests/fixtures/drafts/<set>.<id8>.draft_log.json` as a
`DraftLog`. Then re-run `snapshot_format_inputs.py`, so the inputs fixture
covers the new drafts' cards.
"""

import argparse
import csv
import gzip
import uuid
from collections.abc import Iterator
from pathlib import Path

from boostertutor.analysis.draft import analyze_draft
from boostertutor.db import SessionLocal
from boostertutor.format_inputs import load_format_inputs, name_index
from boostertutor.parsing.names import name_key
from boostertutor.schemas import DraftLog, Pick

API = Path(__file__).resolve().parents[1]
OUT = API / "tests" / "fixtures" / "drafts"

PACK_PREFIX = "pack_card_"


def draft_rows(path: Path) -> Iterator[list[dict[str, str]]]:
    """Each draft's rows, in the file's order. The dump keeps a draft together."""
    with gzip.open(path, "rt", newline="") as f:
        current: list[dict[str, str]] = []
        for row in csv.DictReader(f):
            if current and row["draft_id"] != current[0]["draft_id"]:
                yield current
                current = []
            current.append(row)
        if current:
            yield current


def to_draft_log(rows: list[dict[str, str]], names: dict[str, uuid.UUID]) -> DraftLog:
    """One draft's rows into a `DraftLog`. Raises if a pick is missing or a name unknown."""
    rows = sorted(rows, key=lambda r: (int(r["pack_number"]), int(r["pick_number"])))
    picks: list[Pick] = []
    pool: list[uuid.UUID] = []
    for row in rows:
        pack: list[uuid.UUID] = []
        for column, count in row.items():
            if column.startswith(PACK_PREFIX) and count and int(count):
                pack += [names[name_key(column[len(PACK_PREFIX) :])]] * int(count)
        picked = names[name_key(row["pick"])]
        picks.append(
            Pick(
                pack_number=int(row["pack_number"]) + 1,  # the dump counts from 0
                pick_number=int(row["pick_number"]) + 1,
                pack_cards=pack,
                picked=picked,
                pool_before=list(pool),
            )
        )
        pool.append(picked)
    first = rows[0]
    return DraftLog(
        set_code=first["expansion"].lower(),
        event_type=first["event_type"],
        drafted_at=None,  # the dump's draft_time is when the event began, not the draft
        source="17lands",
        source_id=first["draft_id"],
        wins=int(first["event_match_wins"]),
        losses=int(first["event_match_losses"]),
        picks=picks,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dump", type=Path)
    parser.add_argument("--keep", type=int, default=2, help="drafts to save")
    parser.add_argument("--scan", type=int, default=400, help="drafts to analyse")
    args = parser.parse_args()

    with SessionLocal() as session:
        first = next(draft_rows(args.dump))[0]
        set_code, event_type = first["expansion"].lower(), first["event_type"]
        names = name_index(session, set_code)
        inputs = load_format_inputs(session, set_code, event_type)

    kept = 0
    scanned = 0
    for rows in draft_rows(args.dump):
        if scanned >= args.scan or kept >= args.keep:
            break
        try:
            log = to_draft_log(rows, names)
        except (KeyError, ValueError):
            continue  # an incomplete draft, or a card the set's packs can't hold
        scanned += 1
        analysis = analyze_draft(log, inputs)
        narrow = [p for p in analysis.picks if p.narrow]
        critical = [p for p in analysis.picks if p.noted and not p.narrow]
        if not narrow or len(critical) < 2:
            continue
        OUT.mkdir(parents=True, exist_ok=True)
        assert log.source_id is not None
        out = OUT / f"{log.set_code}.{log.source_id[:8]}.draft_log.json"
        out.write_text(log.model_dump_json(indent=1) + "\n")
        kept += 1
        print(
            f"wrote {out.relative_to(API)}: {len(narrow)} narrow, "
            f"{len(critical)} critical, after scanning {scanned}"
        )


if __name__ == "__main__":
    main()
