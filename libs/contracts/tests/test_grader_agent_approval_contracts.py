"""Unit tests for libs/contracts/src/grader.py, agent.py, and approval.py."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.agent import ReasonRequest, ReasonResponse, ReasonStep
from src.approval import ApprovalRequest, ApprovalResponse, ApprovalStatus
from src.grader import ChunkGrade, EvaluateRequest, EvaluateResponse

FIXTURES = Path(__file__).parent / "fixtures"


# ── EvaluateRequest ───────────────────────────────────────────────────────────

class TestEvaluateRequest:
    def test_instantiation_defaults(self):
        req = EvaluateRequest(answer="Gradient descent minimizes loss.")
        assert req.answer == "Gradient descent minimizes loss."
        assert req.chunks == []

    def test_with_chunks(self):
        req = EvaluateRequest(
            answer="ML is cool",
            chunks=[{"chunk_id": "c-1", "text": "ML overview", "score": 0.9}],
        )
        assert len(req.chunks) == 1

    def test_missing_answer_rejected(self):
        with pytest.raises(ValidationError):
            EvaluateRequest()

    def test_serialization(self):
        req = EvaluateRequest(answer="a", chunks=[])
        d = req.model_dump()
        assert d["answer"] == "a"
        assert d["chunks"] == []

    def test_deserialization_from_fixture(self):
        fixture = json.loads((FIXTURES / "evaluate_request.json").read_text())
        req = EvaluateRequest(**fixture)
        assert req.answer != ""


# ── EvaluateResponse ──────────────────────────────────────────────────────────

class TestEvaluateResponse:
    def test_instantiation(self):
        resp = EvaluateResponse(
            confidence=0.87, answer="test answer",
            verified=True, source_type="documents"
        )
        assert resp.confidence == 0.87
        assert resp.chunk_grades == []

    def test_with_chunk_grades(self):
        resp = EvaluateResponse(
            confidence=0.5, answer="a", verified=False, source_type="ai_knowledge",
            chunk_grades=[ChunkGrade(chunk_id="c-1", reliability="high", score=0.9)]
        )
        assert len(resp.chunk_grades) == 1

    def test_serialization(self):
        resp = EvaluateResponse(confidence=0.8, answer="a", verified=True, source_type="documents")
        d = resp.model_dump()
        assert "confidence" in d


# ── ReasonRequest ─────────────────────────────────────────────────────────────

class TestReasonRequest:
    def test_defaults(self):
        req = ReasonRequest(query="What is supervised learning?")
        assert req.confidence == 0.8
        assert req.knowledge_base_id is None

    def test_with_kb(self):
        req = ReasonRequest(query="q", confidence=0.5, knowledge_base_id="kb-1")
        assert req.knowledge_base_id == "kb-1"

    def test_confidence_out_of_range(self):
        with pytest.raises(ValidationError):
            ReasonRequest(query="q", confidence=1.5)

    def test_serialization(self):
        req = ReasonRequest(query="test", confidence=0.0)
        d = req.model_dump(exclude_none=True)
        assert "knowledge_base_id" not in d

    def test_deserialization_from_fixture(self):
        fixture = json.loads((FIXTURES / "reason_request.json").read_text())
        req = ReasonRequest(**fixture)
        assert req.query != ""


# ── ReasonResponse ────────────────────────────────────────────────────────────

class TestReasonResponse:
    def test_defaults(self):
        resp = ReasonResponse(query="q")
        assert resp.steps == []
        assert resp.final_answer is None
        assert resp.confidence == 0.0

    def test_with_steps(self):
        resp = ReasonResponse(
            query="q",
            steps=[ReasonStep(thought="think", action="search", observation="result")],
            final_answer="The answer is...",
            confidence=0.75,
        )
        assert len(resp.steps) == 1
        assert resp.steps[0].action == "search"

    def test_serialization(self):
        resp = ReasonResponse(query="q", final_answer="ans", confidence=0.9)
        d = resp.model_dump()
        assert d["final_answer"] == "ans"


# ── ApprovalRequest ───────────────────────────────────────────────────────────

class TestApprovalRequest:
    def test_instantiation(self):
        req = ApprovalRequest(
            entity_type="course", entity_id="course-1", submitter_id="user-42"
        )
        assert req.entity_type == "course"
        assert req.metadata == {}

    def test_with_metadata(self):
        req = ApprovalRequest(
            entity_type="user", entity_id="u-1", submitter_id="admin",
            metadata={"role": "creator"}
        )
        assert req.metadata["role"] == "creator"

    def test_serialization(self):
        req = ApprovalRequest(entity_type="content", entity_id="c-1", submitter_id="s-1")
        d = req.model_dump()
        assert d["entity_type"] == "content"

    def test_deserialization_from_fixture(self):
        fixture = json.loads((FIXTURES / "approval_request.json").read_text())
        req = ApprovalRequest(**fixture)
        assert req.entity_id != ""


# ── ApprovalResponse ──────────────────────────────────────────────────────────

class TestApprovalResponse:
    def test_approved(self):
        resp = ApprovalResponse(
            entity_type="course", entity_id="c-1",
            status=ApprovalStatus.APPROVED, reviewer_id="admin-1"
        )
        assert resp.status == ApprovalStatus.APPROVED

    def test_rejected_with_notes(self):
        resp = ApprovalResponse(
            entity_type="user", entity_id="u-1",
            status=ApprovalStatus.REJECTED,
            reviewer_notes="Content policy violation"
        )
        assert resp.reviewer_notes is not None

    def test_status_enum_values(self):
        assert ApprovalStatus.PENDING == "pending"
        assert ApprovalStatus.NEEDS_CLARIFICATION == "needs_clarification"

    def test_deserialization_from_fixture(self):
        fixture = json.loads((FIXTURES / "approval_response.json").read_text())
        resp = ApprovalResponse(**fixture)
        assert resp.status in list(ApprovalStatus)

    def test_serialization(self):
        resp = ApprovalResponse(entity_type="e", entity_id="id", status=ApprovalStatus.PENDING)
        d = resp.model_dump()
        assert d["status"] == "pending"


# ── __init__ re-exports ───────────────────────────────────────────────────────

def test_init_reexports_grader_agent_approval():
    """Verify __init__.py re-exports all grader, agent, and approval models."""
    from src import (
        ApprovalRequest,
        ApprovalResponse,
        ApprovalStatus,
        EvaluateRequest,
        EvaluateResponse,
        ReasonRequest,
        ReasonResponse,
    )
    assert EvaluateRequest is not None
    assert ReasonRequest is not None
    assert ApprovalStatus.APPROVED == "approved"
