"""Colour Sources, Fixers and the effective land count (ADR 0028).

Pure, like the rest of `analysis/`. A Fixer's figures arrive already
resolved, as a `ManaSource`: the taxonomy loader applies its kind's defaults,
its expected Treasures and any override when the file is loaded, so nothing
here knows about kinds.
"""

from dataclasses import dataclass
from typing import Any

from .fitness import LAND_TAG, PIP_RE

# A `ManaSource.colors` value meaning "whichever basics the deck runs".
BASICS = "basics"


@dataclass(frozen=True)
class ManaSource:
    """One Fixer's contribution to a deck's mana, as stored in `card_mana_sources`.

    `colors` is what the card fixes for ("G", "BR", "WUBRG"), or `BASICS`.
    `color_weight` is how much of a Colour Source one copy is, counted only
    toward spells of at least `min_mana_value`. `land_weight` is how much of
    a land it is, for the effective land count.
    """

    kind: str
    colors: str
    color_weight: float
    land_weight: float
    min_mana_value: int = 0


# --------------------------------------------------------------------------
# What a spell needs: Karsten's 40-card table
# --------------------------------------------------------------------------

# Frank Karsten, "How Many Sources Do You Need to Consistently Cast Your
# Spells? A 2022 Update", TCGplayer (formerly ChannelFireball):
# https://www.tcgplayer.com/content/article/How-Many-Sources-Do-You-Need-to-Consistently-Cast-Your-Spells-A-2022-Update/dc23a7d2-0a16-4c0b-ad36-586fcca03ad8/
# The 40-card column: 17 lands, a 90% chance of casting the spell on curve.
# Keyed by (coloured pips of the colour, other mana in the cost), so "1CC",
# a three-drop with two pips of the colour, is (2, 1).
KARSTEN_40: dict[tuple[int, int], int] = {
    (1, 0): 9, (1, 1): 9, (1, 2): 8, (1, 3): 7, (1, 4): 6, (1, 5): 6,
    (2, 0): 14, (2, 1): 12, (2, 2): 11, (2, 3): 10, (2, 4): 9, (2, 5): 8,
    (3, 0): 16, (3, 1): 14, (3, 2): 13, (3, 3): 11, (3, 4): 10,
    (4, 0): 17, (4, 1): 15,
}  # fmt: skip


def sources_needed(pips: int, other: int, *, gold: bool = False) -> int:
    """The sources of one colour a spell needs, from `KARSTEN_40`.

    Past the table's edges the nearest entry is used. More other mana than
    the table lists reads as the most it lists for that many pips, which
    errs toward needing more. More than four pips reads as four; Limited
    hardly prints such a spell. A gold spell needs one more of each colour, as
    Karsten does: it competes with its other colours for the same draws.
    """
    pips = min(pips, 4)
    other = min(other, max(o for p, o in KARSTEN_40 if p == pips))
    return KARSTEN_40[(pips, other)] + (1 if gold else 0)


def pip_groups(mana_cost: str | None) -> dict[str, int]:
    """How many pips of each kind a cost has, keyed by the colours that pay them.

    A plain or Phyrexian pip is keyed by its colour ("R"). A hybrid pip is
    keyed by both its colours ("RW"), because a source of either pays it. A
    two-or-colour pip ({2/W}) can be paid generically, so it is no pip at
    all. Only the front face of a split or adventure cost counts.
    """
    groups: dict[str, int] = {}
    for pip in PIP_RE.findall((mana_cost or "").split("//")[0]):
        parts = pip.split("/")
        if "2" in parts:
            continue
        letters = "".join(c for c in "WUBRG" if c in parts)
        if letters:
            groups[letters] = groups.get(letters, 0) + 1
    return groups


# --------------------------------------------------------------------------
# What a deck has: Colour Sources, and each spell's shortfall
# --------------------------------------------------------------------------

# ADR 0028 s2: a basic-fetcher in a deck of this many basic types or more
# counts two thirds, as Karsten counts fetch lands, because it forces a choice.
BASICS_CHOICE_COLOURS = 3
BASICS_CHOICE_WEIGHT = 2 / 3


@dataclass(frozen=True)
class Shortfall:
    """One spell's worst colour: what it needs against what the deck has."""

    oracle_id: Any
    colors: str  # the pip's colours: "R", or "RW" for a hybrid pip
    required: int
    available: float

    @property
    def short(self) -> float:
        return max(0.0, self.required - self.available)


