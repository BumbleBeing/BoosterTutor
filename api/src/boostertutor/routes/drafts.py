"""The Draft Review endpoints (ADR 0031): HTTP in, `ReviewService` out.

For anyone: import, review and deck ratings, Python-only, nothing stored
per person. For a coached caller (`review/access.py`; until Phase 6, a
request with the Admin Key): Claude's Pick Notes and Draft Summary, stored.
The endpoints never look at how the caller was let in, only at the
`Coached` value the dependency hands them.

The rules live in `review/service.py`. These functions only read the request,
and a failure needs no handling here: `ReviewError` is turned into a
response by the handler in `main.py`.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict

from ..config import settings
from ..review.access import Coached, optional_coach, require_coach
from ..review.postgres import get_review_service
from ..review.rate_limit import client_key
from ..review.service import ReviewService
from ..schemas.coach import CoachedDeckReview, CoachNote, CoachReview
from ..schemas.deck_submission import SubmittedDeck
from ..schemas.draft_review import DraftReview, ImportResponse

Service = Annotated[ReviewService, Depends(get_review_service)]
MaybeCoached = Annotated[Coached | None, Depends(optional_coach)]
MustBeCoached = Annotated[Coached, Depends(require_coach)]

router = APIRouter(prefix="/api/drafts", tags=["drafts"])


class ImportRequest(BaseModel):
    # Unknown fields are refused: the pasted-log input is gone (ADR 0031 s3),
    # and a request that still sends it should hear so.
    model_config = ConfigDict(extra="forbid")

    link: str  # a 17Lands URL or a bare draft id


def _client(request: Request) -> str:
    """The anonymous per-IP key the rate limits count against."""
    return client_key(
        request.client.host if request.client else None,
        request.headers.get("x-forwarded-for"),
        proxy_hops=settings.proxy_hops,
        salt=settings.client_hash_salt,
    )


@router.post("", response_model=ImportResponse)
def post_draft(
    body: ImportRequest, request: Request, service: Service
) -> ImportResponse:
    """Import a 17Lands draft into the Replay Cache, fetching it if new."""
    return service.import_draft(body.link, _client(request))


@router.get("/{draft_id}", response_model=DraftReview)
def get_draft(draft_id: str, service: Service) -> DraftReview:
    """Every pick graded, recomputed from today's statistics."""
    return service.review(draft_id)


@router.post("/{draft_id}/deck", response_model=CoachedDeckReview)
def post_deck(
    draft_id: str,
    body: SubmittedDeck,
    request: Request,
    caller: MaybeCoached,
    service: Service,
) -> CoachedDeckReview:
    """Rate a Submitted Deck. An anonymous deck is not stored (ADR 0031 s5);
    a coached caller's is, and their first gets a Draft Summary."""
    return service.rate_deck(draft_id, body, _client(request), caller)


@router.post("/{draft_id}/picks/{n}/note", response_model=CoachNote)
def post_pick_note(
    draft_id: str, n: int, caller: MustBeCoached, service: Service
) -> CoachNote:
    """The Pick Note for the `n`th pick (1 is P1p1), written by Claude if new.

    `caller` comes before `service`: FastAPI resolves dependencies in order,
    so an anonymous request is refused before any database work.
    """
    return service.pick_note(draft_id, n, caller)


@router.get("/{draft_id}/coach", response_model=CoachReview)
def get_coach_review(
    draft_id: str, caller: MustBeCoached, service: Service
) -> CoachReview:
    """The caller's stored Pick Notes, Draft Summary and decks. No Claude call."""
    return service.coach_review(draft_id, caller)
