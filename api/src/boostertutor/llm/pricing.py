"""What a Claude call cost, from the token counts in its response.

Pure. The prices are Anthropic's first-party rates per million tokens
(2026-10-06). When they change, change them here: `llm_calls.cost_usd` is
written at call time, so older rows keep the price they were made at.

Cache reads cost a tenth of the input price, and a 1-hour cache write
twice it. Every cache write here is 1-hour (ADR 0024 s6), so a 5-minute
write price is not needed.
"""

from dataclasses import dataclass
from decimal import Decimal

MILLION = Decimal(1_000_000)
CACHE_READ = Decimal("0.1")
CACHE_WRITE_1H = Decimal(2)


@dataclass(frozen=True)
class RateCard:
    input: Decimal  # $ per million uncached input tokens
    output: Decimal  # $ per million output tokens


@dataclass(frozen=True)
class Pricing:
    standard: RateCard
    # Claude Haiku 5.5 charges more once a prompt passes 100K tokens. A
    # Pick Note is a few thousand, so this is a guard, not a plan.
    long: RateCard | None = None
    long_above: int = 100_000


PRICES: dict[str, Pricing] = {
    "claude-haiku-5-5": Pricing(
        standard=RateCard(Decimal("0.10"), Decimal("0.50")),
        long=RateCard(Decimal("0.50"), Decimal("2.50")),
    ),
    "claude-sonnet-5-5": Pricing(standard=RateCard(Decimal("2.00"), Decimal("10.00"))),
    # The model the server-side fallback serves some refused Sonnet 5.5
    # calls from (ADR 0030 s4).
    "claude-sonnet-5": Pricing(standard=RateCard(Decimal("2.00"), Decimal("10.00"))),
}


@dataclass(frozen=True)
class Usage:
    """A response's `usage`, in this table's words."""

    input_tokens: int = 0  # uncached input
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    output_tokens: int = 0

    @property
    def prompt_tokens(self) -> int:
        return self.input_tokens + self.cache_read_tokens + self.cache_write_tokens


def cost_usd(model: str, usage: Usage) -> Decimal:
    """Dollars, to six places (a millionth of a dollar), as `llm_calls` stores it.

    An unknown model raises `KeyError`: recording a call as free would
    quietly switch off the spending cap.
    """
    pricing = PRICES[model]
    card = pricing.standard
    if pricing.long is not None and usage.prompt_tokens > pricing.long_above:
        card = pricing.long
    dollars = (
        usage.input_tokens * card.input
        + usage.cache_read_tokens * card.input * CACHE_READ
        + usage.cache_write_tokens * card.input * CACHE_WRITE_1H
        + usage.output_tokens * card.output
    ) / MILLION
    return dollars.quantize(Decimal("0.000001"))
