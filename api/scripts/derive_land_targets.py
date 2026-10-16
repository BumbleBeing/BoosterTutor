"""Measure a format's land targets from its game dump, and print them (ADR 0028 s4).

    RAW_DATA_DIR=... uv run python scripts/derive_land_targets.py hob [--event-type PremierDraft]

Prints the five `format_constants` land columns for a person to transcribe,
as ADR 0013 asks of every format constant: nothing here writes to the
database. Works before the format has a `format_constants` row, since the
targets are measured alongside its other constants.

The method, settled with Jackson on 2026-10-15:

1. Read each distinct 40-card deck in the cached game dump, with its
   average nonland mana value, its effective land count (Fixers included,
   so run it after `ingest taxonomy`), its mean GIH WR and its record.
2. **Adjust each deck's wins for card quality.** Raw win rates say that
   fewer lands win more, because fast decks with strong cards run fewer
   lands. A games-weighted line of win rate on mean GIH WR is fitted, and
   each deck's wins above that line are what the land count is judged on.
3. Each deck counts at its nearest whole land count, in bands of average
   mana value 0.1 wide. A rule has the shape "`low` below cut A, `high`
   from cut B, `middle` between" (A <= B, cuts on a 0.1 grid, low and high
   one land either side of middle). Its score is the adjusted win rate, in
   each band, of the decks running the count the rule asks for, averaged
   over bands weighted by their games: how well a format's decks would do
   if each ran its target. A band whose target count has too few games to
   measure scores its worst measured count, so a rule cannot win by
   pointing at counts nobody plays. The highest score wins.

   (Comparing on-target decks with off-target ones instead was tried, and
   it favours rules that put almost no deck on target.)

A decimal target fitted as a line in mana value was tried first and
rejected: on HOB it ran to the edge of its search, and resampling the
decks moved it by two lands.
"""

import argparse
import csv
import gzip
import math
from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from boostertutor.analysis import fitness as fx
from boostertutor.analysis.deck import deck_metrics
from boostertutor.analysis.draft import FormatInputs
from boostertutor.db import SessionLocal
from boostertutor.drafts import name_index
from boostertutor.format_inputs import load_cards, load_mana_sources
from boostertutor.ingest.deck_ratings import decks_from_game_rows
from boostertutor.ingest.synergy_baseline import cached_dump
from boostertutor.models import CardDraftStats

CUTS = [round(2.0 + 0.1 * i, 1) for i in range(21)]  # 2.0 to 4.0
MIDDLES = (16, 17, 18)
# A (band, land count) cell needs this many games to be measured at all.
MIN_CELL_GAMES = 1000


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("set_code")
    parser.add_argument("--event-type", default="PremierDraft")
    args = parser.parse_args()

    with SessionLocal() as session:
        inputs = _inputs(session, args.set_code, args.event_type)
        names = name_index(session, args.set_code)
    path = cached_dump("game_data_public", args.set_code, args.event_type)
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        found = decks_from_game_rows(next(reader), reader, names)

    decks = []
    for d in found.decks:
        m = deck_metrics(d.deck, inputs)
        decks.append(
            (m.average_mana_value, m.effective_lands, m.card_quality, d.wins, d.games)
        )
    print(f"{path.name}: {len(decks):,} decks, {sum(d[4] for d in decks):,} games")

    # Step 2: wins above what card quality predicts, per deck.
    games = sum(d[4] for d in decks)
    mean_q = sum(q * g for _, _, q, _, g in decks) / games
    mean_y = sum(w for *_, w, _ in decks) / games
    slope = sum(g * (q - mean_q) * (w / g - mean_y) for _, _, q, w, g in decks) / sum(
        g * (q - mean_q) ** 2 for _, _, q, _, g in decks
    )
    print(f"win rate rises {100 * slope:.2f}pp per pp of mean GIH WR; adjusting for it")

    # Step 3: aggregate by (mana value band, whole lands), then score rules.
    cells: dict[tuple[float, int], list[float]] = defaultdict(lambda: [0.0, 0.0])
    for mv, lands, q, w, g in decks:
        band = math.floor(mv * 10) / 10
        cell = cells[(band, round(lands))]
        cell[0] += w - g * (mean_y + slope * (q - mean_q))
        cell[1] += g

    _print_bands(cells)
    rules = []
    for middle in MIDDLES:
        for i, low_below in enumerate(CUTS):
            for high_from in CUTS[i:]:
                rule = (middle - 1, middle, middle + 1, low_below, high_from)
                rules.append((_score(cells, *rule), rule))
    rules.sort(reverse=True)
    print("\nbest rules: adjusted win rate if every deck ran its target")
    for (score, share), (low, mid, high, a, b) in rules[:5]:
        print(
            f"  {low} below {a:.1f}, {mid} between, {high} from {b:.1f}: "
            f"{score:+.2f}pp ({100 * share:.0f}% of games on target)"
        )
    low, mid, high, a, b = rules[0][1]
    print(
        "\nformat_constants:\n"
        f"  land_target_low = {low}\n  land_target_mid = {mid}\n"
        f"  land_target_high = {high}\n  land_low_below_mv = {a:.2f}\n"
        f"  land_high_from_mv = {b:.2f}"
    )


