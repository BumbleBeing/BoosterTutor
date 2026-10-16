"""What an eval report says about one case's Claude calls (Phase 5d).

Shared by the Pick Note and Draft Summary evals, so both report the same
fields: what the case cost, how its prompt cache did, how many tokens were
paid for at the full price, and how long it took. A case is usually one
call; a retry adds a second, and both are counted.
"""

from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from boostertutor.models import LlmCall


def call_totals(calls: Sequence[LlmCall]) -> dict[str, Any]:
    return {
        "attempts": [c.status for c in calls],
        "errors": [c.error for c in calls if c.error],
        "cost_usd": str(sum((c.cost_usd for c in calls), Decimal(0))),
        # Uncached input: the brief, plus the cached blocks on a cache miss.
        "input_tokens": sum(c.input_tokens for c in calls),
        "cache_read_tokens": sum(c.cache_read_tokens for c in calls),
        "cache_write_tokens": sum(c.cache_write_tokens for c in calls),
        "output_tokens": sum(c.output_tokens for c in calls),
        # Each attempt's wall-clock time, as a person would wait for it.
        "latency_ms": [c.latency_ms for c in calls],
    }
