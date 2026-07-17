# ADR-005: Shared Internal Libraries in libs/

**Date:** 2026-02-15  
**Status:** Accepted  
**Deciders:** Platform Team

## Context

14 microservices share common concerns: JWT validation, Redis caching, Kafka publishing, structured logging, health checks, vector DB access, and inter-service contract models. Duplicating these in each service creates maintenance debt and drift.

## Decision

Maintain shared internal packages under `libs/`. Each package (`auth`, `cache`, `contracts`, `kafka`, `logging`, `metrics`, `secrets`, `vector-db`) has its own `requirements.txt`, `pytest.ini`, `src/`, and `tests/` directories. Services install them via `COPY libs/ /app/libs/` in their `Dockerfile`.

## Package Responsibilities

| Package | Responsibility |
|---------|---------------|
| `libs/auth` | JWT validation, role-based middleware, Keycloak config |
| `libs/cache` | Redis client, semantic LLM response cache |
| `libs/contracts` | Shared Pydantic models for inter-service HTTP payloads |
| `libs/kafka` | Kafka producer/consumer, LocalEventBus fallback |
| `libs/logging` | Structured JSON logging configuration |
| `libs/metrics` | Health check patterns, Prometheus metric helpers |
| `libs/secrets` | Centralised secret loading with production-safety guards |
| `libs/vector-db` | Weaviate client abstraction with in-memory fallback |

## Consequences

**Positive:**
- Single fix propagates to all services
- Contract models enforce type-safe inter-service boundaries
- `libs/secrets` centralises all credential loading, eliminating hardcoded fallbacks

**Negative:**
- Changes to `libs/` require rebuilding dependent service containers
- No semantic versioning — breaking changes in libs affect all consumers simultaneously
