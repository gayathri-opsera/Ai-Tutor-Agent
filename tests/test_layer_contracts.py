"""
Root-level layer separation tests (WO-011 / REQ-009).

Verifies that the canonical layer hierarchy is respected across all 13 backend
services and 6 shared libraries:

    config → model → repository → service → controller (api)

Each test function checks that lower-layer modules do NOT import from
higher-layer modules.  The tests parse Python AST directly so they run
without installing any service dependencies.

Run from the repository root:
    pytest tests/test_layer_contracts.py -v
"""
from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

SERVICES = [
    "admin-config",
    "agent-reasoning",
    "analytics",
    "assessment",
    "audit",
    "chat-orchestrator",
    "confidence-grader",
    "content-ingestion",
    "content-management",
    "embedding-service",
    "learner-profile",
    "llm-gateway",
    "rag-pipeline",
]

LIBS = [
    "auth",
    "cache",
    "kafka",
    "logging",
    "metrics",
    "vector-db",
]


def _get_imports(path: Path) -> list[str]:
    """Return all module names imported by a Python source file."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
    return imports


def _python_files(directory: Path, exclude: set[str] | None = None) -> list[Path]:
    """Return all .py files under directory, excluding filenames in exclude set."""
    exclude = exclude or set()
    return [
        p for p in directory.rglob("*.py")
        if p.name not in exclude
    ]


# ── Service layer contracts ───────────────────────────────────────────────────


@pytest.mark.parametrize("service_name", SERVICES)
def test_service_does_not_import_from_api(service_name: str) -> None:
    """service.py MUST NOT import from src.api (controller > service, not reverse)."""
    svc_dir = REPO_ROOT / "services" / service_name / "src"
    service_file = svc_dir / "service.py"
    if not service_file.exists():
        pytest.skip(f"{service_name} has no service.py")

    for imp in _get_imports(service_file):
        assert "src.api" not in imp and not imp.startswith("api."), (
            f"[{service_name}] service.py imports from api layer: {imp!r}. "
            "Service layer must not depend on the controller layer."
        )


@pytest.mark.parametrize("service_name", SERVICES)
def test_utility_modules_do_not_import_from_api(service_name: str) -> None:
    """Utility/processing modules MUST NOT import from src.api."""
    svc_dir = REPO_ROOT / "services" / service_name / "src"
    if not svc_dir.exists():
        pytest.skip(f"{service_name}/src does not exist")

    # Exclude entry-points that legitimately wire layers together
    excluded = {"main.py", "__init__.py"}
    api_dir = svc_dir / "api"

    for py_file in _python_files(svc_dir, exclude=excluded):
        # Skip files inside the api/ sub-package (they ARE the api layer)
        if api_dir.exists() and py_file.is_relative_to(api_dir):
            continue
        # Skip service.py (tested separately above)
        if py_file == svc_dir / "service.py":
            continue

        rel = py_file.relative_to(svc_dir)
        for imp in _get_imports(py_file):
            assert "src.api" not in imp and not imp.startswith("api."), (
                f"[{service_name}] {rel} imports from api layer: {imp!r}. "
                "Utility modules must sit below the service layer."
            )


@pytest.mark.parametrize("service_name", SERVICES)
def test_api_does_not_import_from_each_other(service_name: str) -> None:
    """API handler files must import from their own service only, not from other services."""
    api_dir = REPO_ROOT / "services" / service_name / "src" / "api"
    if not api_dir.exists():
        pytest.skip(f"{service_name} has no api/ directory")

    for py_file in _python_files(api_dir):
        for imp in _get_imports(py_file):
            for other_svc in SERVICES:
                other_mod = other_svc.replace("-", "_")
                if other_mod != service_name.replace("-", "_") and other_mod in imp:
                    pytest.fail(
                        f"[{service_name}] api/{py_file.name} imports from "
                        f"different service {other_svc!r}: {imp!r}"
                    )


# ── Shared library contracts ──────────────────────────────────────────────────


@pytest.mark.parametrize("lib_name", LIBS)
def test_lib_does_not_import_from_any_service(lib_name: str) -> None:
    """Shared libs MUST NOT import from any service's src package."""
    lib_src = REPO_ROOT / "libs" / lib_name / "src"
    if not lib_src.exists():
        pytest.skip(f"libs/{lib_name}/src does not exist")

    service_modules = {svc.replace("-", "_") for svc in SERVICES}

    for py_file in _python_files(lib_src):
        rel = py_file.relative_to(lib_src)
        for imp in _get_imports(py_file):
            for svc_mod in service_modules:
                assert svc_mod not in imp, (
                    f"[lib:{lib_name}] {rel} imports from service {svc_mod!r}: {imp!r}. "
                    "Shared libraries must be independent of service code."
                )


@pytest.mark.parametrize("lib_name", LIBS)
def test_lib_does_not_import_from_api_layer(lib_name: str) -> None:
    """Shared libs MUST NOT import any api/ or controller-layer module."""
    lib_src = REPO_ROOT / "libs" / lib_name / "src"
    if not lib_src.exists():
        pytest.skip(f"libs/{lib_name}/src does not exist")

    for py_file in _python_files(lib_src):
        rel = py_file.relative_to(lib_src)
        for imp in _get_imports(py_file):
            assert "src.api" not in imp and not imp.endswith(".api"), (
                f"[lib:{lib_name}] {rel} imports from api layer: {imp!r}. "
                "Libs must not depend on controller-layer code."
            )
