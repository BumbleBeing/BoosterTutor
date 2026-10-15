"""Load a format's `FormatInputs` from the database, for `analyze_draft`.

The only database reads the draft analysis needs, in one place. Every other
step of the analysis is pure (`analysis/draft.py`).

A format is a set plus a 17Lands event type ("hob", "PremierDraft"). It can
be analysed only when it has statistics and a `format_constants` row. A set
with no tag taxonomy is analysed with synergy and removal scarcity at zero
(`DraftAnalysis.has_taxonomy` says so). A taxonomy with no synergy baseline
is refused: the fitted synergy weight assumes the margin form (ADR 0017), so
without a baseline every tagged card would be over-credited.
"""

import datetime as dt
import uuid
from collections import defaultdict
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .analysis import fitness as fx
from .analysis.draft import FormatInputs, fitness_card, synergy_expectations
from .models import (
    BoosterCard,
    Card,
    CardDraftStats,
    CardTag,
    FormatConstants,
    SynergyBaseline,
    TagPair,
)


class FormatNotReady(LookupError):
    """The format is missing something the analysis needs. The message says what."""


def load_cards(session: Session, set_code: str) -> dict[uuid.UUID, dict[str, Any]]:
    """A `fitness_card` for every card the set's packs can hold, with its tags."""
    tags: dict[uuid.UUID, list[str]] = defaultdict(list)
    for oracle_id, tag in session.execute(
        select(CardTag.oracle_id, CardTag.tag)
        .where(CardTag.set_code == set_code)
        .order_by(CardTag.tag)
    ):
        tags[oracle_id].append(tag)

    rows = session.execute(
        select(Card)
        .join(BoosterCard, BoosterCard.oracle_id == Card.oracle_id)
        .where(BoosterCard.set_code == set_code)
    ).scalars()
    return {
        card.oracle_id: fitness_card(
            card.oracle_id,
            type_line=card.type_line,
            mana_cost=card.mana_cost,
            cmc=card.cmc,
            colors=card.colors,
            color_identity=card.color_identity,
            tags=tags.get(card.oracle_id, []),
        )
        for card in rows
    }


def load_edges(session: Session, set_code: str) -> list[dict[str, Any]]:
    """The authored synergy edges, in the shape `fitness.synergy` reads."""
    return [
        {
            "enabler": p.enabler,
            "payoff": p.payoff,
            "coefficient": p.coefficient,
            "decay": p.decay,
        }
        for p in session.execute(
            select(TagPair).where(TagPair.set_code == set_code)
        ).scalars()
    ]


def fitness_config(row: FormatConstants) -> fx.FitnessConfig:
    """The global settings, with this format's values swapped in (ADR 0013).

    `Numeric` columns come back as `Decimal`, and the fitness function is
    float throughout, so each is converted here at the boundary.
    """
    return fx.FitnessConfig(
        tax_value=float(row.tax_value),
        target_removal=row.target_removal,
        target_curve={
            1: row.target_curve_1,
            2: row.target_curve_2,
            3: row.target_curve_3,
            4: row.target_curve_4,
            5: row.target_curve_5,
            6: row.target_curve_6,
        },
    )


def load_format_inputs(
    session: Session, set_code: str, event_type: str
) -> FormatInputs:
    constants = session.get(FormatConstants, (set_code, event_type))
    if constants is None:
        raise FormatNotReady(f"{set_code}/{event_type} has no format_constants row")

    snapshot: dt.date | None = session.scalar(
        select(func.max(CardDraftStats.snapshot_date)).where(
            CardDraftStats.set_code == set_code,
            CardDraftStats.event_type == event_type,
        )
    )
    if snapshot is None:
        raise FormatNotReady(f"{set_code}/{event_type} has no 17Lands statistics yet")
    overall = {
        s.oracle_id: (s.gih_wr, s.gih_games)
        for s in session.execute(
            select(CardDraftStats).where(
                CardDraftStats.set_code == set_code,
                CardDraftStats.event_type == event_type,
                CardDraftStats.snapshot_date == snapshot,
            )
        ).scalars()
        if s.gih_wr is not None
    }

    edges = load_edges(session, set_code)
    histogram = [
        {
            "oracle_id": b.oracle_id,
            "pack_number": b.pack_number,
            "enabler": b.enabler,
            "payoff": b.payoff,
            "tag_on_card": b.tag_on_card,
            "complement_count": b.complement_count,
            "observations": b.observations,
        }
        for b in session.execute(
            select(SynergyBaseline).where(
                SynergyBaseline.set_code == set_code,
                SynergyBaseline.event_type == event_type,
            )
        ).scalars()
    ]
    if edges and not histogram:
        raise FormatNotReady(
            f"{set_code} has tag pairs but no synergy baseline for {event_type}: "
            "run `python -m boostertutor.ingest synergy-baseline`"
        )

    return FormatInputs(
        set_code=set_code,
        event_type=event_type,
        stats_snapshot=snapshot,
        cards=load_cards(session, set_code),
        stats=fx.Stats(format_avg_wr=float(constants.format_avg_wr), overall=overall),
        edges=edges,
        baseline=synergy_expectations(histogram, edges),
        cfg=fitness_config(constants),
    )
