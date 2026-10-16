"""The fields every eval report carries for a case's calls (Phase 5d)."""

from decimal import Decimal

from eval_report import call_totals

from boostertutor.models import LlmCall


def _call(status: str, latency_ms: int, error: str | None = None) -> LlmCall:
    return LlmCall(
        purpose="pick_note",
        model="claude-haiku-5-5",
        prompt_version="pick_note.v1",
        input_tokens=700,
        cache_read_tokens=3700,
        cache_write_tokens=0,
        output_tokens=180,
        cost_usd=Decimal("0.000200"),
        latency_ms=latency_ms,
        status=status,
        error=error,
    )


def test_a_retried_case_reports_both_attempts() -> None:
    totals = call_totals([_call("invalid", 2400, "too long"), _call("succeeded", 2100)])
    assert totals == {
        "attempts": ["invalid", "succeeded"],
        "errors": ["too long"],
        "cost_usd": "0.000400",
        "input_tokens": 1400,
        "cache_read_tokens": 7400,
        "cache_write_tokens": 0,
        "output_tokens": 360,
        "latency_ms": [2400, 2100],
    }
