"""Shared Pydantic contract models for the approval workflow.

Defined per the architecture specification (WO-015) for future use
in the course-content and user-registration approval flows.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_CLARIFICATION = "needs_clarification"


class ApprovalRequest(BaseModel):
    """Request to submit an entity for admin approval."""

    entity_type: str = Field(..., description="Type of entity: 'user' | 'course' | 'content'")
    entity_id: str
    submitter_id: str
    metadata: dict = Field(default_factory=dict)


class ApprovalResponse(BaseModel):
    """Response after an admin acts on an approval request."""

    entity_type: str
    entity_id: str
    status: ApprovalStatus
    reviewer_id: str | None = None
    reviewer_notes: str | None = None


__all__ = ["ApprovalStatus", "ApprovalRequest", "ApprovalResponse"]
