"""Vector DB client re-export from shared lib."""
from __future__ import annotations

import sys
from pathlib import Path

_vdb_src = Path(__file__).resolve().parents[3] / "libs" / "vector-db" / "src"
if str(_vdb_src) not in sys.path:
    sys.path.insert(0, str(_vdb_src))

from client import QueryResult, VectorDBClient, VectorRecord  # noqa: E402

__all__ = ["VectorDBClient", "VectorRecord", "QueryResult"]
