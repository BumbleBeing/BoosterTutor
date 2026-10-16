"""CLI for the ingests. Run Scryfall first: the 17Lands ingest matches names to its cards.

    uv run python -m boostertutor.ingest scryfall [--sets hob,abc] [--recent 3] [--force]
    uv run python -m boostertutor.ingest 17lands  [--sets hob,abc] [--event-type PremierDraft] [--force]
    uv run python -m boostertutor.ingest taxonomy [--sets hob]
    uv run python -m boostertutor.ingest synergy-baseline [--sets hob] [--max-drafts N]
    uv run python -m boostertutor.ingest deck-ratings [--sets hob]

`taxonomy` loads the hand-authored tags from `data/taxonomy/`, not from
upstream, so it also runs after Scryfall and replaces what was there.
`synergy-baseline` measures ADR 0017's baseline from the cached draft dump;
run it after `taxonomy` whenever which cards carry which tags changes.
`deck-ratings` fits ADR 0026's Deck Ratings from the cached game dump; run
it after `synergy-baseline`, and again whenever tags or Fixers change.

Downloads are cached under `data/raw/`, so re-running is cheap. Each source
records its run in `ingest_runs`, and skips itself when nothing upstream has
changed; `--force` re-downloads and re-ingests regardless.
"""

import argparse
import sys

from ..db import SessionLocal
from . import deck_ratings, scryfall, seventeen_lands, synergy_baseline, taxonomy


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

    lands = sources.add_parser(
        "17lands", help="win rates and ALSA/ATA from the 17Lands public datasets"
    )
    lands.add_argument(
        "--sets",
        help="comma-separated set codes (default: every ingested draftable set)",
    )
    lands.add_argument("--event-type", default=seventeen_lands.DEFAULT_EVENT_TYPE)
    lands.add_argument(
        "--force", action="store_true", help="re-ingest even if the dump is unchanged"
    )

    tax = sources.add_parser(
        "taxonomy", help="the hand-authored tags, from data/taxonomy/{set}.json"
    )
    tax.add_argument(
        "--sets", help="comma-separated set codes (default: every taxonomy file)"
    )

    base = sources.add_parser(
        "synergy-baseline",
        help="ADR 0017's synergy baseline, from the cached draft dump (slow)",
    )
    base.add_argument(
        "--sets", help="comma-separated set codes (default: every taxonomy file)"
    )
    base.add_argument("--event-type", default=seventeen_lands.DEFAULT_EVENT_TYPE)
    base.add_argument(
        "--max-drafts", type=int, help="measure only the first N drafts (a sample)"
    )

    ratings = sources.add_parser(
        "deck-ratings",
        help="ADR 0026's Deck Ratings, fitted from the cached game dump (slow)",
    )
    ratings.add_argument(
        "--sets",
        help="comma-separated set codes (default: every ingested draftable set)",
    )
    ratings.add_argument("--event-type", default=seventeen_lands.DEFAULT_EVENT_TYPE)

    args = parser.parse_args(argv)
    codes = (
        [c.strip() for c in args.sets.split(",") if c.strip()] if args.sets else None
    )
    with SessionLocal() as session:
        if args.source == "scryfall":
            scryfall.load(
                session, set_codes=codes, recent=args.recent, force=args.force
            )
            print("Card data from Scryfall (https://scryfall.com).")
        elif args.source == "synergy-baseline":
            synergy_baseline.load(
                session,
                codes or taxonomy.available_sets(),
                args.event_type,
                max_drafts=args.max_drafts,
            )
        elif args.source == "deck-ratings":
            deck_ratings.load(
                session, codes or seventeen_lands.default_sets(session), args.event_type
            )
        elif args.source == "taxonomy":
            taxonomy.load(session, codes or taxonomy.available_sets())
        else:
            seventeen_lands.load(
                session, set_codes=codes, event_type=args.event_type, force=args.force
            )
            print(
                "Data from 17Lands (https://www.17lands.com/public_datasets), CC BY 4.0."
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