def shortfalls(
    cards: list[dict[str, Any]],
    basics: dict[str, int],
    mana_sources: dict[Any, ManaSource],
) -> list[Shortfall]:
    """Each coloured spell's worst colour, one entry per copy (ADR 0028 s3).

    `cards` are the deck's nonbasic cards as `fitness_card` dicts, with
    their `mana_cost`. A spell's sources for a pip are the lands that make
    one of its colours, counted whole, plus the Fixers whose minimum mana
    value the spell meets, counted at their weight. A Fixer is never a
    source for its own copy: Dori's Treasure can't pay for Dori.

    A land's colours are its colour identity, as elsewhere in the analysis
    (ADR 0012 s6). That is exact for every land HOB prints; a land whose
    identity says more than it taps for would be over-counted.
    """
    basic_colours = {c for c, n in basics.items() if n}
    basics_weight = (
        BASICS_CHOICE_WEIGHT if len(basic_colours) >= BASICS_CHOICE_COLOURS else 1.0
    )

    def fixes(source: ManaSource) -> set[str]:
        return basic_colours if source.colors == BASICS else set(source.colors)

    def weight(source: ManaSource) -> float:
        scale = basics_weight if source.colors == BASICS else 1.0
        return source.color_weight * scale

    land_colours: list[set[str]] = [
        set(c["color_identity"])
        for c in cards
        if LAND_TAG in c["tags"] and c["oracle_id"] not in mana_sources
    ]
    land_colours += [{colour} for colour, n in basics.items() for _ in range(n)]
    fixers = [
        (c["oracle_id"], mana_sources[c["oracle_id"]])
        for c in cards
        if c["oracle_id"] in mana_sources
    ]

    out: list[Shortfall] = []
    for card in cards:
        if LAND_TAG in card["tags"]:
            continue
        groups = pip_groups(card.get("mana_cost"))
        if not groups:
            continue  # colourless: any land casts it
        options = card.get("color_options") or [card["colors"]]
        gold = all(len(option) >= 2 for option in options)
        mana_value = int(card["cmc"])
        worst: Shortfall | None = None
        for colours, pips in groups.items():
            wanted = set(colours)
            available = sum(1.0 for produced in land_colours if produced & wanted)
            own_copy_skipped = False
            for oracle_id, source in fixers:
                if oracle_id == card["oracle_id"] and not own_copy_skipped:
                    own_copy_skipped = True
                    continue
                if mana_value >= source.min_mana_value and fixes(source) & wanted:
                    available += weight(source)
            required = sources_needed(pips, max(0, mana_value - pips), gold=gold)
            here = Shortfall(card["oracle_id"], colours, required, available)
            if worst is None or here.short > worst.short:
                worst = here
        if worst is not None:
            out.append(worst)
    return out


# --------------------------------------------------------------------------
# The effective land count (ADR 0028 s4)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class LandTarget:
    """How many lands a deck wants, by the average mana value of its spells.

    Per format, from `format_constants` (ADR 0028 s4, as amended): `low`
    lands below `low_below_mv`, `high` from `high_from_mv` up, `middle`
    between. The two cuts may be equal, leaving no middle band: HOB's
    measured rule is 16 lands below 3.0 and 18 from 3.0, because 17 was
    never the best count once card quality is accounted for.

    The defaults are ADR 0028's original placeholders, for tests and for a
    format whose row predates the land columns. `over_weight` stays a
    placeholder: being over weighs half of being short.
    """

    low: int = 16
    middle: int = 17
    high: int = 18
    low_below_mv: float = 2.2
    high_from_mv: float = 3.2
    over_weight: float = 0.5

    def lands_for(self, average_mana_value: float) -> int:
        if average_mana_value < self.low_below_mv:
            return self.low
        if average_mana_value >= self.high_from_mv:
            return self.high
        return self.middle

    def distance(self, effective: float, target: int) -> float:
        """Short weighs 1 a land, over weighs `over_weight` a land."""
        return max(0.0, target - effective) + self.over_weight * max(
            0.0, effective - target
        )


def effective_lands(
    cards: list[dict[str, Any]],
    basics: dict[str, int],
    mana_sources: dict[Any, ManaSource],
) -> float:
    """Every land counts 1 and every Fixer its land weight, a fetch land included."""
    total = float(sum(basics.values()))
    for card in cards:
        source = mana_sources.get(card["oracle_id"])
        if source is not None:
            total += source.land_weight
        elif LAND_TAG in card["tags"]:
            total += 1.0
    return total
