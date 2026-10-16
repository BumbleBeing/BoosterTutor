"""What `POST /api/drafts/{id}/deck` takes and returns (ADR 0025, Phase 5c).

Like the review, it is all Python: the Deck Ratings, the facts behind them
and the cards they name. Nothing here is prose and nothing is stored.
"""

import uuid

from pydantic import BaseModel, ConfigDict

from .deck import DeckMetrics, DeckRatings
from .draft_review import CardInfo


class SubmittedDeck(BaseModel):
    """The 40 cards, as the deck builder holds them."""

    # Unknown fields are refused, so a typo can't silently drop part of a deck.
    model_config = ConfigDict(extra="forbid")

    # The pool cards played, one entry per copy; no basic lands.
    cards: list[uuid.UUID]
    # Basic lands by colour letter ("W", "U", "B", "R", "G"): how many of each.
    basics: dict[str, int]


class DeckReview(BaseModel):
    ratings: DeckRatings
    metrics: DeckMetrics
    # Colour Sources (ADR 0028 s2) for each colour the deck's spells use.
    # Fractional, because a Fixer counts for less than a land.
    colour_sources: dict[str, float]
    # Every card `metrics` names (the short spell, the notable omission, the
    # firings), so the panel can show names without a second request.
    cards: dict[uuid.UUID, CardInfo]
