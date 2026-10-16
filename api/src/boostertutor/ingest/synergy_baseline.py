"""Measure how many complements each card usually finds (ADR 0017).

    uv run python -m boostertutor.ingest synergy-baseline [--sets hob] [--max-drafts N]

Synergy is scored as a margin: a firing is worth
`coefficient x (n_eff - E[n_eff | card, pack, edge])`, so a pool that is
merely typical pays nothing. This measures that expectation from the 17Lands
draft dump: for every pick, every card in the pack, and every authored edge
the card sits on, how many pool cards carried the complementary tag.

It stores a histogram of those counts (`models/tags.py`), not the
expectation, so re-tuning a coefficient or a decay never makes it stale.
Changing which cards carry a tag, or adding an edge, does: re-run it then.

Reads the draft dump the 17Lands ingest cached under `data/raw/17lands/`,
and never calls 17Lands itself. A full HOB dump is about 1.6M picks, so a run
takes tens of minutes; `--max-drafts` measures a sample.

Ported from DraftDouble's `scripts/derive_synergy_baseline.py`; the
counting loop is unchanged.
"""

import csv
import gzip
import re
import sys
import time
import uuid
from collections import defaultdict
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from sqlalchemy import delete, insert
from sqlalchemy.orm import Session

from ..config import settings
from ..drafts import name_index
from ..format_inputs import load_cards, load_edges
from ..models import SynergyBaseline
from ..parsing.names import name_key
from .runs import recorded_run
from .seventeen_lands import DEFAULT_EVENT_TYPE

SOURCE = "synergy_baseline"

# (oracle_id, pack_number, enabler, payoff, tag_on_card, complement_count)
HistogramKey = tuple[uuid.UUID, int, str, str, str, int]
# An edge, the end of it a card sits on, and the tag it counts in the pool.
Direction = tuple[dict[str, Any], str, str]


def directions(edges: list[dict[str, Any]]) -> list[Direction]:
    """Each edge with each end a card can sit on, and the complement it counts.

    Mirrors `fitness.synergy`'s walk exactly, the diagonal included: when
    enabler and payoff are the same tag, the two ends are one read.
    """
    out = []
    for e in edges:
        for on_card, complementary in (
            (e["enabler"], e["payoff"]),
            (e["payoff"], e["enabler"]),
        ):
            out.append((e, on_card, complementary))
            if e["enabler"] == e["payoff"]:
                break
    return out


def measure(
    header: list[str],
    rows: Iterable[list[str]],
    names: Mapping[str, uuid.UUID],
    tags_of: Mapping[uuid.UUID, set[str]],
    edges: list[dict[str, Any]],
    *,
    max_drafts: int | None = None,
    progress: Any = None,
) -> dict[HistogramKey, int]:
    """The histogram, from draft-dump rows (0-indexed packs, as in the file).

    Pure. A dump column whose card is not in `names` is ignored, as the
    17Lands ingest does.
    """
    idx = {name: i for i, name in enumerate(header)}

    def columns(prefix: str) -> list[tuple[int, uuid.UUID]]:
        out = []
        for name, i in idx.items():
            if name.startswith(prefix):
                oracle_id = names.get(name_key(name.removeprefix(prefix)))
                if oracle_id is not None:
                    out.append((i, oracle_id))
        return out

    pack_cols, pool_cols = columns("pack_card_"), columns("pool_")
    walk = directions(edges)
    # Which (edge, end) pairs each card can ever reach: once per card rather
    # than once per pick, since the loop below runs millions of times.
    reachable = {
        oid: [(e, on_card, comp) for e, on_card, comp in walk if on_card in tags]
        for oid, tags in tags_of.items()
    }

    histogram: dict[HistogramKey, int] = defaultdict(int)
    seen_drafts, last_draft = 0, None
    draft_col, pack_col = idx["draft_id"], idx["pack_number"]
    for row in rows:
        draft_id = row[draft_col]
        if draft_id != last_draft:
            if max_drafts is not None and seen_drafts >= max_drafts:
                break
            last_draft, seen_drafts = draft_id, seen_drafts + 1
            if progress and seen_drafts % 5000 == 0:
                progress(seen_drafts)

        # How many pool cards carry each tag, counted once per row rather
        # than once per pack card.
        tag_counts: dict[str, int] = defaultdict(int)
        for i, oid in pool_cols:
            cell = row[i]
            if cell and cell != "0":
                for tag in tags_of.get(oid, ()):
                    tag_counts[tag] += int(cell)

        pack_no = int(row[pack_col]) + 1
        for i, oid in pack_cols:
            cell = row[i]
            if not cell or cell == "0":
                continue
            for e, on_card, comp in reachable.get(oid, ()):
                n = tag_counts.get(comp, 0)
                histogram[(oid, pack_no, e["enabler"], e["payoff"], on_card, n)] += 1
    return dict(histogram)


