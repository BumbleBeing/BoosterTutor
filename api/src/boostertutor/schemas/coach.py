"""Claude's prose as the API returns it (ADR 0031 s2, s5): Phase 5d.

Only a caller allowed Claude gets any of this: until Phase 6, a request
with the Admin Key. The anonymous review has no prose field at all.

Each piece of prose says which Stats Snapshot it was written against and
whether today's differs (`stale`), so the page can tag it "written against
older stats". The verdict, gap and best card beside a note are not here:
the page takes them from the review, which Python recomputes every time.
"""

import datetime as dt

from pydantic import BaseModel

from ..briefing import NoteKind
from .deck_submission import DeckReview, SubmittedDeck


class SavedNote(BaseModel):
    """One Pick Note, as stored."""

    pack_number: int
    pick_number: int
    kind: NoteKind
    note: str
    prompt_version: str
    model: str
    stats_snapshot: dt.date  # the Stats Snapshot it was written against


class CoachNote(SavedNote):
    """One Pick Note, as the page gets it."""

    stale: bool  # written against a Stats Snapshot other than today's


class SummaryKeyPick(BaseModel):
    pack_number: int
    pick_number: int


class SavedSummary(BaseModel):
    """The Draft Summary (ADR 0030 s1), as stored."""

    draft_arc: str
    deck: str
    lesson: str
    key_picks: list[SummaryKeyPick]
    prompt_version: str
    model: str
    stats_snapshot: dt.date


class CoachSummary(SavedSummary):
    """The Draft Summary, about `CoachReview.reviewed_deck`, as the page gets it."""

    stale: bool


class SavedReview(BaseModel):
    """Everything stored about one draft for one owner."""

    notes: list[SavedNote]
    summary: SavedSummary | None
    reviewed_deck: SubmittedDeck | None
    current_deck: SubmittedDeck | None


class CoachReview(BaseModel):
    """Everything stored about one draft for this caller: `GET .../coach`."""

    notes: list[CoachNote]  # in pick order
    summary: CoachSummary | None
    reviewed_deck: SubmittedDeck | None  # the deck the summary is about
    current_deck: SubmittedDeck | None  # the latest deck submitted


class ProseUnavailable(BaseModel):
    """Why a deck came back with Deck Ratings but no Draft Summary.

    `kind` is an error kind (`review/errors.py`): "coach_retired" or
    "prose_failed". The ratings are still good; the next deck tries again.
    """

    kind: str
    message: str


class CoachedDeckReview(DeckReview):
    """What `POST /api/drafts/{id}/deck` returns.

    An anonymous deck gets the Deck Ratings and nulls below. A coached
    caller's first deck also gets its Draft Summary, or the reason it has
    none; later decks are stored as `current_deck` and get ratings only.
    """

    summary: CoachSummary | None = None
    summary_unavailable: ProseUnavailable | None = None
