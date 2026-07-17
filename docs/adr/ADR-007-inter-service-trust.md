# ADR-007: Inter-Service Trust Handshake

**Date:** 2026-07-17  
**Status:** Accepted  
**Deciders:** Security Team, Platform Team

## Context

The platform comprises 14 microservices making HTTP calls to each other (chat-orchestrator → rag-pipeline → llm-gateway, etc.). Without an explicit trust handshake, each service implicitly trusts any caller on the internal network — a lateral movement risk if any service is compromised.

Three options were considered:
1. **Network-only trust** — trust internal network, no auth on service-to-service calls (current state, identified as a risk)
2. **mTLS** — mutual TLS between every service pair (high operational overhead; requires cert rotation)
3. **JWT propagation** — forward the caller's Bearer token downstream; use a `SERVICE_INTERNAL_TOKEN` for background/scheduled calls

## Decision

Adopt **JWT propagation** as the explicit inter-service trust handshake:

- `libs/auth/src/service_client.py` provides `service_client(request)` — an httpx `AsyncClient` that automatically adds `Authorization: Bearer <token>` to every outbound request.
- User-facing requests forward the caller's JWT so downstream services can enforce the same RBAC rules.
- Background tasks (purge jobs, Kafka consumers, CronJobs) use a `SERVICE_INTERNAL_TOKEN` env var — a long-lived service account token issued by Keycloak.
- An `X-Service-Name` header identifies the calling service for audit trail purposes.

## Consequences

**Positive:**
- Downstream services can validate the JWT and enforce role-based access control
- Audit logs capture the originating actor, not just the internal service
- `SERVICE_INTERNAL_TOKEN` provides a clear escalation path to mTLS in future
- Single implementation in `libs/auth` ensures consistent propagation across all services

**Negative:**
- Token expiry during long-running streaming responses could cause mid-stream 401s — mitigated by using service tokens for streaming paths
- Services must install `libs/auth` as a dependency, adding a coupling point

## Migration

Set `SERVICE_INTERNAL_TOKEN` in Kubernetes Secrets / SealedSecrets for all services.
Deploy `libs/auth` updates — `service_client` is backward-compatible (falls back to no-auth when token is absent).
