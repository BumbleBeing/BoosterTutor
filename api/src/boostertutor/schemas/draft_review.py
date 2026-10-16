"""What `GET /api/drafts/{id}` returns: everything the review page needs.

All of it is computed by Python from the cached log and the current
statistics. There is no prose here and no Claude field: the anonymous review
is the Python-only tier (ADR 0031 s1).
"""

import datetime as dt
import uuid

from pydantic import BaseModel

from .draft_analysis import DraftAnalysis


class CardInfo(BaseModel):
    """How to show one card: its face, not its statistics."""

    name: str
    mana_cost: str | None
    type_line: str
    cmc: float
    colors: str  # sorted WUBRG letters, "" for colourless
    rarity: str | None
    # Scryfall image URLs. The page loads them only when a pick is expanded.
    image_normal: str | None
    image_art_crop: str | None


class DraftReview(BaseModel):
    draft_id: str
    set_code: str
    event_type: str
    drafted_at: dt.datetime | None
    wins: int | None
    losses: int | None
    pack_size: int
    analysis: DraftAnalysis
    # How many picks got each verdict, for the summary above the timeline.
    verdict_counts: dict[str, int]
    # (pack, pick) of every Noted Pick, in draft order.
    noted_picks: list[tuple[int, int]]
    # Every card the analysis mentions, by oracle id.
    cards: dict[uuid.UUID, CardInfo]
    # The set's own basic lands by colour letter, so the deck builder can show
    # real card art. A colour the set has no printing of is absent.
    basic_lands: dict[str, CardInfo]
