"""Writing one Pick Note with Claude Haiku 5.5 (ADR 0024).

    write_pick_note(client, ledger, brief, ...) -> PickNote

One call per Noted Pick, laid out for the prompt cache: the prompt file
(instructions, vocabulary, few-shot examples) is one system block cached for
an hour, and the pick's brief comes after it as the user message, so every
call shares the cached prefix (ADR 0024 s6).

The response is structured output (`output_config.format`, a JSON schema
of `PickNoteOutput`), validated against that model and then by
`checks.note_problems`: the right pick, a length cap, and no number the
brief does not state.

Why `messages.create` and not `messages.parse`: the request on the wire is
the same, but `parse` validates inside the SDK and, when validation fails
(a truncated or refused response), raises without returning the response,
so its token counts are lost. A failed call is still billed, and the
spending cap only works if every billed call is recorded. A note that fails
either is retried once; a second failure raises `PickNoteFailed`, and the
review shows its Python verdicts without the prose (ADR 0024 s7).

Every API call leaves an `llm_calls` row, the failed ones included, and the
spending cap is checked before each call, the retry included (ADR 0027).
"""

import time
import uuid
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

import anthropic
import pydantic
from anthropic.types import Message, TextBlock
from pydantic import BaseModel

from ..briefing import NoteKind, PickBrief
from ..config import settings
from ..models import LlmCall
from .checks import note_problems
from .pricing import Usage, cost_usd
from .spending import Ledger, check_spending_cap

MODEL = "claude-haiku-5-5"
# The prompt in use. A new version is a new file, never an edit (CLAUDE.md).
PROMPT_VERSION = "pick_note.v1"
PURPOSE = "pick_note"
# Room for low-effort thinking plus a note of at most 600 characters.
MAX_TOKENS = 2000
ATTEMPTS = 2  # the call, and one retry on a note that fails validation
# A practice draft waits on this note, and unlocks after 15 seconds
# (ADR 0024 s3), so the call gives up on the same clock.
TIMEOUT_SECONDS = 15.0

Status = Literal["succeeded", "invalid", "refused", "error"]


class PickNoteOutput(BaseModel):
    """What Claude returns: prose only, keyed by the pick (ADR 0024 s7).

    The verdict, the gap and the best card are attached by Python when the
    note is shown, so the prose can never contradict the label.
    """

    pack_number: int
    pick_number: int
    note: str


# The JSON schema Claude's answer is constrained to, made the way
# `messages.parse` makes it from a Pydantic model.
OUTPUT_FORMAT = {
    "type": "json_schema",
    "schema": anthropic.transform_schema(PickNoteOutput.model_json_schema()),
}


class PickNote(BaseModel):
    """A note to store next to its pick, with the prompt that wrote it."""

    pack_number: int
    pick_number: int
    kind: NoteKind
    note: str
    prompt_version: str


class PickNoteFailed(RuntimeError):
    """No note this time. The pick still shows its verdict; a retry may work."""


@dataclass(frozen=True)
class Prompt:
    version: str  # the file's name without ".md": "pick_note.v1"
    text: str  # exactly what is sent


def load_prompt(version: str, directory: Path | None = None) -> Prompt:
    """A prompt file from `docs/prompts/`, minus its leading `<!-- -->` comment.

    The comment is for the humans editing the file. Everything after it is
    sent byte for byte, so a stray edit shows up as a cache miss rather
    than going unnoticed.
    """
    raw = ((directory or settings.prompts_dir) / f"{version}.md").read_text()
    if raw.startswith("<!--"):
        raw = raw[raw.index("-->") + len("-->") :]
    return Prompt(version=version, text=raw.strip() + "\n")


