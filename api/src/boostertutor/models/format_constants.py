"""Format-level constants for the fitness function (ADR 0013).

Some of what the fitness function needs varies by format rather than being a
universal truth: how far the average win rate sits, how many picks a pack
yields, what a winning deck's curve looks like, and how hard that format
punishes three-colour soup. Those used to be scattered across module
constants in two files and a dataclass of otherwise-global weights, with
only a comment to say which was which.

**Nothing writes to this table automatically.** Scripts print, a person
transcribes. The values change roughly once per set, so automating a
three-times-a-year edit buys nothing and risks a nightly job quietly
clobbering a hand-picked number. The `source` column records how each row's
values were arrived at.
"""

import datetime as dt
from decimal import Decimal

from sqlalchemy import Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class FormatConstants(Base):
    """One row per draftable format: a set plus a 17Lands event type.

    Keyed by both because Premier and Traditional Draft are different
    formats with different match structures, and `card_archetype_stats` and
    `archetype_stats` will be keyed the same way -- anything else invites a
    silent mismatch where the constants come from one event type and the
    card statistics from another.

    Percentage-point values are `Numeric`, not `Float`: these are
    hand-authored decimal constants where binary drift would be silent and
    confusing to anyone reading the table. Callers convert with `float()` at
    the boundary, since the fitness function is float throughout.

    Deliberately no foreign key to `sets`: a row here can be written before
    the set has been ingested, and the seeded HOB row below would otherwise
    depend on ingest order.
    """

    __tablename__ = "format_constants"

    set_code: Mapped[str] = mapped_column(String(8), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(32), primary_key=True)

    # The format's average game-in-hand win rate, and how far below it a card
    # has to fall to be worth no more than filler. `replacement_offset`'s only
    # reader since ADR 0012 is the openness gate.
    format_avg_wr: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    replacement_offset: Mapped[Decimal] = mapped_column(Numeric(5, 2))

    # ADR 0012's commitment tax, in pp. The only column here with no
    # measurable basis: every other value is measured or structural, and this
    # one is a judgement call whose only validation is how real drafts score.
    tax_value: Mapped[Decimal] = mapped_column(Numeric(5, 2))

    # 14 for HOB. Note this is picks, not cards opened: BoosterTutor's
    # CLAUDE.md still says a draft is 45 picks, which is wrong for HOB (42).
    picks_per_pack: Mapped[int] = mapped_column(Integer())

    # What a winning deck in this format looks like (ADR 0010), measured from
    # the 17Lands game data by scripts/derive_target_curve.py in DraftDouble.
    target_creatures: Mapped[int] = mapped_column(Integer())
    target_removal: Mapped[int] = mapped_column(Integer())

    # Non-land cards wanted at each mana value, 7+ counted with the sixes.
    # Six columns rather than JSONB or a child table because the six buckets
    # are structure, not data: the curve term clamps to 1..6 and the deriving
    # script hardcodes the same range, so a variable-length representation
    # would express a flexibility the code does not have.
    target_curve_1: Mapped[int] = mapped_column(Integer())
    target_curve_2: Mapped[int] = mapped_column(Integer())
    target_curve_3: Mapped[int] = mapped_column(Integer())
    target_curve_4: Mapped[int] = mapped_column(Integer())
    target_curve_5: Mapped[int] = mapped_column(Integer())
    target_curve_6: Mapped[int] = mapped_column(Integer())

    # The land targets of ADR 0028 s4: `land_target_low` lands for a deck whose
    # nonland cards average under `land_low_below_mv`, `land_target_high`
    # from `land_high_from_mv` up, `land_target_mid` between. Equal cuts
    # leave no middle band. Measured from the game dump by
    # scripts/derive_land_targets.py, which prints; a person transcribes.
    land_target_low: Mapped[int] = mapped_column(Integer())
    land_target_mid: Mapped[int] = mapped_column(Integer())
    land_target_high: Mapped[int] = mapped_column(Integer())
    land_low_below_mv: Mapped[Decimal] = mapped_column(Numeric(4, 2))
    land_high_from_mv: Mapped[Decimal] = mapped_column(Numeric(4, 2))

    # Free text, because one row's values have mixed provenance: the curve
    # targets are script-derived, `format_avg_wr` measured, `picks_per_pack`
    # structural and `tax_value` hand-picked. A known compromise; per-column
    # provenance is the upgrade if this becomes unwieldy.
    source: Mapped[str] = mapped_column(Text())

    updated_at: Mapped[dt.datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
