"""The one 17lands.com request BoosterTutor makes: a single draft's replay.

ADR 0023 sets its limits: only when a user submits a link, the identifying
User-Agent, a short timeout, and no retrying a 4xx. The other two limits
(one fetch per draft, cached; a rate limit per client) are kept by
`ReviewService.import_draft`, the Replay Cache and `rate_limit.py`.

The parsing is pure and lives in `parsing/seventeen_lands.py`.
"""

import json
from typing import Any

from ..ingest.fetching import FetchError, HTTPStatusError, fetch_json_bytes
from ..parsing.errors import DraftInputError

DRAFT_URL = "https://www.17lands.com/data/draft?draft_id={draft_id}"
METADATA_URL = "https://www.17lands.com/data/event_metadata?draft_id={draft_id}"

# A user is waiting, so give up quickly: 15 seconds, two attempts at most
# (the second only after a 5xx or a network error).
TIMEOUT_SECONDS = 15
MAX_ATTEMPTS = 2


def fetch_seventeen_lands_draft(draft_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """The draft payload and its event metadata, or `DraftInputError`.

    Metadata first: it is tiny, and a draft 17Lands can't find fails before
    the larger pick log is requested.
    """
    metadata = _fetch_json(METADATA_URL.format(draft_id=draft_id))
    draft = _fetch_json(DRAFT_URL.format(draft_id=draft_id))
    return draft, metadata


def _fetch_json(url: str) -> dict[str, Any]:
    try:
        raw = fetch_json_bytes(url, max_attempts=MAX_ATTEMPTS, timeout=TIMEOUT_SECONDS)
    except HTTPStatusError as exc:
        if exc.status == 404:
            # 17Lands says {"message": "We can't seem to find that draft...",
            # "status": "error"}. It does not distinguish a private draft from
            # one that doesn't exist, so neither can we.
            raise DraftInputError(
                "draft_not_found",
                "17Lands can't find that draft. It may be private, or the link "
                "may be wrong.",
            ) from exc
        raise DraftInputError(
            "upstream_failure", f"17Lands answered HTTP {exc.status}"
        ) from exc
    except FetchError as exc:
        raise DraftInputError("upstream_failure", "17Lands didn't answer") from exc

    try:
        payload = json.loads(raw)
    except ValueError as exc:
        raise DraftInputError(
            "upstream_failure", "17Lands answered with something that isn't JSON"
        ) from exc
    if not isinstance(payload, dict):
        raise DraftInputError(
            "upstream_failure", "17Lands answered in an unexpected shape"
        )
    return payload
