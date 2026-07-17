"""Shared inter-service contract models.

Re-exports all public models from domain-specific modules so callers can use
a single import path::

    from libs.contracts.src import RetrieveRequest, RetrieveResponse
    from libs.contracts.src import EmbedRequest, CompletionRequest
    from libs.contracts.src import EvaluateRequest, ReasonRequest
    from libs.contracts.src import ApprovalRequest, ApprovalResponse
"""
from src.agent import ReasonRequest, ReasonResponse, ReasonStep
from src.approval import ApprovalRequest, ApprovalResponse, ApprovalStatus
from src.embedding import EmbedRequest, EmbedResponse
from src.grader import ChunkGrade, EvaluateRequest, EvaluateResponse
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
    # Grader
    "EvaluateRequest",
    "ChunkGrade",
    "EvaluateResponse",
    # Agent
    "ReasonRequest",
    "ReasonStep",
    "ReasonResponse",
    # Approval
    "ApprovalStatus",
    "ApprovalRequest",
    "ApprovalResponse",
]
