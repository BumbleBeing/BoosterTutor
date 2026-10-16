"""The Submitted Deck: what a drafter builds from their pool (ADR 0025).

Exactly 40 cards: pool cards plus basic lands. Basics are counted by colour
rather than named by card, because the deck builder adds them with five
buttons and the game dump records them as five columns. Any basics the
drafter took are pruned from the pool before building, so `main` never
holds one.

A larger deck would need every deck metric to handle it, for little gain,
so 40 is a rule rather than a minimum.
"""

import uuid
from collections import Counter

from pydantic import BaseModel

DECK_SIZE = 40
BASIC_COLOURS = "WUBRG"


class DeckError(ValueError):
    """The deck can't be submitted as it stands. The message says why."""


class Deck(BaseModel):
    """A 40-card deck. Copies are separate entries in `main` and `sideboard`."""

    main: list[uuid.UUID]  # the pool cards played, basics excluded
    basics: dict[str, int]  # colour letter -> how many of that basic
    sideboard: list[uuid.UUID]  # the pool cards not played

    @property
    def size(self) -> int:
        return len(self.main) + sum(self.basics.values())


def deck_from_pool(
    pool: list[uuid.UUID], *, main: list[uuid.UUID], basics: dict[str, int]
) -> Deck:
    """The deck, with what is left of the pool as its sideboard, or `DeckError`."""
    for colour, count in basics.items():
        if colour not in BASIC_COLOURS or count < 0:
            raise DeckError(f"{colour!r} x {count} is not a basic land count")
    basics = {c: n for c, n in basics.items() if n}

    # Counter subtraction drops what goes below zero, so a card played more
    # often than it was drafted shows up as a remainder on the deck's side.
    over = Counter(main) - Counter(pool)
    if over:
        raise DeckError(f"{sum(over.values())} card(s) in the deck are not in the pool")

    size = len(main) + sum(basics.values())
    if size != DECK_SIZE:
        raise DeckError(f"a deck must be {DECK_SIZE} cards; this one is {size} cards")

    sideboard = list((Counter(pool) - Counter(main)).elements())
    return Deck(main=list(main), basics=basics, sideboard=sideboard)
