"""Getting a user's draft into a `DraftLog`: the I/O around `parsing/`.

The parsers are pure. This module does what they cannot: fetch a 17Lands
draft, and read from the database which cards a set's packs can hold.

The 17Lands fetch is the one 17lands.com request BoosterTutor makes, and
ADR 0023 sets its limits: only when a user submits a link, the identifying
User-Agent, a short timeout, and no retrying a 4xx. The other two limits
(one fetch per draft, cached; a rate limit per client) are kept by
`draft_import.py`, the Replay Cache and `rate_limit.py`.
"""

import json
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .ingest.fetching import FetchError, HTTPStatusError, fetch_json_bytes
from .models import BoosterCard, Card
from .parsing import seventeen_lands
from .parsing.errors import DraftInputError
from .parsing.names import name_key
from .schemas import DraftLog

DRAFT_URL = "https://www.17lands.com/data/draft?draft_id={draft_id}"
METADATA_URL = "https://www.17lands.com/data/event_metadata?draft_id={draft_id}"

# A user is waiting, so give up quickly: 15 seconds, two attempts at most
# (the second only after a 5xx or a network error).
TIMEOUT_SECONDS = 15
MAX_ATTEMPTS = 2


def name_index(session: Session, set_code: str) -> dict[str, uuid.UUID]:
    """`name_key` to oracle id, for every card the set's packs can hold.

    The same index the 17Lands ingest matches statistics with, so every
    card in a draft that resolves here also has its statistics found.
    """
    rows = session.execute(
        select(Card.name, BoosterCard.oracle_id)
        .join(Card, Card.oracle_id == BoosterCard.oracle_id)
        .where(BoosterCard.set_code == set_code)
    )
    return {name_key(name): oracle_id for name, oracle_id in rows}


def fetch_seventeen_lands_draft(draft_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """The draft payload and its event metadata, or `DraftInputError`.

    Metadata first: it is tiny, and a draft 17Lands can't find fails before
    the larger pick log is requested.
    """
    metadata = _fetch_json(METADATA_URL.format(draft_id=draft_id))
    draft = _fetch_json(DRAFT_URL.format(draft_id=draft_id))
    return draft, metadata


def draft_log_from_link(session: Session, text: str) -> DraftLog:
    """Whatever the user pasted (a 17Lands URL or a draft id) into a `DraftLog`."""
    draft_id = seventeen_lands.parse_draft_id(text)
    draft, metadata = fetch_seventeen_lands_draft(draft_id)
    names = name_index(session, seventeen_lands.draft_set_code(metadata))
    return seventeen_lands.parse_draft(draft, metadata, names, draft_id=draft_id)


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
