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


class DeckFiring(BaseModel):
    """One deck card's tag pair, and the deck cards that complete it."""

    oracle_id: uuid.UUID
    tag_on_card: str
    complementary_tag: str
    count: int  # deck cards carrying the complementary tag
    pp: float
    contributing: list[uuid.UUID]


class DeckMetrics(BaseModel):
    """Every fact Python states about a Submitted Deck (ADR 0026 s1, ADR 0028).

    The Draft Summary may say nothing about the deck that is not in here.
    """

    # The mean GIH WR of the nonland cards, minus the format's average, in pp.
    card_quality: float
    # Nonland cards by mana value, 1 to 6 (0 counts as 1, 7+ as 6), and the
    # summed distance from the format's target curve (ADR 0010, 0013).
    curve: dict[int, int]
    curve_distance: int
    # Tag-pair firings among the deck's own cards (ADR 0006, 0009): each
    # nonland card's synergy against the rest of the deck, summed, in pp.
    # The absolute form: ADR 0017's baseline is a pick-time expectation and
    # has no meaning for a finished deck.
    synergy: float
    synergy_firings: list[DeckFiring]  # the largest few, for the summary to name
    creatures: int
    removal: int  # cards tagged _removal_
    # ADR 0028 s3: the most Colour Sources any one spell is short of Karsten's
    # requirement, and that spell ("this needs 12 red sources; your deck has
    # 8"). Only a shortfall counts, so a deck with enough sources scores 0
    # and names no spell. Sources can be fractional, as Fixers weigh less
    # than a land.
    mana_shortfall: float
    mana_short_spell: uuid.UUID | None
    mana_short_colors: str | None  # "R", or "RW" for a hybrid pip
    mana_required: int | None
    mana_available: float | None
    spells_short: int  # copies short at all; a fact for the summary, not graded
