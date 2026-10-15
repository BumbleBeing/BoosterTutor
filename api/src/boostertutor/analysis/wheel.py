"""Wheel analysis: what came back, and what the table took (development plan 3.3).

At a table of eight, the pack you open is passed round the other seven
drafters and comes back to you eight picks later. So for every pick in the
first lap of a pack (picks 1-6 of a 14-card pack, 1-7 of a 15-card one) the
draft log knows exactly:

  * **what wheeled**: the pack at pick p + 8, all of which went round the
    whole table untaken;
  * **what the table took**: the pack at pick p, minus the card you took,
    minus what came back. Seven cards, one per other drafter.

A *good* card wheeling says nobody else at the table wanted its colour,
which is the loudest signal a draft gives. "Good" here means a game-in-hand
win rate at or above the format's average, the measured `format_avg_wr`,
not a new threshold (ADR 0013's constants, nothing invented).

These are facts for the review to explain, **not a scoring term**. ADR 0018
retired openness from the fitness function after the backtest found it paid
for what a card's win rate already prices; noticing that a colour is
flowing is still worth telling a drafter about, and this is where it lives.
Pure, like the rest of `analysis/`.
"""

import uuid
from collections import Counter
from typing import Any

from ..schemas import DraftLog
from ..schemas.draft_analysis import ColorSignal, PackWheel, WheelCard, WheelLap
from ..schemas.draft_log import PACKS

# Drafters at the table. Every format v1 reviews is an eight-person pod;
# a pack comes back after passing through the seven others.
SEATS = 8

COLORS = "WUBRG"


def wheel_analysis(
    log: DraftLog,
    cards: dict[uuid.UUID, dict[str, Any]],
    gih_wr: dict[uuid.UUID, float],
    alsa: dict[uuid.UUID, float],
    format_avg_wr: float,
) -> list[PackWheel]:
    """One `PackWheel` per pack: each first-lap pick's wheel, and a colour summary."""
    size = log.pack_size
    picks = {(p.pack_number, p.pick_number): p for p in log.picks}

    def card(oid: uuid.UUID) -> WheelCard:
        wr = gih_wr.get(oid)
        return WheelCard(
            oracle_id=oid,
            colors=cards[oid]["colors"],
            gih_wr=wr,
            alsa=alsa.get(oid),
            above_average=wr is not None and wr >= format_avg_wr,
        )

    wheels = []
    for pack in range(1, PACKS + 1):
        laps = []
        for first in range(1, size - SEATS + 1):
            opened, returned = picks[(pack, first)], picks[(pack, first + SEATS)]
            gone = Counter(opened.pack_cards) - Counter([opened.picked])
            came_back = Counter(returned.pack_cards)
            if came_back - gone:
                # A card came back that was never there: the table was not
                # eight seats, or the log is wrong. Say nothing rather than
                # report a wheel that did not happen.
                raise ValueError(
                    f"pack {pack}: pick {first + SEATS} holds cards pick {first} did not"
                )
            taken = gone - came_back
            laps.append(
                WheelLap(
                    first_pick=first,
                    returned_at=first + SEATS,
                    wheeled=[card(oid) for oid in returned.pack_cards],
                    taken_by_table=[card(oid) for oid in sorted(taken.elements())],
                )
            )
        wheels.append(PackWheel(pack_number=pack, laps=laps, colors=_colors(laps)))
    return wheels


def _colors(laps: list[WheelLap]) -> list[ColorSignal]:
    """Per colour, across a pack's laps: good cards that wheeled, cards taken.

    A gold card counts for each of its colours. Colourless cards count for
    none: an artifact wheeling says nothing about which colour is open.
    """
    signals = []
    for color in COLORS:
        wheeled = [c for lap in laps for c in lap.wheeled if color in c.colors]
        taken = [c for lap in laps for c in lap.taken_by_table if color in c.colors]
        good = [c for c in wheeled if c.above_average]
        signals.append(
            ColorSignal(
                color=color,
                good_cards_wheeled=len(good),
                cards_wheeled=len(wheeled),
                cards_taken_by_table=len(taken),
                best_wheeled=max(good, key=lambda c: c.gih_wr or 0.0).oracle_id
                if good
                else None,
            )
        )
    return signals
