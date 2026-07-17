"""Shared Pydantic contract models for the Agent Reasoning service.

Migrated from services/agent-reasoning/src/api/agent.py (WO-015).
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ReasonRequest(BaseModel):
    """Request body for POST /api/internal/agent/reason."""

    query: str
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    knowledge_base_id: str | None = None


class ReasonStep(BaseModel):
    """A single ReAct trace step."""

    thought: str | None = None
    action: str | None = None
    action_input: str | None = None
    observation: str | None = None


class ReasonResponse(BaseModel):
    """Response envelope for POST /api/internal/agent/reason."""

    query: str
    sub_queries: list[str] = Field(default_factory=list)
    steps: list[ReasonStep] = Field(default_factory=list)
    final_answer: str | None = None
    confidence: float = 0.0


__all__ = ["ReasonRequest", "ReasonStep", "ReasonResponse"]
