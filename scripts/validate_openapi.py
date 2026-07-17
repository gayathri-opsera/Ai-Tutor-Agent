#!/usr/bin/env python3
"""OpenAPI contract validation script (WO-016).

Imports each FastAPI service app directly (no running server needed), generates
its OpenAPI schema using ``app.openapi()``, then diffs it against the stored
baseline in ``libs/contracts/openapi/``.

Exit codes
----------
0  — all schemas match baselines (or ``--update`` was used to save new baselines)
1  — one or more breaking changes detected
2  — usage / configuration error

Usage
-----
    # Validate a single service
    python scripts/validate-openapi.py --service chat-orchestrator

    # Validate all services
    python scripts/validate-openapi.py --all

    # Update a single baseline (intentional contract change)
    python scripts/validate-openapi.py --service rag-pipeline --update

    # Update all baselines (run after intentional API changes)
    python scripts/validate-openapi.py --all --update
"""
from __future__ import annotations

import argparse
import importlib
import json
import sys
import textwrap
import unittest.mock as mock
from pathlib import Path
from typing import Any

# ── Paths ─────────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent.parent
BASELINES_DIR = REPO_ROOT / "libs" / "contracts" / "openapi"
CONTRACTS_SRC = str(REPO_ROOT / "libs" / "contracts" / "src")
VECTOR_DB_SRC = str(REPO_ROOT / "libs" / "vector-db" / "src")

# ── Service registry ──────────────────────────────────────────────────────────
# Each entry describes how to import the FastAPI app for a service.
#
# Keys
# ----
# service_dir   : path to the service root (parent of src/)
# app_attr      : "create_app" (factory) or "app" (module-level instance)
# mock_modules  : modules to mock before importing (missing native deps)
# extra_paths   : extra PYTHONPATH entries needed (e.g. shared libs)
# factory_repo  : if True, pass repository=MockSessionRepository() to factory

SERVICES: dict[str, dict] = {
    "chat-orchestrator": {
        "service_dir": "services/chat-orchestrator",
        "app_attr": "create_app",
        "mock_modules": ["asyncpg", "sse_starlette", "sse_starlette.sse"],
        "extra_paths": [],
        "factory_repo": True,
    },
    "rag-pipeline": {
        "service_dir": "services/rag-pipeline",
        "app_attr": "create_app",
        "mock_modules": ["asyncpg", "weaviate"],
        "extra_paths": [VECTOR_DB_SRC],
        "factory_repo": False,
    },
    "llm-gateway": {
        "service_dir": "services/llm-gateway",
        "app_attr": "create_app",
        "mock_modules": ["openai", "anthropic"],
        "extra_paths": [],
        "factory_repo": False,
    },
    "embedding-service": {
        "service_dir": "services/embedding-service",
        "app_attr": "create_app",
        "mock_modules": ["sentence_transformers", "torch", "faster_whisper"],
        "extra_paths": [],
        "factory_repo": False,
    },
    "confidence-grader": {
        "service_dir": "services/confidence-grader",
        "app_attr": "create_app",
        "mock_modules": [],
        "extra_paths": [],
        "factory_repo": False,
    },
    "agent-reasoning": {
        "service_dir": "services/agent-reasoning",
        "app_attr": "create_app",
        "mock_modules": ["anthropic", "openai", "aiohttp"],
        "extra_paths": [],
        "factory_repo": False,
    },
    "admin-config": {
        "service_dir": "services/admin-config",
        "app_attr": "app",
        "mock_modules": [],
        "extra_paths": [],
        "factory_repo": False,
    },
    "analytics": {
        "service_dir": "services/analytics",
        "app_attr": "app",
        "mock_modules": ["asyncpg"],
        "extra_paths": [],
        "factory_repo": False,
    },
    "assessment": {
        "service_dir": "services/assessment",
        "app_attr": "app",
        "mock_modules": ["asyncpg"],
        "extra_paths": [],
        "factory_repo": False,
    },
    "audit": {
        "service_dir": "services/audit",
        "app_attr": "app",
        "mock_modules": ["asyncpg", "aiokafka"],
        "extra_paths": [],
        "factory_repo": False,
    },
    "content-ingestion": {
        "service_dir": "services/content-ingestion",
        "app_attr": "create_app",
        "mock_modules": ["asyncpg", "aiokafka", "faster_whisper"],
        "extra_paths": [],
        "factory_repo": False,
    },
    "content-management": {
        "service_dir": "services/content-management",
        "app_attr": "app",
        "mock_modules": ["asyncpg", "aiokafka"],
        "extra_paths": [],
        "factory_repo": False,
    },
    "learner-profile": {
        "service_dir": "services/learner-profile",
        "app_attr": "app",
        "mock_modules": ["asyncpg", "aiokafka"],
        "extra_paths": [],
        "factory_repo": False,
    },
}

