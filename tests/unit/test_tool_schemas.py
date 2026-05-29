# Owner: Nasser
"""Unit tests for agent-tool argument schemas (task T054, contract C-T2-2).

The Pydantic boundary is load-bearing: it is the only thing standing between
LLM-supplied JSON and the tenant-scoped business logic. These tests pin the
guarantees the rest of Track 2 depends on:

- `extra="forbid"` rejects LLM-supplied tenant_id / session_id / actor_id
  (the trusted identifiers are passed by the caller, never the model).
- Field length and pattern constraints reject oversize / malformed inputs.
- Defaults and bounds match the contract values exactly.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.agent.tools import CaptureLeadArgs, EscalateArgs, RagSearchArgs


# ---------------------------------------------------------------------------
# extra="forbid" — trusted-context fields cannot be supplied by the LLM.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("forbidden_field", ["tenant_id", "session_id", "actor_id"])
def test_rag_search_args_rejects_trusted_context_fields(forbidden_field: str) -> None:
    payload = {"query": "what plans do you offer?", forbidden_field: "evil-value"}
    with pytest.raises(ValidationError) as exc_info:
        RagSearchArgs(**payload)
    assert any(
        err["type"] == "extra_forbidden" and err["loc"] == (forbidden_field,)
        for err in exc_info.value.errors()
    )


@pytest.mark.parametrize("forbidden_field", ["tenant_id", "session_id", "actor_id"])
def test_capture_lead_args_rejects_trusted_context_fields(forbidden_field: str) -> None:
    payload = {"intent": "Visitor wants a follow-up call.", forbidden_field: "evil-value"}
    with pytest.raises(ValidationError) as exc_info:
        CaptureLeadArgs(**payload)
    assert any(
        err["type"] == "extra_forbidden" and err["loc"] == (forbidden_field,)
        for err in exc_info.value.errors()
    )


@pytest.mark.parametrize("forbidden_field", ["tenant_id", "session_id", "actor_id"])
def test_escalate_args_rejects_trusted_context_fields(forbidden_field: str) -> None:
    payload = {"reason": "Visitor is upset.", forbidden_field: "evil-value"}
    with pytest.raises(ValidationError) as exc_info:
        EscalateArgs(**payload)
    assert any(
        err["type"] == "extra_forbidden" and err["loc"] == (forbidden_field,)
        for err in exc_info.value.errors()
    )


# ---------------------------------------------------------------------------
# RagSearchArgs bounds.
# ---------------------------------------------------------------------------


def test_rag_search_args_defaults_top_k_to_five() -> None:
    args = RagSearchArgs(query="anything")
    assert args.top_k == 5


def test_rag_search_args_rejects_empty_query() -> None:
    with pytest.raises(ValidationError):
        RagSearchArgs(query="")


def test_rag_search_args_rejects_query_over_500_chars() -> None:
    with pytest.raises(ValidationError):
        RagSearchArgs(query="x" * 501)


def test_rag_search_args_clamps_top_k_range() -> None:
    with pytest.raises(ValidationError):
        RagSearchArgs(query="ok", top_k=0)
    with pytest.raises(ValidationError):
        RagSearchArgs(query="ok", top_k=11)


# ---------------------------------------------------------------------------
# CaptureLeadArgs bounds.
# ---------------------------------------------------------------------------


def test_capture_lead_args_accepts_minimal_payload() -> None:
    args = CaptureLeadArgs(intent="Wants pricing details.")
    assert args.intent == "Wants pricing details."
    assert args.name is None
    assert args.contact is None


def test_capture_lead_args_rejects_oversized_intent() -> None:
    with pytest.raises(ValidationError):
        CaptureLeadArgs(intent="x" * 1001)


def test_capture_lead_args_rejects_empty_intent() -> None:
    with pytest.raises(ValidationError):
        CaptureLeadArgs(intent="")


def test_capture_lead_args_accepts_email_contact() -> None:
    args = CaptureLeadArgs(intent="follow up", contact="visitor@example.com")
    assert args.contact == "visitor@example.com"


def test_capture_lead_args_accepts_phone_contact() -> None:
    args = CaptureLeadArgs(intent="follow up", contact="+1 (415) 555-0100")
    assert args.contact == "+1 (415) 555-0100"


def test_capture_lead_args_rejects_invalid_contact_regex() -> None:
    with pytest.raises(ValidationError):
        CaptureLeadArgs(intent="follow up", contact="not-an-email-or-phone")


def test_capture_lead_args_rejects_empty_name() -> None:
    with pytest.raises(ValidationError):
        CaptureLeadArgs(intent="follow up", name="")


def test_capture_lead_args_rejects_oversized_name() -> None:
    with pytest.raises(ValidationError):
        CaptureLeadArgs(intent="follow up", name="x" * 201)


# ---------------------------------------------------------------------------
# EscalateArgs bounds.
# ---------------------------------------------------------------------------


def test_escalate_args_accepts_reason() -> None:
    args = EscalateArgs(reason="Visitor explicitly asked for a human.")
    assert args.reason.startswith("Visitor")


def test_escalate_args_rejects_empty_reason() -> None:
    with pytest.raises(ValidationError):
        EscalateArgs(reason="")


def test_escalate_args_rejects_oversized_reason() -> None:
    with pytest.raises(ValidationError):
        EscalateArgs(reason="x" * 281)
