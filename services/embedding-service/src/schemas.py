"""Request/response schemas for the Embedding Service.

Models migrated to libs/contracts/src/embedding.py (WO-014).
Re-exported here for backward compatibility.
"""
from __future__ import annotations

# noqa: F401 — re-export for backward compatibility
from embedding import EmbedRequest, EmbedResponse

__all__ = ["EmbedRequest", "EmbedResponse"]
