"""Load a format's `PrimerFacts`: the I/O half of `briefing/primer.py`.

Read from the newest Stats Snapshot (or the one given, so a practice draft
is explained with its own numbers, ADR 0020): every colour pair's row in
`archetype_stats`, and each colour's best mono-coloured commons from
`card_draft_stats`, among cards with at least `FitnessConfig.min_games`
games in hand, so a thin sample never tops the list.
"""

import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .analysis.fitness import FitnessConfig
from .briefing.primer import COLOURS, ArchetypeRate, CommonRate, PrimerFacts
from .models import ArchetypeStats, Card, CardDraftStats, CardPrint, FormatConstants

COMMONS_PER_COLOUR = 5


def load_primer_facts(
    session: Session,
    set_code: str,
    event_type: str,
    snapshot_date: dt.date | None = None,
) -> PrimerFacts:
    if snapshot_date is None:
        snapshot_date = session.scalar(
            select(func.max(ArchetypeStats.snapshot_date)).where(
                ArchetypeStats.set_code == set_code,
                ArchetypeStats.event_type == event_type,
            )
        )
    if snapshot_date is None:
        raise LookupError(f"{set_code} {event_type} has no archetype statistics")
    constants = session.get(FormatConstants, (set_code, event_type))
    if constants is None:
        raise LookupError(f"{set_code} {event_type} has no format_constants row")

    archetypes = [
        ArchetypeRate(archetype=row.archetype, win_rate=row.win_rate, games=row.games)
        for row in session.execute(
            select(ArchetypeStats).where(
                ArchetypeStats.set_code == set_code,
                ArchetypeStats.event_type == event_type,
                ArchetypeStats.snapshot_date == snapshot_date,
                ArchetypeStats.win_rate.is_not(None),
            )
        ).scalars()
        if row.win_rate is not None
    ]

    commons = session.execute(
        select(Card.name, Card.colors, CardDraftStats.gih_wr, CardDraftStats.gih_games)
        .join(CardDraftStats, CardDraftStats.oracle_id == Card.oracle_id)
        .join(
            CardPrint,
            (CardPrint.oracle_id == Card.oracle_id) & (CardPrint.set_code == set_code),
        )
        .where(
            CardDraftStats.set_code == set_code,
            CardDraftStats.event_type == event_type,
            CardDraftStats.snapshot_date == snapshot_date,
            CardDraftStats.gih_wr.is_not(None),
            CardDraftStats.gih_games >= FitnessConfig().min_games,
            CardPrint.rarity == "common",
        )
        .distinct()
    ).all()
    top: dict[str, list[CommonRate]] = {}
    for colour in COLOURS:
        mono = sorted(
            (c for c in commons if c.colors == colour),
            key=lambda c: (-c.gih_wr, c.name),
        )
        top[colour] = [
            CommonRate(name=c.name, gih_wr=c.gih_wr, games=c.gih_games)
            for c in mono[:COMMONS_PER_COLOUR]
        ]

    return PrimerFacts(
        set_code=set_code,
        event_type=event_type,
        stats_snapshot=snapshot_date,
        format_avg_wr=float(constants.format_avg_wr),
        archetypes=archetypes,
        top_commons=top,
    )
