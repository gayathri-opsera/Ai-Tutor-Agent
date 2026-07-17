#!/usr/bin/env python3
"""Entry-point wrapper — delegates to validate_openapi module (WO-016).

Named with a hyphen for CLI ergonomics:
    python scripts/validate-openapi.py --service chat-orchestrator

Logic lives in validate_openapi.py which is importable by unit tests.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from validate_openapi import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
