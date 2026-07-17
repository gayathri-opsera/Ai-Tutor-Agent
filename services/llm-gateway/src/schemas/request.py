"""Provider-agnostic LLM request schema (ADR-001).

Models migrated to libs/contracts/src/llm.py (WO-014).
Re-exported here for backward compatibility.
"""
from __future__ import annotations

# noqa: F401 — re-export for backward compatibility
from llm import (
    CompletionRequest,
    Message,
    MessageRole,
    ModelTier,
)

__all__ = ["ModelTier", "MessageRole", "Message", "CompletionRequest"]
