"""Unit tests for scripts/validate-openapi.py."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Add the scripts/ dir to path so we can import validate-openapi
SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

from validate_openapi import detect_breaking_changes, load_schema  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


def _load(filename: str) -> dict:
    return json.loads((FIXTURES / filename).read_text())


# ── detect_breaking_changes ───────────────────────────────────────────────────

class TestDetectBreakingChanges:
    def test_identical_schemas_no_issues(self):
        baseline = _load("matching_baseline.json")
        current = _load("matching_current.json")
        issues = detect_breaking_changes(baseline, current)
        assert issues == []

    def test_removed_path_is_breaking(self):
        baseline = _load("baseline.json")
        # Current schema is missing /api/v1/items/{item_id} and /health
        current = _load("breaking_removed_endpoint.json")
        issues = detect_breaking_changes(baseline, current)
        removed = [i for i in issues if "REMOVED path" in i]
        assert len(removed) >= 2  # /api/v1/items/{item_id} and /health removed

    def test_removed_method_is_breaking(self):
        """Remove the GET method from /api/v1/items — only POST remains."""
        baseline = _load("baseline.json")
        current = _load("breaking_removed_endpoint.json")
        issues = detect_breaking_changes(baseline, current)
        # GET /api/v1/items is also removed in the breaking fixture
        method_issues = [i for i in issues if "REMOVED" in i]
        assert len(method_issues) > 0

    def test_new_required_field_is_breaking(self):
        """Adding a new required field breaks existing callers."""
        baseline = _load("baseline.json")
        current = _load("breaking_new_required_field.json")
        issues = detect_breaking_changes(baseline, current)
        breaking = [i for i in issues if "new required fields" in i.lower() or "BREAKING" in i]
        assert any("category" in i for i in breaking)

    def test_added_optional_field_not_breaking(self):
        """Adding a new optional (non-required) field is backward compatible."""
        baseline = _load("baseline.json")
        # non_breaking adds 'description' as an optional field (not in 'required')
        current = _load("non_breaking_optional_field.json")
        issues = detect_breaking_changes(baseline, current)
        assert issues == []

    def test_removed_required_field_is_breaking(self):
        """Removing a previously-required field is a breaking change."""
        baseline = _load("breaking_new_required_field.json")  # has "category" required
        current = _load("baseline.json")                       # "category" removed from required
        issues = detect_breaking_changes(baseline, current)
        breaking = [i for i in issues if "required fields removed" in i.lower()]
        assert any("category" in i for i in breaking)

    def test_removed_status_code_is_breaking(self):
        """Removing a previously-documented response status code is breaking."""
        baseline = _load("baseline.json")
        # Make a current schema that drops 404 from /api/v1/items/{item_id}
        current = json.loads((FIXTURES / "baseline.json").read_text())
        current["paths"]["/api/v1/items/{item_id}"]["get"]["responses"] = {
            "200": {"description": "OK"}
        }
        issues = detect_breaking_changes(baseline, current)
        removed_code = [i for i in issues if "status codes removed" in i.lower()]
        assert len(removed_code) > 0
        assert "404" in removed_code[0] or "422" in removed_code[0]

    def test_empty_baseline_no_issues(self):
        """Empty baseline produces no issues (no endpoints to compare)."""
        baseline = {"openapi": "3.1.0", "info": {}, "paths": {}}
        current = _load("baseline.json")
        issues = detect_breaking_changes(baseline, current)
        assert issues == []

    def test_added_new_endpoint_not_breaking(self):
        """Adding a completely new endpoint is not a breaking change."""
        baseline = _load("baseline.json")
        current = json.loads(json.dumps(baseline))  # deep copy
        current["paths"]["/api/v1/newresource"] = {
            "get": {"summary": "New", "responses": {"200": {"description": "OK"}}}
        }
        issues = detect_breaking_changes(baseline, current)
        assert issues == []


# ── load_schema ───────────────────────────────────────────────────────────────

class TestLoadSchema:
    def test_loads_from_path(self):
        schema = load_schema(FIXTURES / "baseline.json")
        assert "paths" in schema

    def test_loads_from_string_path(self):
        schema = load_schema(str(FIXTURES / "baseline.json"))
        assert schema["openapi"] == "3.1.0"

    def test_passes_through_dict(self):
        d = {"openapi": "3.1.0", "paths": {}}
        assert load_schema(d) is d