def pick_note_request(brief: PickBrief, prompt: Prompt) -> dict[str, Any]:
    """The arguments to `messages.parse`, for one brief.

    Nothing about the draft, the user or the time goes in `system`: that
    block must be byte-identical on every call, or the cache never hits.
    """
    return {
        "model": MODEL,
        "max_tokens": MAX_TOKENS,
        "output_config": {"effort": "low", "format": OUTPUT_FORMAT},
        "system": [
            {
                "type": "text",
                "text": prompt.text,
                "cache_control": {"type": "ephemeral", "ttl": "1h"},
            }
        ],
        "messages": [{"role": "user", "content": brief.text}],
    }


def write_pick_note(
    client: anthropic.Anthropic,
    ledger: Ledger,
    brief: PickBrief,
    *,
    prompt: Prompt,
    cap: Decimal,
    draft_key: str | None,
    user_id: uuid.UUID | None,
) -> PickNote:
    """Ask Claude for this pick's note, check it, and record every call.

    `user_id` is None only for eval and CLI runs: a call made for a user
    always names them (ADR 0021). Raises `SpendingCapReached` before any
    call once today's spend is at the cap, and `PickNoteFailed` when no
    note passed its checks.
    """
    request = pick_note_request(brief, prompt)
    pick = (brief.pack_number, brief.pick_number)
    row = {
        "purpose": PURPOSE,
        "model": MODEL,
        "prompt_version": prompt.version,
        "user_id": user_id,
        "draft_key": draft_key,
        "subject": f"P{pick[0]}p{pick[1]}",
    }

    problems: list[str] = []
    for _ in range(ATTEMPTS):
        check_spending_cap(ledger, cap)
        started = time.perf_counter()
        try:
            message = client.with_options(timeout=TIMEOUT_SECONDS).messages.create(
                **request
            )
        except anthropic.APIError as exc:
            ledger.record(_call(row, started, Usage(), "error", repr(exc), None))
            raise PickNoteFailed(f"the API call failed: {exc}") from exc

        request_id = message._request_id
        usage = Usage(
            input_tokens=message.usage.input_tokens,
            cache_read_tokens=message.usage.cache_read_input_tokens or 0,
            cache_write_tokens=message.usage.cache_creation_input_tokens or 0,
            output_tokens=message.usage.output_tokens,
        )
        if message.stop_reason == "refusal":
            # Claude Haiku 5.5 has no server-side fallback, and asking again
            # is unlikely to change a safety decision, so no retry.
            ledger.record(_call(row, started, usage, "refused", None, request_id))
            raise PickNoteFailed("Claude declined to write this note")

        output = None
        try:
            output = PickNoteOutput.model_validate_json(_text(message))
            problems = note_problems(output, brief.text, pick)
        except pydantic.ValidationError as exc:
            # Truncated or malformed JSON: a max_tokens stop, say.
            problems = [f"the response did not validate: {exc.error_count()} error(s)"]

        status: Status = "invalid" if problems else "succeeded"
        error = "; ".join(problems) or None
        ledger.record(_call(row, started, usage, status, error, request_id))
        if output is not None and not problems:
            return PickNote(
                pack_number=output.pack_number,
                pick_number=output.pick_number,
                kind=brief.kind,
                note=output.note.strip(),
                prompt_version=prompt.version,
            )

    raise PickNoteFailed(f"no valid note after {ATTEMPTS} tries: {'; '.join(problems)}")


def _text(message: Message) -> str:
    """The answer's text. Thinking blocks, if any, come first and are skipped."""
    return "".join(b.text for b in message.content if isinstance(b, TextBlock))


def _call(
    row: dict[str, Any],
    started: float,
    usage: Usage,
    status: Status,
    error: str | None,
    request_id: str | None,
) -> LlmCall:
    return LlmCall(
        **row,
        input_tokens=usage.input_tokens,
        cache_read_tokens=usage.cache_read_tokens,
        cache_write_tokens=usage.cache_write_tokens,
        output_tokens=usage.output_tokens,
        cost_usd=cost_usd(MODEL, usage),
        latency_ms=round((time.perf_counter() - started) * 1000),
        status=status,
        error=error,
        request_id=request_id,
    )
