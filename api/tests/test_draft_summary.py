"""Writing a Draft Summary: the request, the fallback, the retry and the ledger (ADR 0030 s4).

As in `test_pick_note.py`, Claude is replaced by a fake at the SDK
boundary, `client.beta.messages.create`, and one test runs the real SDK
client over a mock transport to check the wire format. The ledger is in
memory. Nothing here makes a network call.
"""

import json
import uuid
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import anthropic
import httpx2
import pytest
from anthropic.types.beta import BetaMessage
from conftest import FIXTURES, load_deck_inputs
from test_summary_brief import BR_DECK, brief_for

from boostertutor.briefing.card_facts import CardFacts
from boostertutor.briefing.primer import format_primer
from boostertutor.briefing.summary import SummaryBrief
from boostertutor.llm.draft_summary import (
    FALLBACK_BETA,
    HAIKU,
    MODEL,
    DraftSummaryFailed,
    draft_summary_request,
    load_prompt,
    write_draft_summary,
)
from boostertutor.llm.spending import SpendingCapReached
from boostertutor.models import LlmCall
from boostertutor.schemas.draft_analysis import DraftAnalysis

PROMPT = load_prompt("draft_summary.v1")
PRIMER = format_primer(load_deck_inputs()[2])
CAP = Decimal("5.00")
DECKS = FIXTURES / "decks"


def summary_json(**changes: Any) -> str:
    summary = {
        "draft_arc": "Red flowed in pack 2, and black never stopped.",
        "deck": "An A overall, and removal carries it.",
        "lesson": "Trust what wheels.",
        "key_picks": [{"pack_number": 1, "pick_number": 12}],
    }
    return json.dumps({**summary, **changes})


def api_message(
    text: str,
    stop_reason: str = "end_turn",
    *,
    model: str = MODEL,
    iterations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """A Messages API response body, as the API sends it."""
    usage: dict[str, Any] = {
        "input_tokens": 5000,
        "output_tokens": 400,
        "cache_read_input_tokens": 3000,
        "cache_creation_input_tokens": 0,
    }
    if iterations is not None:
        usage["iterations"] = iterations
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": [{"type": "text", "text": text}] if text else [],
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": usage,
    }


def good() -> dict[str, Any]:
    return api_message(summary_json())


class FakeClient:
    """Answers each call with the next response in `answers`."""

    def __init__(self, *answers: dict[str, Any] | Exception) -> None:
        self.answers = list(answers)
        self.requests: list[dict[str, Any]] = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def with_options(self, **_: Any) -> "FakeClient":
        return self

    def _create(self, **request: Any) -> BetaMessage:
        self.requests.append(request)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        message = BetaMessage.model_validate(answer)
        message._request_id = "req_test"
        return message


class Ledger:
    def __init__(self, spent: str = "0") -> None:
        self.spent = Decimal(spent)
        self.calls: list[LlmCall] = []

    def spent_today(self) -> Decimal:
        return self.spent

    def record(self, call: LlmCall) -> None:
        self.calls.append(call)


@pytest.fixture(scope="module")
def brief(
    analysis: DraftAnalysis, card_facts: dict[uuid.UUID, CardFacts]
) -> SummaryBrief:
    return brief_for(analysis, card_facts, BR_DECK)


def write(client: Any, ledger: Ledger, brief: SummaryBrief, model: str = MODEL) -> Any:
    return write_draft_summary(
        client,
        ledger,
        brief,
        prompt=PROMPT,
        primer=PRIMER,
        cap=CAP,
        draft_key="17lands:d9ac6765",
        user_id=None,
        model=model,
    )


# --------------------------------------------------------------------------
# The request
# --------------------------------------------------------------------------


