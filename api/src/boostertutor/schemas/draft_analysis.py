"""What the analysis says about a draft (development plan 3.3).

Every fact the review will state is in here, computed by Python. Claude
(Phase 4) only explains it in prose, and may not state a number that is not
in this shape.

Points of win rate (pp) are rounded to a thousandth. The verdicts are
decided on the unrounded values; the rounding is only so a stored analysis
or a golden file does not change with floating-point noise.
"""

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel

FitnessClass = Literal["solid", "questionable", "mistake"]
Verdict = Literal["indifferent", "solid", "questionable", "mistake"]


class SynergyFiring(BaseModel):
    """One authored tag pair that found its complement in the pool (ADR 0006, 0017)."""

    tag_on_card: str
    complementary_tag: str
    pool_count: int  # n: pool cards carrying the complementary tag
    effective_count: float  # n after the edge's decay (ADR 0009)
    expected_count: float  # what this card usually finds (ADR 0017)
    coefficient: float
    pp: float  # synergy_weight x coefficient x (effective - expected)
    contributing: list[uuid.UUID]  # the pool cards behind it, in pick order


class CardScore(BaseModel):
    """One card in a pack, scored against the pool before the pick.

    The parts add up to `total`. A basic land is never scored: it has no
    score and no class, and taking one is always a mistake.
    """

    oracle_id: uuid.UUID
    scored: bool
    total: float | None = None
    gih_wr: float | None = None  # the base, the format-wide game-in-hand win rate
    color_fit: float = 0.0  # the commitment tax, never positive (ADR 0012, 0015)
    curve: float = 0.0
    role: float = 0.0  # removal scarcity (ADR 0018)
    synergy: float = 0.0
    games: int = 0  # the sample behind gih_wr
    insufficient_data: bool = False  # under FitnessConfig.min_games
    fitness_class: FitnessClass | None = None  # by gap to the pack's best (ADR 0008)
    firings: list[SynergyFiring] = []  # at most two, the largest


class PoolState(BaseModel):
    """The pool before a pick: what a coach would glance at."""

    size: int
    colors: dict[str, int]  # cards containing each colour, lands excluded
    curve: dict[int, int]  # non-land cards by mana value, 0 to 6 (6 = 6+)
    creatures: int
    removal: int  # cards tagged _removal_
    predicted_archetype: str | None  # the leading pair (ADR 0012 s4)


class PickAnalysis(BaseModel):
    pack_number: int
    pick_number: int
    picked: uuid.UUID
    verdict: Verdict
    best: uuid.UUID | None  # the highest-scoring card; None if nothing scored
    # How many pp the pick fell short of the best card. 0 when the best card
    # was taken; None when the card taken was never scored (a basic land).
    gap: float | None
    commitment: float  # lambda: how much the pool constrained this pick
    pool: PoolState
    cards: list[CardScore]  # one per distinct card in the pack, best first


class DraftAnalysis(BaseModel):
    set_code: str
    event_type: str
    stats_snapshot: dt.date  # which 17Lands dump the win rates come from
    has_taxonomy: bool  # False: the set is untagged, so synergy and role are zero
    pack_size: int
    picks: list[PickAnalysis]
