"""Writing one Draft Summary with Claude Sonnet 5.5 (ADR 0024, ADR 0030 s4).

    write_draft_summary(client, ledger, brief, ...) -> DraftSummary

One call per Reviewed Deck, laid out for the prompt cache: the prompt file
(instructions and few-shot examples) is system block 1, the Format Primer
is system block 2, both cached for an hour, and the draft's brief comes
after them as the user message.

It follows `pick_note.py`: `messages.create` (here on the beta client)
with `output_config.format`, the answer validated against
`DraftSummaryOutput` and then by `checks.summary_problems`, one retry on
a summary that fails either, the spending cap checked before every
attempt, and an `llm_calls` row for every call, the failed ones included.

Two differences from a Pick Note:

- **The refusal fallback.** Claude Sonnet 5.5's safety classifiers can
  decline a request. With `fallbacks: "default"` (a beta) the API re-runs a
  declined request on the model Anthropic recommends for the refusal's
  category, inside the same call. A `refusal` stop reason then means the
  whole chain declined, and is not retried. Claude Haiku 5.5 has no
  fallback, so its requests (for the eval's comparison) leave it out.
- **Cost, attempt by attempt.** When a fallback served the answer, the
  top-level `usage` covers only the serving attempt. `usage.iterations`
  lists every attempt with the model that ran it, so the cost is summed
  over those at each model's price, and the row records the model that
  served the answer.
"""

import time
import uuid
from decimal import Decimal
from typing import Any, Literal

import anthropic
import pydantic
from anthropic.types.beta import BetaMessage, BetaTextBlock
from pydantic import BaseModel

from ..briefing.summary import SummaryBrief
from ..models import LlmCall
from .checks import summary_problems
from .pick_note import Prompt, load_prompt
from .pricing import Usage, cost_usd
from .spending import Ledger, check_spending_cap

MODEL = "claude-sonnet-5-5"
HAIKU = "claude-haiku-5-5"  # run through the same eval, for comparison
PROMPT_VERSION = "draft_summary.v1"
PURPOSE = "draft_summary"
SUBJECT = "summary"
FALLBACK_BETA = "server-side-fallback-2026-07-01"
# Room for low-effort thinking plus about 200 words of JSON.
MAX_TOKENS = 4000
ATTEMPTS = 2  # the call, and one retry on a summary that fails validation
# Nobody waits on a live screen for this one as they do for a Pick Note,
# but a submitted deck still shows a spinner, so give up after a minute.
TIMEOUT_SECONDS = 60.0

Status = Literal["succeeded", "invalid", "refused", "error"]

__all__ = [
    "FALLBACK_BETA",
    "HAIKU",
    "MODEL",
    "DraftSummary",
    "DraftSummaryFailed",
    "DraftSummaryOutput",
    "KeyPick",
    "draft_summary_request",
    "load_prompt",
    "write_draft_summary",
]


class KeyPick(BaseModel):
    """A pick the summary points to. Python shows its card, verdict and gap."""

    pack_number: int
    pick_number: int


class DraftSummaryOutput(BaseModel):
    """What Claude returns: three prose fields and up to two Key Picks (ADR 0030 s1)."""

    draft_arc: str
    deck: str
    lesson: str
    key_picks: list[KeyPick]


OUTPUT_FORMAT = {
    "type": "json_schema",
    "schema": anthropic.transform_schema(DraftSummaryOutput.model_json_schema()),
}


class DraftSummary(BaseModel):
    """A summary to store with its draft review, with the prompt and model that wrote it."""

    draft_arc: str
    deck: str
    lesson: str
    key_picks: list[KeyPick]
    prompt_version: str
    model: str  # the model that served it: a fallback may differ from MODEL


class DraftSummaryFailed(RuntimeError):
    """No summary this time. The review still shows its Python facts and ratings."""


def draft_summary_request(
    brief: SummaryBrief, prompt: Prompt, primer: str, *, model: str = MODEL
) -> dict[str, Any]:
    """The arguments to `beta.messages.create`, for one brief.

    Nothing about the draft, the user or the time goes in `system`: both
    blocks must be byte-identical on every call of the format, or the cache
    never hits.
    """
    cached = {"type": "ephemeral", "ttl": "1h"}
    request: dict[str, Any] = {
        "model": model,
        "max_tokens": MAX_TOKENS,
        "output_config": {"effort": "low", "format": OUTPUT_FORMAT},
        "system": [
            {"type": "text", "text": prompt.text, "cache_control": cached},
            {"type": "text", "text": primer, "cache_control": cached},
        ],
        "messages": [{"role": "user", "content": brief.text}],
    }
    if model == MODEL:
        request["betas"] = [FALLBACK_BETA]
        request["fallbacks"] = "default"
    return request


