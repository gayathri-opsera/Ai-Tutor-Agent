# ADR-004: Keycloak for Identity and Access Management

**Date:** 2026-02-10  
**Status:** Accepted  
**Deciders:** Security Team, Platform Team

## Context

The platform serves three distinct user roles (Learner, Creator, Admin) with different permission boundaries. A bespoke auth implementation would require maintaining JWT signing, token refresh, role management, and MFA support.

## Decision

Use **Keycloak** as the identity provider. The `libs/auth` package provides JWT validation middleware and role-based decorators for FastAPI services. The React frontend uses Keycloak JS adapter with `ProtectedRoute` components.

## Consequences

**Positive:**
- Enterprise-grade identity management with OIDC/OAuth2 support out of the box
- Role-based access control (RBAC) via Keycloak realm roles — no custom role logic in services
- Single source of truth for user identities across all 14 microservices
- Keycloak realm export in `k8s/base/keycloak/` enables reproducible realm configuration

**Negative:**
- Additional 512 MB+ container in local development
- Keycloak upgrade path requires realm export/import testing
- Cold-start latency on the first request after Keycloak restarts
