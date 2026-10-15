"""Writing a Pick Note: the request, the retry, and the ledger (ADR 0024 s6-s8).

Claude is replaced by a fake at the SDK boundary, `client.messages.create`,
which answers with what the API would. One test runs the real SDK client
over a mock transport, to check the wire format the fake can't. The ledger is in memory. Nothing here makes a network call.
"""

import json
import uuid
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import anthropic
import httpx2
import pytest
from anthropic.types import Message

from boostertutor.analysis.fitness import FitnessConfig
from boostertutor.briefing import PickBrief, pick_brief
from boostertutor.briefing.card_facts import CardFacts
from boostertutor.llm.pick_note import (
    MODEL,
    OUTPUT_FORMAT,
    PickNoteFailed,
    load_prompt,
    pick_note_request,
    write_pick_note,
)
from boostertutor.llm.spending import SpendingCapReached
from boostertutor.models import LlmCall
from boostertutor.schemas.draft_analysis import DraftAnalysis

PROMPT = load_prompt("pick_note.v1")
CAP = Decimal("5.00")


# --------------------------------------------------------------------------
# Fakes
# --------------------------------------------------------------------------


def api_message(text: str, stop_reason: str = "end_turn") -> dict[str, Any]:
    """A Messages API response body, as the API sends it."""
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": MODEL,
        "content": [{"type": "text", "text": text}],
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {
            "input_tokens": 900,
            "output_tokens": 150,
            "cache_read_input_tokens": 2000,
            "cache_creation_input_tokens": 0,
        },
    }


class FakeClient:
    """Answers each call with the next response in `answers`."""

    def __init__(self, *answers: dict[str, Any] | Exception) -> None:
        self.answers = list(answers)
        self.requests: list[dict[str, Any]] = []
        self.messages = SimpleNamespace(create=self._create)

    def with_options(self, **_: Any) -> "FakeClient":
        return self

    def _create(self, **request: Any) -> Message:
        self.requests.append(request)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        message = Message.model_validate(answer)
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


def good(pack: int = 1, pick: int = 1) -> dict[str, Any]:
    note = "Pinecone Strike was the pick: it cost you 2.2pp."
    return api_message(
        json.dumps({"pack_number": pack, "pick_number": pick, "note": note})
    )


@pytest.fixture(scope="module")
def brief(analysis: DraftAnalysis, card_facts: dict[uuid.UUID, CardFacts]) -> PickBrief:
    return pick_brief(
        analysis, card_facts, FitnessConfig(), pack_number=1, pick_number=1
    )


def write(client: FakeClient, ledger: Ledger, brief: PickBrief) -> Any:
    return write_pick_note(
        client,  # type: ignore[arg-type]
        ledger,
        brief,
        prompt=PROMPT,
        cap=CAP,
        draft_key="17lands:d9ac6765",
        user_id=None,
    )


# --------------------------------------------------------------------------
# The request
# --------------------------------------------------------------------------


def test_the_instructions_are_one_cached_block_and_the_brief_comes_after(
    brief: PickBrief,
) -> None:
    request = pick_note_request(brief, PROMPT)
    assert request["model"] == "claude-haiku-5-5"
    assert request["output_config"] == {"effort": "low", "format": OUTPUT_FORMAT}
    assert set(OUTPUT_FORMAT["schema"]["properties"]) == {  # type: ignore[index]
        "pack_number",
        "pick_number",
        "note",
    }
    assert request["system"] == [
        {
            "type": "text",
            "text": PROMPT.text,
            "cache_control": {"type": "ephemeral", "ttl": "1h"},
        }
    ]
    assert request["messages"] == [{"role": "user", "content": brief.text}]


def test_the_cached_block_is_byte_identical_across_drafts(
    brief: PickBrief,
    eval_analysis: DraftAnalysis,
    card_facts: dict[uuid.UUID, CardFacts],
) -> None:
    """ADR 0024 s6: nothing from a draft or a user may reach the cached block."""
    other = pick_brief(
        eval_analysis, card_facts, FitnessConfig(), pack_number=2, pick_number=3
    )
    assert other.text != brief.text
    assert (
        pick_note_request(other, PROMPT)["system"]
        == pick_note_request(brief, PROMPT)["system"]
    )


def test_the_prompt_file_loses_only_its_comment() -> None:
    assert PROMPT.version == "pick_note.v1"
    assert PROMPT.text.startswith("You are a Magic: the Gathering Limited coach.")
    assert "<!--" not in PROMPT.text


# --------------------------------------------------------------------------
# Calls, retries and the ledger
# --------------------------------------------------------------------------