# ── Schema loading ─────────────────────────────────────────────────────────────

def load_schema(schema_or_path: dict | Path | str) -> dict[str, Any]:
    """Return an OpenAPI schema dict from a dict or a JSON file path."""
    if isinstance(schema_or_path, dict):
        return schema_or_path
    return json.loads(Path(schema_or_path).read_text())


def generate_schema(service_name: str) -> dict[str, Any]:
    """Import the service's FastAPI app and return its generated OpenAPI schema."""
    cfg = SERVICES[service_name]
    svc_root = str(REPO_ROOT / cfg["service_dir"])

    # Build the Python path for this service
    paths_to_add = [svc_root, CONTRACTS_SRC] + cfg["extra_paths"]
    for p in paths_to_add:
        sys.path.insert(0, p)

    # Apply module mocks
    mocked: list[str] = []
    for mod_name in cfg["mock_modules"]:
        if mod_name not in sys.modules:
            sys.modules[mod_name] = mock.MagicMock()
            mocked.append(mod_name)

    try:
        # Clear any previously loaded service src modules
        stale = [k for k in list(sys.modules) if k == "src" or k.startswith("src.")]
        for k in stale:
            del sys.modules[k]

        service_module = importlib.import_module("src.main")
        app_attr = getattr(service_module, cfg["app_attr"])

        if callable(app_attr) and cfg["app_attr"] == "create_app":
            if cfg["factory_repo"]:
                # Lazy import here to avoid circular deps
                from src.repository import MockSessionRepository  # noqa: PLC0415
                app = app_attr(repository=MockSessionRepository())
            else:
                app = app_attr()
        else:
            # Module-level app instance
            app = app_attr

        return app.openapi()
    finally:
        for p in paths_to_add:
            if p in sys.path:
                sys.path.remove(p)
        for mod_name in mocked:
            sys.modules.pop(mod_name, None)
        stale = [k for k in list(sys.modules) if k == "src" or k.startswith("src.")]
        for k in stale:
            del sys.modules[k]


# ── Breaking change detection ──────────────────────────────────────────────────

def _extract_paths_summary(schema: dict) -> dict[str, dict]:
    """Return {path: {method: {"required_fields": [...], "status_codes": [...]}}}."""
    result: dict[str, dict] = {}
    for path, path_item in schema.get("paths", {}).items():
        result[path] = {}
        for method, operation in path_item.items():
            if not isinstance(operation, dict):
                continue
            # Gather required request body fields
            req_fields: list[str] = []
            req_body = operation.get("requestBody", {})
            if req_body:
                for _media, media_val in req_body.get("content", {}).items():
                    schema_ref = media_val.get("schema", {})
                    req_fields = schema_ref.get("required", [])
            result[path][method.upper()] = {
                "required_fields": req_fields,
                "status_codes": list(operation.get("responses", {}).keys()),
                "operation_id": operation.get("operationId", ""),
            }
    return result


