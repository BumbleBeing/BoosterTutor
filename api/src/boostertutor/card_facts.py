"""Load the `CardFacts` a brief needs, for exactly the cards in an analysis.

The I/O half of `briefing/`, which is pure (ADR 0024 s5). Names, costs, type
lines and oracle text come from `cards`; rarity from `card_prints`, because
rarity belongs to a printing, not to a card.
"""

import uuid
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from .briefing.card_facts import CardFacts
from .models import Card, CardPrint
from .schemas.draft_analysis import DraftAnalysis


def analysis_cards(analysis: DraftAnalysis) -> set[uuid.UUID]:
    """Every card a brief for this draft could name: the packs and the pool."""
    return {c.oracle_id for pick in analysis.picks for c in pick.cards}


def load_card_facts(
    session: Session, set_code: str, oracle_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, CardFacts]:
    """`CardFacts` for each card, or a `LookupError` naming how many are missing.

    A card's rarity is its rarity in `set_code` when it was printed there.
    A bonus-sheet card (a Special Guest, say) was printed in its own set
    instead, so it takes that printing's rarity.
    """
    ids = set(oracle_ids)
    cards = session.execute(select(Card).where(Card.oracle_id.in_(ids))).scalars()
    by_id = {card.oracle_id: card for card in cards}
    rarity: dict[uuid.UUID, str] = {}
    prints = session.execute(
        select(CardPrint.oracle_id, CardPrint.set_code, CardPrint.rarity)
        .where(CardPrint.oracle_id.in_(ids))
        # Deterministic: the draft set's own printing wins, then by set code.
        .order_by(
            CardPrint.oracle_id, CardPrint.set_code != set_code, CardPrint.set_code
        )
    )
    for oracle_id, _, card_rarity in prints:
        rarity.setdefault(oracle_id, card_rarity)

    missing = ids - (by_id.keys() & rarity.keys())
    if missing:
        raise LookupError(f"{len(missing)} card(s) have no card or printing row")
    return {
        oid: CardFacts(
            name=card.name,
            mana_cost=card.mana_cost,
            rarity=rarity[oid],
            type_line=card.type_line,
            oracle_text=card.oracle_text,
        )
        for oid, card in by_id.items()
    }