def test_a_good_note_is_returned_and_its_call_recorded(brief: PickBrief) -> None:
    ledger = Ledger()
    note = write(FakeClient(good()), ledger, brief)
    assert (note.pack_number, note.pick_number, note.kind) == (1, 1, "critical")
    assert note.note == "Pinecone Strike was the pick: it cost you 2.2pp."
    assert note.prompt_version == "pick_note.v1"
    (call,) = ledger.calls
    assert (call.status, call.purpose, call.model, call.prompt_version) == (
        "succeeded",
        "pick_note",
        "claude-haiku-5-5",
        "pick_note.v1",
    )
    assert (call.draft_key, call.subject, call.user_id) == (
        "17lands:d9ac6765",
        "P1p1",
        None,
    )
    assert (
        call.input_tokens,
        call.cache_read_tokens,
        call.cache_write_tokens,
        call.output_tokens,
    ) == (900, 2000, 0, 150)
    # 900 x $0.10 + 2,000 x $0.01 + 150 x $0.50, per million tokens.
    assert call.cost_usd == Decimal("0.000185")
    assert call.request_id == "req_test"
    assert call.latency_ms >= 0


def test_an_invalid_note_is_retried_once(brief: PickBrief) -> None:
    invented = api_message(
        json.dumps({"pack_number": 1, "pick_number": 1, "note": "It cost 9.9pp."})
    )
    ledger = Ledger()
    note = write(FakeClient(invented, good()), ledger, brief)
    assert note.note.startswith("Pinecone Strike")
    assert [c.status for c in ledger.calls] == ["invalid", "succeeded"]
    assert ledger.calls[0].error == "numbers not in the brief: 9.9"


def test_json_that_does_not_validate_is_retried_too(brief: PickBrief) -> None:
    ledger = Ledger()
    note = write(FakeClient(api_message('{"note": '), good()), ledger, brief)
    assert note.pick_number == 1
    assert [c.status for c in ledger.calls] == ["invalid", "succeeded"]


def test_two_invalid_notes_fail_cleanly(brief: PickBrief) -> None:
    bad = api_message(json.dumps({"pack_number": 1, "pick_number": 2, "note": "x"}))
    ledger = Ledger()
    with pytest.raises(PickNoteFailed):
        write(FakeClient(bad, bad), ledger, brief)
    assert [c.status for c in ledger.calls] == ["invalid", "invalid"]


def test_a_refusal_is_recorded_and_not_retried(brief: PickBrief) -> None:
    ledger = Ledger()
    with pytest.raises(PickNoteFailed):
        write(FakeClient(api_message("", stop_reason="refusal")), ledger, brief)
    assert [c.status for c in ledger.calls] == ["refused"]


def test_an_api_failure_is_recorded_and_not_retried(brief: PickBrief) -> None:
    """The SDK has already retried a 429 or a 5xx twice by the time it raises."""
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    ledger = Ledger()
    with pytest.raises(PickNoteFailed):
        write(FakeClient(anthropic.APIConnectionError(request=request)), ledger, brief)
    (call,) = ledger.calls
    assert (call.status, call.cost_usd, call.input_tokens) == ("error", Decimal(0), 0)


def test_at_the_spending_cap_no_call_is_made(brief: PickBrief) -> None:
    client = FakeClient(good())
    ledger = Ledger(spent="5.00")
    with pytest.raises(SpendingCapReached):
        write(client, ledger, brief)
    assert client.requests == [] and ledger.calls == []


def test_the_cap_is_checked_again_before_the_retry(brief: PickBrief) -> None:
    """A retry is a second billed call, so it must not slip past the cap."""
    invented = api_message(
        json.dumps({"pack_number": 1, "pick_number": 1, "note": "It cost 9.9pp."})
    )

    class FillsUp(Ledger):
        def record(self, call: LlmCall) -> None:
            super().record(call)
            self.spent = CAP

    client = FakeClient(invented, good())
    with pytest.raises(SpendingCapReached):
        write(client, FillsUp(), brief)
    assert len(client.requests) == 1


def test_the_real_sdk_sends_the_request_and_reads_the_answer(brief: PickBrief) -> None:
    """The real client over a mock transport: the wire format, not the fake's.

    Checks what the fake can't: that the SDK accepts these arguments, turns
    `PickNoteOutput` into a JSON schema with the effort beside it, keeps
    the cache marker, and that a raw response still parses.
    """
    sent: list[dict[str, Any]] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        sent.append(json.loads(request.content))
        return httpx2.Response(200, json=good(), headers={"request-id": "req_wire"})

    client = anthropic.Anthropic(
        api_key="test-key-not-real",
        http_client=anthropic.DefaultHttpxClient(
            transport=httpx2.MockTransport(handler)
        ),
    )
    ledger = Ledger()
    note = write_pick_note(
        client,
        ledger,
        brief,
        prompt=PROMPT,
        cap=CAP,
        draft_key=None,
        user_id=None,
    )
    assert note.note.startswith("Pinecone Strike")
    assert ledger.calls[0].request_id == "req_wire"
    (body,) = sent
    assert body["output_config"]["effort"] == "low"
    assert body["output_config"]["format"]["type"] == "json_schema"
    assert set(body["output_config"]["format"]["schema"]["properties"]) == {
        "pack_number",
        "pick_number",
        "note",
    }
    assert body["system"][0]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}
    assert body["messages"] == [{"role": "user", "content": brief.text}]
