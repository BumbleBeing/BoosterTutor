"""A cached draft plus today's statistics, as the review page's data."""

import uuid
from collections import Counter
from collections.abc import Callable, Iterable

from .analysis.draft import FormatInputs, analyze_draft
from .schemas import DraftLog
from .schemas.draft_review import CardInfo, DraftReview


def build_review(
    log: DraftLog,
    inputs: FormatInputs,
    card_infos: Callable[[Iterable[uuid.UUID]], dict[uuid.UUID, CardInfo]],
    basic_lands: dict[str, CardInfo],
) -> DraftReview:
    """Recompute every verdict. Nothing here is stored; see `models.replay`."""
    analysis = analyze_draft(log, inputs)

    mentioned = {
        oid
        for p in analysis.picks
        for oid in (p.picked, *(c.oracle_id for c in p.cards))
    }
    # The wheel tables name cards too (what came back, what the table took).
    for wheel in analysis.wheels:
        for lap in wheel.laps:
            mentioned.update(c.oracle_id for c in (*lap.wheeled, *lap.taken_by_table))
        mentioned.update(
            c.best_wheeled for c in wheel.colors if c.best_wheeled is not None
        )

    return DraftReview(
        draft_id=log.source_id or "",
        set_code=log.set_code,
        event_type=log.event_type,
        drafted_at=log.drafted_at,
        wins=log.wins,
        losses=log.losses,
        pack_size=log.pack_size,
        analysis=analysis,
        verdict_counts=dict(Counter(p.verdict for p in analysis.picks)),
        noted_picks=[(p.pack_number, p.pick_number) for p in analysis.picks if p.noted],
        cards=card_infos(mentioned),
        basic_lands=basic_lands,
    )
