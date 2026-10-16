"""Who may call Claude: the Admin Key until Phase 6 (ADR 0031 s2).

Two FastAPI dependencies read the `X-Admin-Key` header:

- `optional_coach` gives a `Coached` caller, or None for an anonymous one.
  The deck endpoint uses it: anonymous decks are rated as before.
- `require_coach` refuses an anonymous caller. The Pick Note endpoint and
  the stored-prose endpoint use it.

The endpoints and `ReviewService` only see the `Coached` value, never the
header. Phase 6 replaces "a valid admin key" with "a signed-in user" in
these two functions and the endpoints stay as they are. Until then
`user_id` is None: an admin-key review belongs to no user (ADR 0031 s5).
"""

import hmac
import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header

from ..config import settings
from .errors import ReviewError


@dataclass(frozen=True)
class Coached:
    """A caller allowed Claude's prose, and whose reviews are stored."""

    # The signed-in user from Phase 6. None for an admin-key call, which is
    # also what its `llm_calls` rows record (ADR 0031 s2).
    user_id: uuid.UUID | None


def admin_key_matches(given: str, expected: str | None) -> bool:
    """Whether `given` is the Admin Key. Always False when none is configured.

    `hmac.compare_digest` takes as long for a near miss as for a wild guess,
    so the response time can't be used to guess the key a letter at a time.
    """
    if not expected:
        return False
    return hmac.compare_digest(given.encode(), expected.encode())


def optional_coach(
    x_admin_key: Annotated[str | None, Header()] = None,
) -> Coached | None:
    """None without the header; a `Coached` caller with the right key.

    A wrong key is an error rather than "anonymous", so an admin who mistyped
    it hears so instead of quietly getting the anonymous page.
    """
    if x_admin_key is None:
        return None
    expected = settings.admin_key
    if not admin_key_matches(
        x_admin_key, expected.get_secret_value() if expected else None
    ):
        raise ReviewError("not_authorised", "That admin key isn't right.")
    return Coached(user_id=None)


def require_coach(
    caller: Annotated[Coached | None, Depends(optional_coach)],
) -> Coached:
    """A `Coached` caller, or a 401: this endpoint writes Claude's prose."""
    if caller is None:
        raise ReviewError(
            "not_authorised", "Sign in for a coach's note and a Draft Summary."
        )
    return caller
