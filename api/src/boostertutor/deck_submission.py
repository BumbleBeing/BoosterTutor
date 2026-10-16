"""A Submitted Deck, checked against the draft's pool and rated.

The glue between the cached draft and the pure deck analysis. Nothing is
stored and no Claude call is made (ADR 0031 s5).
"""

import uuid
from collections.abc import Callable, Iterable

from .analysis.deck import deck_metrics
from .analysis.deck_rating import DeckRatingModel, rate_deck
from .analysis.draft import FormatInputs
from .analysis.mana import colour_sources
from .schemas import DraftLog
from .schemas.deck import deck_from_pool
from .schemas.deck_submission import DeckReview, SubmittedDeck
from .schemas.draft_review import CardInfo


def pool_of(log: DraftLog, inputs: FormatInputs) -> list[uuid.UUID]:
    """The cards a deck can be built from: every pick but the basic lands.

    A basic land drafted is pruned (ADR 0025 s1); the builder's five buttons
    add basics instead.
    """
    return [
        p.picked
        for p in log.picks
        if not inputs.cards.get(p.picked, {})
        .get("type_line", "")
        .startswith("Basic Land")
    ]


def rate_submitted_deck(
    submitted: SubmittedDeck,
    log: DraftLog,
    inputs: FormatInputs,
    model: DeckRatingModel | None,
    card_infos: Callable[[Iterable[uuid.UUID]], dict[uuid.UUID, CardInfo]],
) -> DeckReview:
    """The deck's ratings, or `DeckError` saying why it can't be a deck."""
    deck = deck_from_pool(
        pool_of(log, inputs), main=submitted.cards, basics=submitted.basics
    )
    metrics = deck_metrics(deck, inputs)

    named = {metrics.mana_short_spell, *(f.oracle_id for f in metrics.synergy_firings)}
    for f in metrics.synergy_firings:
        named.update(f.contributing)
    if metrics.notable_omission is not None:
        named.update(
            (metrics.notable_omission.oracle_id, metrics.notable_omission.instead_of)
        )
    named.discard(None)

    return DeckReview(
        ratings=rate_deck(metrics, model),
        metrics=metrics,
        colour_sources=colour_sources(
            [inputs.cards[oid] for oid in deck.main], deck.basics, inputs.mana_sources
        ),
        cards=card_infos({oid for oid in named if oid is not None}),
    )
