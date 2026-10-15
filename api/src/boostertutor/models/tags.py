"""The hand-authored tag taxonomy, and the synergy baseline measured from it.

Everything else in the database can be rebuilt by re-running an ingest. The
taxonomy cannot: it is human judgement (ADR 0004, 0006, 0009). Its system of
record is therefore a git-tracked JSON file per set, `api/data/taxonomy/`,
and these tables are loaded from it (`python -m boostertutor.ingest
taxonomy`). Editing happens in DraftDouble's tagger, which writes the same
file format, so `git diff` stays the change log for every tag and weight.

Tags are authored per set, so `set_code` is part of every key. There is no
tag hierarchy: a card that makes Treasure is tagged `artifact` outright, so
`card_tags` is the complete truth about a card and nothing is inferred.

No foreign key to `sets`, as with `format_constants`: a taxonomy can be
loaded for a set before or after its cards, in either order.
"""

import uuid

from sqlalchemy import (
    CheckConstraint,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

TAG_KINDS = ("enabler", "payoff", "both", "self_payoff")


class Tag(Base):
    """The vocabulary: one row per tag a set uses.

    `self_payoff` is the odd one out: a tag that synergises only with itself,
    for a card that rewards more copies of the same card. It is almost always
    a vocabulary of one card, named after it, and its weight lives on the
    diagonal of `tag_pairs`.
    """

    __tablename__ = "tags"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('enabler', 'payoff', 'both', 'self_payoff')", name="kind_known"
        ),
    )

    set_code: Mapped[str] = mapped_column(String(8), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), primary_key=True)  # snake_case
    kind: Mapped[str] = mapped_column(String(16))
    notes: Mapped[str | None] = mapped_column(Text())


class TagPair(Base):
    """A synergy edge: one enabler tag coupled to one payoff tag (ADR 0006).

    Directional, and legitimately cyclic: a sacrifice outlet and a death
    trigger enable each other, which is two rows with their own coefficients.
    This table is the weighted graph; the tagger's coefficient grid is its
    adjacency matrix.

    The diagonal (enabler = payoff) is reserved for `self_payoff` tags, and a
    `self_payoff` tag may appear nowhere else. The taxonomy loader checks
    both, since a CHECK constraint cannot see the `tags` table.
    """

    __tablename__ = "tag_pairs"
    __table_args__ = (
        # Named by hand: the naming convention uses only the first column,
        # which would give both keys the same name.
        ForeignKeyConstraint(
            ["set_code", "enabler"],
            ["tags.set_code", "tags.name"],
            ondelete="CASCADE",
            name="fk_tag_pairs_enabler_tags",
        ),
        ForeignKeyConstraint(
            ["set_code", "payoff"],
            ["tags.set_code", "tags.name"],
            ondelete="CASCADE",
            name="fk_tag_pairs_payoff_tags",
        ),
        CheckConstraint("decay >= 0 AND decay <= 1", name="decay_in_range"),
    )

    set_code: Mapped[str] = mapped_column(String(8), primary_key=True)
    enabler: Mapped[str] = mapped_column(String(64), primary_key=True)
    payoff: Mapped[str] = mapped_column(String(64), primary_key=True)
    # How much the edge is worth, in coefficient units: the fitness function
    # multiplies by `synergy_weight` (pp per unit).
    coefficient: Mapped[float] = mapped_column(Float())
    # ADR 0009: how much of the previous copy's value each further copy of the
    # complementary tag is worth, 0..1. The effective count is the geometric
    # series 1 + d + d^2 + ...: at 1.0 every copy counts in full, at 0.5 the
    # count converges on 2, at 0.0 only the first copy counts.
    decay: Mapped[float] = mapped_column(Float(), default=0.5)
    notes: Mapped[str | None] = mapped_column(Text())


class CardTag(Base):
    """Which tags are on which card. Deleting a tag removes it from every card."""

    __tablename__ = "card_tags"
    __table_args__ = (
        ForeignKeyConstraint(
            ["set_code", "tag"], ["tags.set_code", "tags.name"], ondelete="CASCADE"
        ),
        Index("ix_card_tags_set_tag", "set_code", "tag"),
    )

    oracle_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cards.oracle_id", ondelete="CASCADE"),
        primary_key=True,
    )
    set_code: Mapped[str] = mapped_column(String(8), primary_key=True)
    tag: Mapped[str] = mapped_column(String(64), primary_key=True)


class SynergyBaseline(Base):
    """How many complements a card usually finds in a pool (ADR 0017).

    Synergy is scored as a margin over what is typical: a firing is worth
    `coefficient x (n_eff - E[n_eff | card, pack, edge])`. A card's GIH WR
    already prices its typical synergy, so paying the level would pay twice.

    Stored as a **histogram of complement counts**, not as the expectation:
    the expensive input (pool composition across every pick in the 17Lands
    draft dump) does not depend on any weight, so re-tuning a coefficient or
    a decay never makes this stale. The expectation is computed at load time
    for whatever decay each edge carries. The n = 0 rows are kept, because
    the expectation's denominator is every appearance of the card.

    Measured, not authored, so unlike the three tables above it is rebuilt
    from the dump rather than loaded from the taxonomy file. No foreign key
    to `tag_pairs`: an edge deleted after measuring is skipped at load.
    """

    __tablename__ = "synergy_baseline"
    __table_args__ = (Index("ix_synergy_baseline_format", "set_code", "event_type"),)

    set_code: Mapped[str] = mapped_column(String(8), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(32), primary_key=True)
    oracle_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cards.oracle_id", ondelete="CASCADE"),
        primary_key=True,
    )
    pack_number: Mapped[int] = mapped_column(Integer(), primary_key=True)  # 1-based
    enabler: Mapped[str] = mapped_column(String(64), primary_key=True)
    payoff: Mapped[str] = mapped_column(String(64), primary_key=True)
    # Which end of the edge the card is on: a card holding both tags fires
    # the edge twice, once from each end.
    tag_on_card: Mapped[str] = mapped_column(String(64), primary_key=True)
    complement_count: Mapped[int] = mapped_column(Integer(), primary_key=True)  # n
    observations: Mapped[int] = mapped_column(Integer())  # how often that n was seen