def _score(
    cells: dict[tuple[float, int], list[float]],
    low: int,
    middle: int,
    high: int,
    low_below: float,
    high_from: float,
) -> tuple[float, float]:
    """The games-weighted adjusted win rate at the rule's target, and its coverage."""
    measured: dict[float, dict[int, float]] = defaultdict(dict)
    band_games: dict[float, float] = defaultdict(float)
    for (band, lands), (resid, g) in cells.items():
        band_games[band] += g
        if g >= MIN_CELL_GAMES:
            measured[band][lands] = resid / g
    total = weighted = on_target = 0.0
    for band, rates in measured.items():
        # Bands are 0.1 wide and the cuts sit on band edges, so a band's
        # lower edge says which side of a cut all of it is on.
        if band < low_below - 1e-9:
            target = low
        elif band >= high_from - 1e-9:
            target = high
        else:
            target = middle
        rate = rates.get(target, min(rates.values()))
        weighted += band_games[band] * rate
        total += band_games[band]
        on_target += cells.get((band, target), (0.0, 0.0))[1]
    return 100 * weighted / total, on_target / total


def _print_bands(cells: dict[tuple[float, int], list[float]]) -> None:
    print("\nadjusted win rate (pp) by average mana value and whole lands")
    print("  avg MV       16       17       18   best")
    for band in sorted({b for b, _ in cells}):
        row, best = [], None
        for lands in (16, 17, 18):
            resid, g = cells.get((band, lands), (0.0, 0.0))
            if g >= MIN_CELL_GAMES:
                pp = 100 * resid / g
                row.append(f"{pp:+8.1f}")
                if best is None or pp > best[0]:
                    best = (pp, lands)
            else:
                row.append(" " * 8)
        if best:
            print(f"  {band:6.1f} {''.join(row)}   {best[1]}")


def _inputs(session: Session, set_code: str, event_type: str) -> FormatInputs:
    """Just what the metrics read, without needing a `format_constants` row.

    The format average is the cards' own games-weighted mean: card quality
    is only ever compared within the format, so its offset cancels out.
    """
    snapshot = session.scalar(
        select(func.max(CardDraftStats.snapshot_date)).where(
            CardDraftStats.set_code == set_code, CardDraftStats.event_type == event_type
        )
    )
    rows = session.scalars(
        select(CardDraftStats).where(
            CardDraftStats.set_code == set_code,
            CardDraftStats.event_type == event_type,
            CardDraftStats.snapshot_date == snapshot,
        )
    ).all()
    overall = {
        s.oracle_id: (s.gih_wr, s.gih_games) for s in rows if s.gih_wr is not None
    }
    games = sum(g for _, g in overall.values())
    return FormatInputs(
        set_code=set_code,
        event_type=event_type,
        stats_snapshot=snapshot,
        cards=load_cards(session, set_code),
        stats=fx.Stats(
            format_avg_wr=sum(wr * g for wr, g in overall.values()) / games,
            overall=overall,
        ),
        mana_sources=load_mana_sources(session, set_code),
    )


if __name__ == "__main__":
    main()
