# ADR-001: Monorepo with Microservice Architecture

**Date:** 2026-01-15  
**Status:** Accepted  
**Deciders:** Platform Team

## Context

The Ai Tutor Agent platform requires independent deployment of AI components (LLM gateway, RAG pipeline, confidence grading, agent reasoning) alongside standard platform concerns (auth, analytics, content management). These components have vastly different scaling profiles and update cadences.

## Decision

Adopt a **monorepo** layout containing independent **microservices**, each with its own `Dockerfile`, `requirements.txt`, K8s manifests, and CI workflow. Shared concerns (auth, caching, Kafka, logging, metrics, vector-db, contracts) live in `libs/` as internal packages.

## Consequences

**Positive:**
- Atomic commits across service and library boundaries
- Single `docker-compose.yml` brings up the full stack for local development
- Consistent service skeleton (main.py, service.py, api/, tests/) reduces cognitive cost of switching services
- Shared `libs/` packages enforce DRY without requiring published packages

**Negative:**
- 14 near-identical CI workflows — addressed by parameterised reusable workflow (planned)
- `git clone` includes all services even for single-service contributors
- Dependency version drift risk across 16+ `requirements.txt` files — mitigated by shared constraints file (planned)
