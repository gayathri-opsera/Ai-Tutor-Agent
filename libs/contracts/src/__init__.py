"""Shared inter-service contract models.

Re-exports all public models from domain-specific modules so callers can use
a single import path::

    from libs.contracts.src import RetrieveRequest, RetrieveResponse
    # or
    from libs.contracts.src.rag import RetrieveRequest
    from libs.contracts.src.embedding import EmbedRequest, EmbedResponse
    from libs.contracts.src.llm import CompletionRequest, CompletionResponse
"""
from src.embedding import EmbedRequest, EmbedResponse
from src.llm import (
    CompletionChoice,
    CompletionRequest,
    CompletionResponse,
    Message,
    MessageRole,
    ModelTier,
    StreamChunk,
    UsageStats,
)
from src.rag import (
    ChunkResult,
    IngestChunk,
    IngestRequest,
    RetrieveRequest,
    RetrieveResponse,
)

__all__ = [
    # RAG
    "RetrieveRequest",
    "ChunkResult",
    "RetrieveResponse",
    "IngestChunk",
    "IngestRequest",
    # Embedding
    "EmbedRequest",
    "EmbedResponse",
    # LLM
    "ModelTier",
    "MessageRole",
    "Message",
    "CompletionRequest",
    "UsageStats",
    "CompletionChoice",
    "CompletionResponse",
    "StreamChunk",
]
