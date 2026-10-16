"""The Draft Review endpoints (ADR 0031): HTTP in, `ReviewService` out.

Anonymous and Python-only: no Claude call, no prose, nothing per-user stored.
The rules live in `review/service.py`. These functions only read the request,
and a failure needs no handling here: `ReviewError` is turned into a
response by the handler in `main.py`.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict

from ..config import settings
from ..review.postgres import get_review_service
from ..review.rate_limit import client_key
from ..review.service import ReviewService
from ..schemas.deck_submission import DeckReview, SubmittedDeck
from ..schemas.draft_review import DraftReview, ImportResponse

Service = Annotated[ReviewService, Depends(get_review_service)]

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


@router.post("/{draft_id}/deck", response_model=DeckReview)
def post_deck(
    draft_id: str, body: SubmittedDeck, request: Request, service: Service
) -> DeckReview:
    """Rate a Submitted Deck. Nothing is stored (ADR 0031 s5)."""
    return service.rate_deck(draft_id, body, _client(request))
