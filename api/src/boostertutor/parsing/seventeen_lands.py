"""A 17Lands draft link into a `DraftLog` (development plan 3.1, input 1).

The two payloads come from `17lands.com/data/draft` and
`data/event_metadata` (ADR 0023; fetched in `boostertutor.drafts`). This
module only reads them.

What the draft payload holds, confirmed on a real HOB draft (2026-09-18 and
2026-10-14):
  * `picks`: one entry per pick, with `pack_number` and `pick_number`
    **0-indexed**, `pick` (the card taken) and `available` (the pack before
    the pick, *including* the card taken).
  * cards are named, not numbered: no oracle id, no Arena id. A double-faced
    card is named by its front face only.
  * each entry's `picks` is a list, for formats that take two cards at a time.
  * It also carries 17Lands' own statistics and advice
    (`card_performance_data`, `suggested_pick`, `sections`). Those are site
    data that ADR 0002 rules out, so they are never read here; every
    statistic BoosterTutor uses comes from the public datasets.
"""

import re
import uuid
from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from ..schemas import DraftLog, Pick
from .errors import DraftInputError
from .names import name_key

# A draft id is 32 lower-case hex characters. Accept it bare or anywhere in a
# URL such as https://www.17lands.com/draft/<id>/1/1, so the user can paste
# whatever they copied.
DRAFT_ID_RE = re.compile(r"[0-9a-f]{32}")


def parse_draft_id(text: str) -> str:
    """The draft id in a bare id or a 17Lands URL."""
    match = DRAFT_ID_RE.search(text.strip().lower())
    if match is None:
        raise DraftInputError(
            "invalid_input",
            "that doesn't look like a 17Lands draft link or draft id",
        )
    return match.group(0)


def draft_set_code(metadata: dict[str, Any]) -> str:
    """The draft's set, lower case. Read first, to build the right name index."""
    meta = metadata.get("metadata", metadata)
    expansion = meta.get("expansion") if isinstance(meta, dict) else None
    if not isinstance(expansion, str) or not expansion:
        raise DraftInputError("upstream_failure", "17Lands did not say the draft's set")
    return expansion.lower()


def parse_draft(
    draft: dict[str, Any],
    metadata: dict[str, Any],
    names: Mapping[str, uuid.UUID],
    *,
    draft_id: str | None = None,
) -> DraftLog:
    """Turn the two payloads into a `DraftLog`, or raise `DraftInputError`.

    `names` maps `name_key(name)` to an oracle id, for every card the set's
    packs can hold (`booster_cards`), the same index the 17Lands ingest
    matches statistics with. Empty means we have no data for the set.
    """
    set_code = draft_set_code(metadata)
    meta = metadata.get("metadata", metadata)
    if not names:
        raise DraftInputError(
            "unsupported_set",
            f"BoosterTutor has no card data for {set_code.upper()} yet",
            {"set_code": set_code},
        )

    raw_picks = draft.get("picks")
    if not isinstance(raw_picks, list) or not raw_picks:
        raise DraftInputError("upstream_failure", "the 17Lands draft has no picks")

    try:
        # 0-indexed in the payload; 1-based everywhere in BoosterTutor.
        entries = sorted(
            (
                (int(e["pack_number"]) + 1, int(e["pick_number"]) + 1, e)
                for e in raw_picks
            ),
            key=lambda item: (item[0], item[1]),
        )
        rows = [
            (pack, pick, e["pick"]["name"], [c["name"] for c in e["available"]])
            for pack, pick, e in entries
        ]
    except (KeyError, TypeError, ValueError) as exc:
        raise DraftInputError(
            "upstream_failure", "the 17Lands draft is not in the shape we expect"
        ) from exc

    if any(len(e.get("picks") or [None]) > 1 for _, _, e in entries):
        raise DraftInputError(
            "unsupported_format",
            "this draft took more than one card per pick, which isn't supported",
        )

    # Resolve every name in the whole draft first, so a draft with three
    # unknown cards reports all three at once rather than one per attempt.
    every_name = {n for _, _, taken, pack in rows for n in [taken, *pack]}
    unresolved = sorted(n for n in every_name if name_key(n) not in names)
    if unresolved:
        raise DraftInputError(
            "unresolved_cards",
            f"{len(unresolved)} card name(s) in this draft aren't in our "
            f"{set_code.upper()} card list",
            unresolved,
        )

    picks: list[Pick] = []
    pool: list[uuid.UUID] = []
    for pack, pick, taken, pack_names in rows:
        picked = names[name_key(taken)]
        picks.append(
            Pick(
                pack_number=pack,
                pick_number=pick,
                pack_cards=[names[name_key(n)] for n in pack_names],
                picked=picked,
                pool_before=list(pool),
            )
        )
        pool.append(picked)

    try:
        return DraftLog(
            set_code=set_code,
            event_type=str(meta.get("format") or "PremierDraft"),
            drafted_at=None,  # neither payload says when the draft was made
            source="17lands",
            source_id=draft_id,
            wins=_int_or_none(meta.get("wins")),
            losses=_int_or_none(meta.get("losses")),
            picks=picks,
        )
    except ValidationError as exc:
        # Most often an unfinished draft: picks stop partway through a pack.
        reason = exc.errors()[0]["msg"].removeprefix("Value error, ")
        raise DraftInputError(
            "malformed_draft",
            "this draft isn't three complete packs, so it can't be reviewed",
            reason,
        ) from exc


def _int_or_none(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None
