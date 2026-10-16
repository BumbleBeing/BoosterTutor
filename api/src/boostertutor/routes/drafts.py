"""POST /api/drafts and GET /api/drafts/{id} (ADR 0031, Phase 5a).

Anonymous and Python-only: no Claude call, no prose, nothing per-user stored.
"""

import re
from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from ..config import settings
from ..draft_import import import_draft
from ..draft_review import build_review
from ..draft_services import DraftServices, get_services
from ..format_inputs import FormatNotReady
from ..parsing.errors import DraftInputError
from ..rate_limit import RateLimited, client_key
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


@router.post("", response_model=ImportResponse)
def post_draft(
    body: ImportRequest,
    request: Request,
    services: Services,
) -> ImportResponse:
    client = client_key(
        request.client.host if request.client else None,
        request.headers.get("x-forwarded-for"),
        proxy_hops=settings.proxy_hops,
        salt=settings.client_hash_salt,
    )
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
        inputs = services.inputs_for(log.set_code, log.event_type)
    except FormatNotReady:
        _fail(
            503,
            "format_not_ready",
            f"There are no statistics for {log.set_code.upper()} "
            f"{log.event_type} yet. Please try again later.",
        )
    # Verdicts are recomputed here, every time, from the cached log and the
    # current statistics (ADR 0031 s5).
    return build_review(
        log, inputs, lambda ids: services.card_infos_for(log.set_code, ids)
    )
