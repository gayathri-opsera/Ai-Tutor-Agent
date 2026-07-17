"""Shared inter-service contract models.

Re-exports all public models from domain-specific modules so callers can use
a single import path::

    from libs.contracts.src import RetrieveRequest, RetrieveResponse
    # or
    from libs.contracts.src.rag import RetrieveRequest
"""
from src.rag import (
    ChunkResult,
    IngestChunk,
    IngestRequest,
    RetrieveRequest,
    RetrieveResponse,
)

__all__ = [
    "RetrieveRequest",
    "ChunkResult",
    "RetrieveResponse",
    "IngestChunk",
    "IngestRequest",
]
