"""17Lands public datasets: addresses, and reading what a dump says.

Only the pieces the Scryfall ingest needs so far: the draft dump's address,
and the card names its header lists. The full 17Lands ingest (development
plan 2.3) builds on this module.

Data from 17Lands (https://www.17lands.com/public_datasets), CC BY 4.0. The
etiquette in CLAUDE.md applies: cached snapshots only, at most one request
per set and format per day, never from a user request path.
"""

import csv

S3_BASE = "https://17lands-public.s3.amazonaws.com/analysis_data"

# Every card that appears in a pack has a `pack_card_<name>` column.
PACK_CARD_PREFIX = "pack_card_"


def draft_data_url(set_code: str, event_type: str = "PremierDraft") -> str:
    """17Lands spells set codes in upper case: `HOB`, not `hob`."""
    return (
        f"{S3_BASE}/draft_data/draft_data_public.{set_code.upper()}.{event_type}.csv.gz"
    )


def pack_card_names(header_line: str) -> list[str]:
    """Every card name a draft dump's header says appeared in a pack.

    A double-faced card is named by its front face alone, as 17Lands does.
    """
    header = next(csv.reader([header_line]))
    return [
        column[len(PACK_CARD_PREFIX) :]
        for column in header
        if column.startswith(PACK_CARD_PREFIX)
    ]
