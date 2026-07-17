"""Unit tests for approval Kafka event schemas (WO-182)."""
from __future__ import annotations

import json
import pytest

from src.schemas.events import (
    UserApprovalRequestedEvent,
    UserApprovalCompletedEvent,
    CourseApprovalRequestedEvent,
    CourseApprovalCompletedEvent,
)


class TestUserApprovalRequestedEvent:
    def test_default_event_type(self):
        ev = UserApprovalRequestedEvent(
            actor_id="kc-user-1",
            user_id="db-uuid-1",
            keycloak_id="kc-user-1",
            email_hash="abc123",
        )
        assert ev.event_type == "user.approval.requested"

    def test_has_required_envelope_fields(self):
        ev = UserApprovalRequestedEvent(
            actor_id="kc-user-1",
            user_id="db-uuid-1",
            keycloak_id="kc-user-1",
            email_hash="abc123",
        )
        assert ev.event_id
        assert ev.timestamp
        assert ev.schema_version == "1.0"
        assert ev.resource_type == "user"

    def test_serialises_to_json(self):
        ev = UserApprovalRequestedEvent(
            actor_id="kc-user-1",
            user_id="db-uuid-1",
            keycloak_id="kc-user-1",
            email_hash="abc123",
        )
        data = json.loads(ev.model_dump_json())
        assert data["event_type"] == "user.approval.requested"
        assert data["actor_id"] == "kc-user-1"


class TestUserApprovalCompletedEvent:
    def test_approved_outcome(self):
        ev = UserApprovalCompletedEvent(
            actor_id="admin-1",
            user_id="db-uuid-1",
            keycloak_id="kc-user-1",
            outcome="approved",
            roles_assigned=["Learner"],
        )
        assert ev.outcome == "approved"
        assert "Learner" in ev.roles_assigned

    def test_rejected_outcome_no_roles(self):
        ev = UserApprovalCompletedEvent(
            actor_id="admin-1",
            user_id="db-uuid-1",
            keycloak_id="kc-user-1",
            outcome="rejected",
        )
        assert ev.outcome == "rejected"
        assert ev.roles_assigned == []


class TestCourseApprovalRequestedEvent:
    def test_defaults(self):
        ev = CourseApprovalRequestedEvent(
            actor_id="creator-1",
            kb_id="kb-uuid-1",
            course_name="Python 101",
        )
        assert ev.event_type == "course.approval.requested"
        assert ev.resource_type == "course"


class TestCourseApprovalCompletedEvent:
    def test_approved_no_reason(self):
        ev = CourseApprovalCompletedEvent(
            actor_id="admin-1",
            kb_id="kb-uuid-1",
            outcome="approved",
        )
        assert ev.outcome == "approved"
        assert ev.reason == ""

    def test_rejected_with_reason(self):
        ev = CourseApprovalCompletedEvent(
            actor_id="admin-1",
            kb_id="kb-uuid-1",
            outcome="rejected",
            reason="Insufficient content quality",
        )
        assert ev.reason == "Insufficient content quality"

    def test_all_outcomes_valid(self):
        for outcome in ("approved", "rejected", "clarification_requested"):
            ev = CourseApprovalCompletedEvent(
                actor_id="admin-1", kb_id="kb-1", outcome=outcome
            )
            assert ev.outcome == outcome
