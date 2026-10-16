"""The coach: Claude writing a Pick Note or a Draft Summary for a request (ADR 0031 s2).

`ClaudeCoach` is `ReviewService`'s way to call Claude. It holds what every
call needs (the client, the `llm_calls` ledger, the prompts and the daily
spending cap) so the service only hands over a brief. The calls themselves
are `write_pick_note` and `write_draft_summary`, unchanged from Phase 4:
the cap is checked before every attempt and every attempt leaves an
`llm_calls` row, so an admin-key call is capped and recorded like any
other (ADR 0027 s3).

Raises what those raise: `SpendingCapReached`, `PickNoteFailed`,
`DraftSummaryFailed`. The service turns them into `ReviewError`s.
"""

import uuid
from decimal import Decimal

import anthropic

from ..briefing import PickBrief
from ..briefing.summary import SummaryBrief
from .draft_summary import DraftSummary, write_draft_summary
from .pick_note import PickNote, Prompt, write_pick_note
from .spending import Ledger


class ClaudeCoach:
    def __init__(
        self,
        client: anthropic.Anthropic,
        ledger: Ledger,
        *,
        cap: Decimal,
        pick_note_prompt: Prompt,
        summary_prompt: Prompt,
    ) -> None:
        self.client = client
        self.ledger = ledger
        self.cap = cap
        self.pick_note_prompt = pick_note_prompt
        self.summary_prompt = summary_prompt

    def pick_note(
        self, brief: PickBrief, *, draft_key: str, user_id: uuid.UUID | None
    ) -> PickNote:
        return write_pick_note(
            self.client,
            self.ledger,
            brief,
            prompt=self.pick_note_prompt,
            cap=self.cap,
            draft_key=draft_key,
            user_id=user_id,
        )

    def draft_summary(
        self,
        brief: SummaryBrief,
        primer: str,
        *,
        draft_key: str,
        user_id: uuid.UUID | None,
    ) -> DraftSummary:
        return write_draft_summary(
            self.client,
            self.ledger,
            brief,
            prompt=self.summary_prompt,
            primer=primer,
            cap=self.cap,
            draft_key=draft_key,
            user_id=user_id,
        )