def cached_draft_dump(set_code: str, event_type: str) -> Path:
    """The newest draft dump the 17Lands ingest has downloaded for the format."""
    return cached_dump("draft_data_public", set_code, event_type)


def cached_dump(kind: str, set_code: str, event_type: str) -> Path:
    """The newest `kind` dump ("draft_data_public", "game_data_public") cached."""
    base = f"{kind}.{set_code.upper()}.{event_type}"
    found = sorted(
        p
        for p in (settings.raw_data_dir / "17lands").glob(f"{base}.*.csv.gz")
        if re.fullmatch(rf"{re.escape(base)}\.\d{{8}}\.csv\.gz", p.name)
    )
    if not found:
        raise FileNotFoundError(
            f"no cached {base} dump: run `python -m boostertutor.ingest 17lands "
            f"--sets {set_code} --force` first"
        )
    return found[-1]


def load(
    session: Session,
    set_codes: list[str],
    event_type: str = DEFAULT_EVENT_TYPE,
    *,
    max_drafts: int | None = None,
) -> None:
    for set_code in set_codes:
        with recorded_run(session, SOURCE, scope=f"{set_code}/{event_type}") as record:
            edges = load_edges(session, set_code)
            if not edges:
                print(f"{set_code}: no tag pairs, so nothing to measure")
                record.status = "skipped"
                continue
            path = cached_draft_dump(set_code, event_type)
            record.source_url = path.name
            cards = load_cards(session, set_code)
            tags_of = {oid: set(card["tags"]) for oid, card in cards.items()}

            started = time.monotonic()

            def progress(drafts: int, started: float = started) -> None:
                elapsed = time.monotonic() - started
                print(f"  {drafts:>7} drafts, {elapsed:,.0f} s", file=sys.stderr)

            with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
                reader = csv.reader(handle)
                histogram = measure(
                    next(reader),
                    reader,
                    name_index(session, set_code),
                    tags_of,
                    edges,
                    max_drafts=max_drafts,
                    progress=progress,
                )

            session.execute(
                delete(SynergyBaseline).where(
                    SynergyBaseline.set_code == set_code,
                    SynergyBaseline.event_type == event_type,
                )
            )
            rows = [
                {
                    "set_code": set_code,
                    "event_type": event_type,
                    "oracle_id": oid,
                    "pack_number": pack,
                    "enabler": enabler,
                    "payoff": payoff,
                    "tag_on_card": on_card,
                    "complement_count": n,
                    "observations": obs,
                }
                for (oid, pack, enabler, payoff, on_card, n), obs in histogram.items()
            ]
            if rows:
                session.execute(insert(SynergyBaseline), rows)
            record.row_count = len(rows)
            sample = f", first {max_drafts} drafts only" if max_drafts else ""
            record.notes = f"{len(rows):,} histogram rows from {path.name}{sample}"
            print(f"{set_code}/{event_type}: {record.notes}")
