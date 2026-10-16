"""POST /api/drafts and GET /api/drafts/{id} (ADR 0031, Phase 5a).

Anonymous and Python-only: no Claude call, no prose, nothing per-user stored.
"""

import re
from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from ..config import settings
from ..deck_submission import rate_submitted_deck
from ..draft_import import import_draft
from ..draft_review import build_review
from ..draft_services import DraftServices, get_services
from ..format_inputs import FormatNotReady, stats_event_type
from ..parsing.errors import DraftInputError
from ..rate_limit import RateLimited, client_key
from ..schemas.deck import DeckError
from ..schemas.deck_submission import DeckReview, SubmittedDeck
from ..schemas.draft_review import DraftReview

Services = Annotated[DraftServices, Depends(get_services)]

router = APIRouter(prefix="/api/drafts", tags=["drafts"])

# How each kind of failure is told to the client. The body is always
# `{"detail": {"kind", "message", "detail"}}`; the page switches on `kind`.
STATUS_BY_KIND = {
    "invalid_input": 422,
    "draft_not_found": 404,
    "unsupported_set": 422,
    "unsupported_format": 422,
    "unresolved_cards": 422,
    "malformed_draft": 422,
    "upstream_failure": 502,
}


class ImportRequest(BaseModel):
    # Unknown fields are refused: the pasted-log input is gone (ADR 0031 s3),
    # and a request that still sends it should hear so.
    model_config = ConfigDict(extra="forbid")

    link: str  # a 17Lands URL or a bare draft id


class ImportResponse(BaseModel):
    draft_id: str
    cached: bool  # True: 17Lands was not asked


def _fail(
    status: int, kind: str, message: str, headers: dict[str, str] | None = None
) -> NoReturn:
    raise HTTPException(
        status_code=status,
        detail={"kind": kind, "message": message, "detail": None},
        headers=headers,
    )


def _client(request: Request) -> str:
    """The anonymous per-IP key the limiters count against."""
    return client_key(
        request.client.host if request.client else None,
        request.headers.get("x-forwarded-for"),
        proxy_hops=settings.proxy_hops,
        salt=settings.client_hash_salt,
    )


@router.post("", response_model=ImportResponse)
def post_draft(
    body: ImportRequest,
    request: Request,
    services: Services,
) -> ImportResponse:
    client = _client(request)
    try:
        imported = import_draft(body.link, client, services)
    except RateLimited as exc:
        _fail(
            429,
            "rate_limited",
            "Too many drafts imported from 17Lands just now. Please try again "
            "in a little while.",
            headers={"Retry-After": str(exc.retry_after)},
        )
    except DraftInputError as exc:
        raise HTTPException(
            status_code=STATUS_BY_KIND[exc.kind], detail=exc.to_dict()
        ) from exc
    return ImportResponse(draft_id=imported.draft_id, cached=imported.cached)


DRAFT_ID_RE = re.compile(r"^[0-9a-f]{32}$")


@router.get("/{draft_id}", response_model=DraftReview)
def get_draft(draft_id: str, services: Services) -> DraftReview:
    if not DRAFT_ID_RE.match(draft_id):
        _fail(422, "invalid_input", "that isn't a 17Lands draft id")
    log = services.store.get(draft_id)
    if log is None:
        _fail(
            404,
            "draft_not_found",
            "That draft hasn't been imported yet. Submit its 17Lands link first.",
        )
    try:
        inputs = services.inputs_for(log.set_code, stats_event_type(log.event_type))
    except FormatNotReady:
        _fail(
            503,
            "format_not_ready",
            f"There are no statistics for {log.set_code.upper()} "
            f"{log.event_type} yet. Please try again later.",
        )
    # Verdicts are recomputed here, every time, from the cached log and the
    # current statistics (ADR 0031 s5).
    # A Traditional or Open draft is rated with the Premier statistics, so it
    # is analysed as one; the review still reports the event it really was.
    analysed = log.model_copy(update={"event_type": inputs.event_type})
    review = build_review(
        analysed, inputs, lambda ids: services.card_infos_for(log.set_code, ids)
    )
    review.event_type = log.event_type
    return review


@router.post("/{draft_id}/deck", response_model=DeckReview)
def post_deck(
    draft_id: str, body: SubmittedDeck, request: Request, services: Services
) -> DeckReview:
    """Rate a Submitted Deck. Anonymous: nothing is stored (ADR 0031 s5)."""
    if not DRAFT_ID_RE.match(draft_id):
        _fail(422, "invalid_input", "that isn't a 17Lands draft id")
    try:
        # Counted before the deck is checked, so a stream of bad decks runs
        # out too. The "deck:" prefix keeps this allowance apart from the
        # 17Lands fetch allowance in the same table.
        services.deck_limiter.check_and_record("deck:" + _client(request))
    except RateLimited as exc:
        _fail(
            429,
            "rate_limited",
            "Too many decks submitted just now. Please try again in a little while.",
            headers={"Retry-After": str(exc.retry_after)},
        )
    log = services.store.get(draft_id)
    if log is None:
        _fail(
            404,
            "draft_not_found",
            "That draft hasn't been imported yet. Submit its 17Lands link first.",
        )
    try:
        inputs = services.inputs_for(log.set_code, stats_event_type(log.event_type))
    except FormatNotReady:
        _fail(
            503,
            "format_not_ready",
            f"There are no statistics for {log.set_code.upper()} "
            f"{log.event_type} yet. Please try again later.",
        )
    model = services.deck_model_for(log.set_code, inputs.event_type)
    try:
        return rate_submitted_deck(
            body,
            log,
            inputs,
            model,
            lambda ids: services.card_infos_for(log.set_code, ids),
        )
    except DeckError as exc:
        _fail(422, "invalid_deck", str(exc))
