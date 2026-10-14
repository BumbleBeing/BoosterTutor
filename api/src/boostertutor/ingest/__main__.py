"""CLI: `uv run python -m boostertutor.ingest scryfall [--sets hob,abc] [--recent 3] [--force]`.

Downloads are cached under `data/raw/`, so re-running is cheap. Each source
records its run in `ingest_runs`, and skips itself when nothing upstream has
changed; `--force` re-downloads and re-ingests regardless.
"""

import argparse
import sys

from ..db import SessionLocal
from . import scryfall


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m boostertutor.ingest")
    sources = parser.add_subparsers(dest="source", required=True)

    scry = sources.add_parser(
        "scryfall", help="cards and printings from Scryfall bulk data"
    )
    scry.add_argument(
        "--sets",
        help="comma-separated set codes, e.g. hob,abc (default: the most recent)",
    )
    scry.add_argument(
        "--recent",
        type=int,
        default=3,
        help="how many recent draftable sets (default 3)",
    )
    scry.add_argument(
        "--force",
        action="store_true",
        help="re-download and re-ingest even if unchanged",
    )

    args = parser.parse_args(argv)
    with SessionLocal() as session:
        if args.source == "scryfall":
            codes = (
                [c.strip() for c in args.sets.split(",") if c.strip()]
                if args.sets
                else None
            )
            scryfall.load(
                session, set_codes=codes, recent=args.recent, force=args.force
            )
    print("Card data from Scryfall (https://scryfall.com).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