def write_draft_summary(
    client: anthropic.Anthropic,
    ledger: Ledger,
    brief: SummaryBrief,
    *,
    prompt: Prompt,
    primer: str,
    cap: Decimal,
    draft_key: str | None,
    user_id: uuid.UUID | None,
    model: str = MODEL,
) -> DraftSummary:
    """Ask Claude for this draft's summary, check it, and record every call.

    `user_id` is None only for eval and CLI runs (ADR 0021). Raises
    `SpendingCapReached` before any call once today's spend is at the cap,
    and `DraftSummaryFailed` when no summary passed its checks.
    """
    request = draft_summary_request(brief, prompt, primer, model=model)
    row = {
        "purpose": PURPOSE,
        "prompt_version": prompt.version,
        "user_id": user_id,
        "draft_key": draft_key,
        "subject": SUBJECT,
    }

    problems: list[str] = []
    for _ in range(ATTEMPTS):
        check_spending_cap(ledger, cap)
        started = time.perf_counter()
        try:
            message = client.with_options(timeout=TIMEOUT_SECONDS).beta.messages.create(
                **request
            )
        except anthropic.APIError as exc:
            ledger.record(
                _call(
                    row, model, started, Usage(), Decimal(0), "error", repr(exc), None
                )
            )
            raise DraftSummaryFailed(f"the API call failed: {exc}") from exc

        usage, cost = _usage_and_cost(message, model)
        served = message.model
        request_id = message._request_id
        if message.stop_reason == "refusal":
            # With the fallback, this is the whole chain declining.
            ledger.record(
                _call(row, served, started, usage, cost, "refused", None, request_id)
            )
            raise DraftSummaryFailed("Claude declined to write this summary")

        output = None
        try:
            output = DraftSummaryOutput.model_validate_json(_text(message))
            problems = summary_problems(output, brief.text, brief.picks)
        except pydantic.ValidationError as exc:
            problems = [f"the response did not validate: {exc.error_count()} error(s)"]

        status: Status = "invalid" if problems else "succeeded"
        error = "; ".join(problems) or None
        ledger.record(
            _call(row, served, started, usage, cost, status, error, request_id)
        )
        if output is not None and not problems:
            return DraftSummary(
                draft_arc=output.draft_arc.strip(),
                deck=output.deck.strip(),
                lesson=output.lesson.strip(),
                key_picks=output.key_picks,
                prompt_version=prompt.version,
                model=served,
            )

    raise DraftSummaryFailed(
        f"no valid summary after {ATTEMPTS} tries: {'; '.join(problems)}"
    )


def _usage_and_cost(message: BetaMessage, model: str) -> tuple[Usage, Decimal]:
    """The call's tokens and cost, over every attempt when a fallback ran."""
    iterations = [
        it
        for it in message.usage.iterations or []
        if it.type in ("message", "fallback_message")
    ]
    if not iterations:
        usage = Usage(
            input_tokens=message.usage.input_tokens,
            cache_read_tokens=message.usage.cache_read_input_tokens or 0,
            cache_write_tokens=message.usage.cache_creation_input_tokens or 0,
            output_tokens=message.usage.output_tokens,
        )
        return usage, cost_usd(model, usage)

    total = Usage()
    cost = Decimal(0)
    for it in iterations:
        part = Usage(
            input_tokens=it.input_tokens,
            cache_read_tokens=it.cache_read_input_tokens,
            cache_write_tokens=it.cache_creation_input_tokens,
            output_tokens=it.output_tokens,
        )
        cost += cost_usd(it.model or model, part)
        total = Usage(
            input_tokens=total.input_tokens + part.input_tokens,
            cache_read_tokens=total.cache_read_tokens + part.cache_read_tokens,
            cache_write_tokens=total.cache_write_tokens + part.cache_write_tokens,
            output_tokens=total.output_tokens + part.output_tokens,
        )
    return total, cost


def _text(message: BetaMessage) -> str:
    """The answer's text. Thinking and fallback blocks, if any, are skipped."""
    return "".join(b.text for b in message.content if isinstance(b, BetaTextBlock))


def _call(
    row: dict[str, Any],
    model: str,
    started: float,
    usage: Usage,
    cost: Decimal,
    status: Status,
    error: str | None,
    request_id: str | None,
) -> LlmCall:
    return LlmCall(
        **row,
        model=model,
        input_tokens=usage.input_tokens,
        cache_read_tokens=usage.cache_read_tokens,
        cache_write_tokens=usage.cache_write_tokens,
        output_tokens=usage.output_tokens,
        cost_usd=cost,
        latency_ms=round((time.perf_counter() - started) * 1000),
        status=status,
        error=error,
        request_id=request_id,
    )
