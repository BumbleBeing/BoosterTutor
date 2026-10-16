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
from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel

from .draft_analysis import DraftAnalysis

DECK_SIZE = 40
BASIC_COLOURS = "WUBRG"
# A basic land by name, as a deck list writes it.
BASIC_NAMES = {
    "Plains": "W",
    "Island": "U",
    "Swamp": "B",
    "Mountain": "R",
    "Forest": "G",
}


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


def drafted_pool(
    analysis: DraftAnalysis, cards: Mapping[uuid.UUID, Any]
) -> list[uuid.UUID]:
    """The cards a deck is built from: every pick but the basic lands (ADR 0025 s1).

    `cards` maps each oracle id to anything with a `type_line`, such as
    `CardFacts`.
    """
    return [
        p.picked
        for p in analysis.picks
        if not cards[p.picked].type_line.startswith("Basic Land")
    ]


def deck_from_names(
    pool: list[uuid.UUID], names: list[str], ids: Mapping[str, uuid.UUID]
) -> Deck:
    """A deck written as card names, one entry per copy, basics included.

    How the eval's fixture decks are written. `ids` maps a card's name to
    its oracle id; basics are counted by colour, as the deck builder adds
    them. A name that is neither a basic nor known raises `DeckError`
    naming it, and the deck is then checked as `deck_from_pool` checks it.
    """
    basics: Counter[str] = Counter()
    main = []
    unknown = []
    for name in names:
        if name in BASIC_NAMES:
            basics[BASIC_NAMES[name]] += 1
        elif name in ids:
            main.append(ids[name])
        else:
            unknown.append(name)
    if unknown:
        raise DeckError(f"not a card in this draft: {', '.join(unknown)}")
    return deck_from_pool(pool, main=main, basics=dict(basics))


class DeckFiring(BaseModel):
    """One deck card's tag pair, and the deck cards that complete it."""

    oracle_id: uuid.UUID
    tag_on_card: str
    complementary_tag: str
    count: int  # deck cards carrying the complementary tag
    pp: float
    contributing: list[uuid.UUID]


class NotableOmission(BaseModel):
    """A sideboard card far better than the deck's weakest playable (ADR 0026 s1)."""

    oracle_id: uuid.UUID
    gih_wr: float
    instead_of: uuid.UUID  # the deck's weakest nonland card
    instead_of_gih_wr: float
    gap: float  # gih_wr - instead_of_gih_wr, past FitnessConfig.mistake_gap


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
    # ADR 0028 s4: lands plus Fixers' land weights, against a target set by
    # the nonland cards' average mana value. The distance weighs being short
    # twice as hard as being over.
    average_mana_value: float
    effective_lands: float
    land_target: int
    land_distance: float
    # At most one, and only as a fact: ranked swaps stay postponed (ADR 0025 s4).
    notable_omission: NotableOmission | None


Grade = Literal["A", "B", "C", "D", "F"]


class MetricRating(BaseModel):
    """One metric's value, and where it falls among the format's decks."""

    metric: str
    value: float
    percentile: int | None = None  # 0-100: the share of decks it is as good as
    grade: Grade | None = None


class DeckRatings(BaseModel):
    """A Submitted Deck's Deck Ratings (ADR 0026 s2).

    Relative to 17Lands users, who play better than average: a C is an
    average 17Lands deck. Unrated when the format has no fitted model.
    """

    rated: bool
    message: str | None = None  # "not enough data to rate" when unrated
    metrics: list[MetricRating]
    predicted_win_rate: float | None = None  # the regression's, in percent
    percentile: int | None = None
    grade: Grade | None = None
