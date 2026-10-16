"""Every way a Draft Review request can fail, as one exception (ADR 0031).

The routes catch nothing. `ReviewService` raises `ReviewError`, and one
handler in `main.py` turns it into the response the page reads:

    {"detail": {"kind": ..., "message": ..., "detail": ...}}

The page switches on `kind` to decide what to tell the person, so a kind is
a promise to the frontend (`web/src/lib/api/client.ts` lists the same ones).
"""

from typing import Any, Literal

from ..parsing.errors import DraftInputError

Kind = Literal[
    # From the parsers and the 17Lands fetch (`parsing/errors.py`).
    "invalid_input",
    "draft_not_found",
    "unsupported_set",
    "unsupported_format",
    "unresolved_cards",
    "malformed_draft",
    "upstream_failure",
    # From the service itself.
    "invalid_deck",  # the 40 cards aren't a legal deck from this pool
    "rate_limited",  # out of allowance; `retry_after` says for how long
    "format_not_ready",  # no statistics loaded for this set and event yet
]

# The HTTP status each kind is sent with.
STATUS: dict[Kind, int] = {
    "invalid_input": 422,
    "draft_not_found": 404,
    "unsupported_set": 422,
    "unsupported_format": 422,
    "unresolved_cards": 422,
    "malformed_draft": 422,
    # 17Lands failed, not us and not the user: a bad gateway.
    "upstream_failure": 502,
    "invalid_deck": 422,
    "rate_limited": 429,
    # Temporary: the nightly ingest will fill it in.
    "format_not_ready": 503,
}


class ReviewError(Exception):
    def __init__(
        self,
        kind: Kind,
        message: str,
        detail: Any = None,
        *,
        retry_after: int | None = None,
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.detail = detail  # optional extra data, e.g. unmatched card names
        self.retry_after = retry_after  # seconds; sent as a Retry-After header

    @classmethod
    def from_input(cls, exc: DraftInputError) -> "ReviewError":
        return cls(exc.kind, exc.message, exc.detail)

    @property
    def status(self) -> int:
        return STATUS[self.kind]

    def body(self) -> dict[str, Any]:
        return {"kind": self.kind, "message": self.message, "detail": self.detail}
