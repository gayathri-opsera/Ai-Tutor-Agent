# ADR-002: Weaviate as Vector Store

**Date:** 2026-01-20  
**Status:** Accepted  
**Deciders:** ML Platform Team

## Context

The RAG pipeline requires a vector store for semantic similarity search over course content chunks. Candidates considered: Pinecone, Qdrant, pgvector (PostgreSQL extension), Weaviate.

## Decision

Use **Weaviate** as the vector store, deployed as a sidecar container in Docker Compose and as a StatefulSet in Kubernetes with a PersistentVolume for data durability.

## Why Weaviate over alternatives

| Criterion | Pinecone | pgvector | Weaviate |
|-----------|----------|----------|----------|
| Self-hosted | No | Yes | Yes |
| Schema-aware | No | No | **Yes** |
| Hybrid search | No | Partial | **Yes** |
| Auth support | Managed | DB-level | **API key** |
| K8s-native | No | Yes | **Yes** |

Weaviate's schema awareness allows the `CourseChunk` class to carry metadata (course_id, chunk_index, language) as filterable properties alongside the vector, enabling course-scoped RAG retrieval without a separate metadata store.

## Consequences

**Positive:**
- Schema-validated vector classes prevent silent payload drift
- API-key authentication is supported natively (enabled in all non-local environments)
- Persistent volume eliminates full-reload on restart when properly configured

**Negative:**
- Additional container adds ~256 MB RAM overhead
- Weaviate version upgrades require schema migration tooling
- Anonymous access must be explicitly disabled in every environment configuration
