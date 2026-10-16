"""Importing a draft: a 17Lands link in, a cached `DraftLog` out (ADR 0031).

The order matters. A draft already in the Replay Cache is answered at once,
with no 17Lands request and no use of the caller's allowance. Only a miss
passes the rate limit, and the limit is charged before the fetch so a failed
fetch still counts.
"""

from dataclasses import dataclass

from .draft_services import DraftServices
from .parsing import seventeen_lands
from .parsing.errors import DraftInputError


@dataclass(frozen=True)
class Imported:
    draft_id: str
    cached: bool  # True: answered from the Replay Cache, 17Lands not asked


def import_draft(text: str, client: str, services: DraftServices) -> Imported:
    """Whatever the user pasted into a cached draft, or `DraftInputError` /
    `RateLimited`."""
    draft_id = seventeen_lands.parse_draft_id(text)
    if services.store.has(draft_id):
        return Imported(draft_id, cached=True)

    services.limiter.check_and_record(client)
    draft, metadata = services.fetch(draft_id)

    # Refuse an unsupported set before matching any cards: we may hold no
    # card data for it, and a log of it must not be cached.
    set_code = seventeen_lands.draft_set_code(metadata)
    if set_code not in services.supported_sets:
        raise DraftInputError(
            "unsupported_set",
            "BoosterTutor reviews HOB drafts for now. More sets are coming.",
            {"set_code": set_code},
        )

    log = seventeen_lands.parse_draft(
        draft, metadata, services.names_for(set_code), draft_id=draft_id
    )
    services.store.add(log)
    return Imported(draft_id, cached=False)