def test_two_cached_blocks_come_first_and_the_brief_last(brief: SummaryBrief) -> None:
    request = draft_summary_request(brief, PROMPT, PRIMER)
    assert request["model"] == "claude-sonnet-5-5"
    assert request["output_config"]["effort"] == "low"
    cached = {"type": "ephemeral", "ttl": "1h"}
    assert request["system"] == [
        {"type": "text", "text": PROMPT.text, "cache_control": cached},
        {"type": "text", "text": PRIMER, "cache_control": cached},
    ]
    assert request["messages"] == [{"role": "user", "content": brief.text}]
    schema = request["output_config"]["format"]["schema"]
    assert set(schema["properties"]) == {"draft_arc", "deck", "lesson", "key_picks"}


def test_sonnet_asks_for_the_server_side_fallback_and_haiku_does_not(
    brief: SummaryBrief,
) -> None:
    sonnet = draft_summary_request(brief, PROMPT, PRIMER)
    assert (sonnet["fallbacks"], sonnet["betas"]) == ("default", [FALLBACK_BETA])
    haiku = draft_summary_request(brief, PROMPT, PRIMER, model=HAIKU)
    assert haiku["model"] == "claude-haiku-5-5"
    assert "fallbacks" not in haiku and "betas" not in haiku


def test_the_cached_blocks_are_byte_identical_across_drafts(
    brief: SummaryBrief,
    examples_analysis: DraftAnalysis,
    card_facts: dict[uuid.UUID, CardFacts],
) -> None:
    """ADR 0024 s6: nothing from a draft or a user may reach a cached block."""
    example = json.loads((DECKS / "hob.5d9123f8.example1.json").read_text())
    other = brief_for(examples_analysis, card_facts, example["deck"])
    assert other.text != brief.text
    assert (
        draft_summary_request(other, PROMPT, PRIMER)["system"]
        == draft_summary_request(brief, PROMPT, PRIMER)["system"]
    )


def test_the_prompt_file_loses_only_its_comment() -> None:
    assert PROMPT.version == "draft_summary.v1"
    assert PROMPT.text.startswith("You are ")
    assert "<!--" not in PROMPT.text


# --------------------------------------------------------------------------
# Calls, retries and the ledger
# --------------------------------------------------------------------------


def test_a_good_summary_is_returned_and_its_call_recorded(brief: SummaryBrief) -> None:
    ledger = Ledger()
    summary = write(FakeClient(good()), ledger, brief)
    assert summary.lesson == "Trust what wheels."
    assert [(k.pack_number, k.pick_number) for k in summary.key_picks] == [(1, 12)]
    assert (summary.prompt_version, summary.model) == ("draft_summary.v1", MODEL)
    (call,) = ledger.calls
    assert (call.status, call.purpose, call.model, call.subject) == (
        "succeeded",
        "draft_summary",
        "claude-sonnet-5-5",
        "summary",
    )
    # 5,000 x $2 + 3,000 x $0.20 + 400 x $10, per million tokens.
    assert call.cost_usd == Decimal("0.014600")
    assert call.request_id == "req_test"


def test_a_summary_served_by_the_fallback_is_priced_attempt_by_attempt(
    brief: SummaryBrief,
) -> None:
    """The refused attempt and the serving one, each at its own model's price."""
    served = api_message(
        summary_json(),
        model="claude-sonnet-5",
        iterations=[
            {
                "type": "message",
                "model": "claude-sonnet-5-5",
                "input_tokens": 5000,
                "output_tokens": 0,
                "cache_read_input_tokens": 0,
                "cache_creation_input_tokens": 0,
            },
            {
                "type": "fallback_message",
                "model": "claude-sonnet-5",
                "input_tokens": 5000,
                "output_tokens": 400,
                "cache_read_input_tokens": 0,
                "cache_creation_input_tokens": 0,
            },
        ],
    )
    ledger = Ledger()
    summary = write(FakeClient(served), ledger, brief)
    assert summary.model == "claude-sonnet-5"
    (call,) = ledger.calls
    assert call.model == "claude-sonnet-5"
    assert (call.input_tokens, call.output_tokens) == (10_000, 400)
    # 5,000 in at $2, then 5,000 in at $2 and 400 out at $10, per million.
    assert call.cost_usd == Decimal("0.024000")