def detect_breaking_changes(
    baseline: dict[str, Any], current: dict[str, Any]
) -> list[str]:
    """Return a list of human-readable breaking change descriptions.

    Breaking changes:
    - Removed endpoint (path + method combo)
    - Changed HTTP method for a path
    - Added or removed required request body fields
    - Changed status codes on existing endpoints
    """
    issues: list[str] = []

    base_paths = _extract_paths_summary(baseline)
    curr_paths = _extract_paths_summary(current)

    # Detect removed endpoints
    for path, methods in base_paths.items():
        if path not in curr_paths:
            issues.append(f"REMOVED path: {path}")
            continue
        for method in methods:
            if method not in curr_paths[path]:
                issues.append(f"REMOVED method: {method} {path}")

    # Detect changed required fields and status codes
    for path, methods in base_paths.items():
        if path not in curr_paths:
            continue
        for method, base_op in methods.items():
            if method not in curr_paths[path]:
                continue
            curr_op = curr_paths[path][method]

            base_req = set(base_op["required_fields"])
            curr_req = set(curr_op["required_fields"])

            added_required = curr_req - base_req
            removed_required = base_req - curr_req

            if added_required:
                issues.append(
                    f"BREAKING: {method} {path} — new required fields: {sorted(added_required)}"
                )
            if removed_required:
                issues.append(
                    f"BREAKING: {method} {path} — required fields removed: {sorted(removed_required)}"
                )

            base_codes = set(base_op["status_codes"])
            curr_codes = set(curr_op["status_codes"])
            removed_codes = base_codes - curr_codes
            if removed_codes:
                issues.append(
                    f"BREAKING: {method} {path} — response status codes removed: {sorted(removed_codes)}"
                )

    return issues


# ── Main logic ─────────────────────────────────────────────────────────────────

def validate_service(service_name: str, update: bool = False) -> bool:
    """Validate (or update) a single service. Returns True if OK."""
    baseline_path = BASELINES_DIR / f"{service_name}.openapi.json"

    print(f"\n{'─' * 60}")
    print(f"Service: {service_name}")

    try:
        current = generate_schema(service_name)
    except Exception as exc:
        print(f"  ❌ ERROR generating schema: {exc}")
        return False

    if update:
        baseline_path.write_text(json.dumps(current, indent=2))
        print(f"  ✅ Baseline updated → {baseline_path.relative_to(REPO_ROOT)}")
        return True

    if not baseline_path.exists():
        print(f"  ❌ No baseline found at {baseline_path.relative_to(REPO_ROOT)}")
        print(f"     Run with --update to create it.")
        return False

    baseline = load_schema(baseline_path)
    issues = detect_breaking_changes(baseline, current)

    if not issues:
        paths_count = len(current.get("paths", {}))
        print(f"  ✅ Schema matches baseline ({paths_count} paths)")
        return True

    print(f"  ❌ {len(issues)} breaking change(s) detected:")
    for issue in issues:
        print(f"     • {issue}")
    print(
        "\n  To update the baseline after an intentional API change, run:\n"
        f"     python scripts/validate-openapi.py --service {service_name} --update"
    )
    return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="OpenAPI contract validation — compares generated schemas to baselines.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(
            """
            Examples:
              python scripts/validate-openapi.py --service chat-orchestrator
              python scripts/validate-openapi.py --all
              python scripts/validate-openapi.py --service rag-pipeline --update
              python scripts/validate-openapi.py --all --update
            """
        ),
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--service", choices=list(SERVICES), help="Validate a specific service")
    target.add_argument("--all", action="store_true", help="Validate all registered services")
    parser.add_argument(
        "--update", action="store_true", help="Update baseline instead of validating"
    )
    args = parser.parse_args(argv)

    services_to_check = [args.service] if args.service else list(SERVICES)
    results: dict[str, bool] = {}

    for svc in services_to_check:
        results[svc] = validate_service(svc, update=args.update)

    print(f"\n{'═' * 60}")
    passed = sum(v for v in results.values())
    failed = len(results) - passed

    if args.update:
        print(f"✅ Updated {passed} baseline(s).")
        return 0

    print(f"Results: {passed} passed, {failed} failed")
    if failed:
        print("\n❌ CONTRACT VALIDATION FAILED — see breaking changes above.")
        return 1

    print("\n✅ All contract validations passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
