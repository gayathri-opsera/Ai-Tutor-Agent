"""Vector DB client re-export from shared lib.

In Docker the PYTHONPATH already includes /app/libs/vector-db/src via
Dockerfile.service, so we can import directly.
"""
from __future__ import annotations

from client import QueryResult, VectorDBClient, VectorRecord

__all__ = ["VectorDBClient", "VectorRecord", "QueryResult"]
