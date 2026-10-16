"""What a call cost, from its token counts (ADR 0024 s8).

Worked by hand from Anthropic's rate cards (2026-10-06): Claude Haiku 5.5
is $0.10 in and $0.50 out per million tokens for prompts of up to 100K
tokens, cache reads 0.1x the input price, 1-hour cache writes 2x.
"""

from decimal import Decimal

import pytest

from boostertutor.llm.pricing import Usage, cost_usd


def test_a_pick_note_costs_its_four_kinds_of_token() -> None:
    """1,000 in = $0.0001; 2,000 cache read = $0.00002; 200 out = $0.0001."""
    usage = Usage(input_tokens=1000, cache_read_tokens=2000, output_tokens=200)
    assert cost_usd("claude-haiku-5-5", usage) == Decimal("0.000220")


def test_a_one_hour_cache_write_costs_twice_the_input_price() -> None:
    """2,000 tokens written at $0.20 per million = $0.0004."""
    usage = Usage(cache_write_tokens=2000)
    assert cost_usd("claude-haiku-5-5", usage) == Decimal("0.000400")


def test_sonnet_has_its_own_rate_card() -> None:
    """Claude Sonnet 5.5: $2 in, $10 out. 1,000 in + 500 out = $0.002 + $0.005."""
    usage = Usage(input_tokens=1000, output_tokens=500)
    assert cost_usd("claude-sonnet-5-5", usage) == Decimal("0.007000")


def test_a_haiku_prompt_over_100k_tokens_is_priced_at_the_long_rate() -> None:
    """$0.50 in and $2.50 out once the prompt passes 100K: 150,000 in = $0.075."""
    usage = Usage(input_tokens=150_000, output_tokens=1000)
    assert cost_usd("claude-haiku-5-5", usage) == Decimal("0.077500")


def test_an_unpriced_model_is_refused() -> None:
    """A model with no rate card would record a call as free, so it fails loudly."""
    with pytest.raises(KeyError):
        cost_usd("claude-unknown", Usage())


def test_claude_sonnet_5_is_priced_for_calls_a_fallback_served() -> None:
    """ADR 0030 s4: a refused Sonnet 5.5 call may be served by Claude Sonnet 5."""
    usage = Usage(input_tokens=1000, output_tokens=500)
    assert cost_usd("claude-sonnet-5", usage) == Decimal("0.007000")