def test_an_invented_number_is_retried_once(brief: SummaryBrief) -> None:
    invented = api_message(summary_json(lesson="You lost 9.99pp of equity."))
    ledger = Ledger()
    summary = write(FakeClient(invented, good()), ledger, brief)
    assert summary.lesson == "Trust what wheels."
    assert [c.status for c in ledger.calls] == ["invalid", "succeeded"]
    assert ledger.calls[0].error == "lesson: numbers not in the brief: 9.99"


def test_a_key_pick_outside_the_draft_fails_validation(brief: SummaryBrief) -> None:
    bad = api_message(summary_json(key_picks=[{"pack_number": 4, "pick_number": 1}]))
    ledger = Ledger()
    with pytest.raises(DraftSummaryFailed):
        write(FakeClient(bad, bad), ledger, brief)
    assert [c.status for c in ledger.calls] == ["invalid", "invalid"]


def test_json_that_does_not_validate_is_retried_too(brief: SummaryBrief) -> None:
    ledger = Ledger()
    write(FakeClient(api_message('{"draft_arc": '), good()), ledger, brief)
    assert [c.status for c in ledger.calls] == ["invalid", "succeeded"]


def test_a_refusal_of_the_whole_chain_is_recorded_and_not_retried(
    brief: SummaryBrief,
) -> None:
    ledger = Ledger()
    with pytest.raises(DraftSummaryFailed):
        write(FakeClient(api_message("", stop_reason="refusal")), ledger, brief)
    assert [c.status for c in ledger.calls] == ["refused"]


def test_an_api_failure_is_recorded_and_not_retried(brief: SummaryBrief) -> None:
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    ledger = Ledger()
    with pytest.raises(DraftSummaryFailed):
        write(FakeClient(anthropic.APIConnectionError(request=request)), ledger, brief)
    (call,) = ledger.calls
    assert (call.status, call.cost_usd) == ("error", Decimal(0))


def test_at_the_spending_cap_no_call_is_made(brief: SummaryBrief) -> None:
    client = FakeClient(good())
    with pytest.raises(SpendingCapReached):
        write(client, Ledger(spent="5.00"), brief)
    assert client.requests == []


def test_haiku_is_called_and_recorded_under_its_own_name(brief: SummaryBrief) -> None:
    ledger = Ledger()
    client = FakeClient(api_message(summary_json(), model=HAIKU))
    summary = write(client, ledger, brief, model=HAIKU)
    assert summary.model == HAIKU and ledger.calls[0].model == HAIKU
    assert "fallbacks" not in client.requests[0]


def test_the_real_sdk_sends_the_fallback_and_reads_the_answer(
    brief: SummaryBrief,
) -> None:
    """The real client over a mock transport: the wire format, not the fake's."""
    sent: list[tuple[dict[str, Any], str | None]] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        sent.append(
            (json.loads(request.content), request.headers.get("anthropic-beta"))
        )
        return httpx2.Response(200, json=good(), headers={"request-id": "req_wire"})

    client = anthropic.Anthropic(
        api_key="test-key-not-real",
        http_client=anthropic.DefaultHttpxClient(
            transport=httpx2.MockTransport(handler)
        ),
    )
    ledger = Ledger()
    summary = write(client, ledger, brief)
    assert summary.lesson == "Trust what wheels."
    assert ledger.calls[0].request_id == "req_wire"
    ((body, beta),) = sent
    assert body["fallbacks"] == "default"
    assert beta == FALLBACK_BETA
    assert [b["cache_control"]["ttl"] for b in body["system"]] == ["1h", "1h"]
    assert body["output_config"]["format"]["type"] == "json_schema"
