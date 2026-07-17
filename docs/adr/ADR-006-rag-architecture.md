# ADR-006: RAG Pipeline for Contextual AI Responses

**Date:** 2026-03-01  
**Status:** Accepted  
**Deciders:** ML Platform Team, Product Team

## Context

The AI tutor must answer questions grounded in specific course content rather than relying solely on the LLM's training data. A pure LLM approach produces hallucinations about course-specific material.

## Decision

Implement a **Retrieval-Augmented Generation (RAG)** pipeline:

1. **Ingestion:** Course content is chunked, embedded via `embedding-service`, and stored in Weaviate with a `CourseChunk` schema.
2. **Retrieval:** `rag-pipeline` service receives a user query, embeds it, and performs cosine similarity search against Weaviate, optionally scoped to a `knowledge_base_id`.
3. **Generation:** Retrieved chunks are passed as context to `llm-gateway`, which constructs a prompt with source attribution.
4. **Fallback:** When Weaviate is unavailable, an in-memory vector store is used. When no RAG chunks are found and the session is not KB-scoped, `chat-orchestrator` fetches web context in parallel and uses it as grounding.

## Consequences

**Positive:**
- Grounded responses reduce hallucination on course-specific content
- Source attribution (document references) enables learner verification
- Knowledge-base scoping allows per-course content isolation

**Negative:**
- RAG quality depends on chunk quality — poor chunking degrades answer quality
- Weaviate in-memory fallback loses all indexed data on restart — persistent volume is the correct configuration for all non-local environments
- Embedding API costs scale with knowledge base size
