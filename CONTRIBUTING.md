# Contributing to Ai-Tutor-Agent

Welcome! This guide explains how to get from `git clone` to a running local
environment and how to contribute code that aligns with the project's
architecture.

---

## Prerequisites

| Tool | Version |
|---|---|
| Python | 3.11+ |
| Docker + Docker Compose | 24+ |
| Node.js | 20+ (frontend only) |
| Make | any |

---

## Local Setup (Full Stack)

```bash
# 1. Clone and enter repo
git clone https://github.com/gayathri-opsera/Ai-Tutor-Agent.git
cd Ai-Tutor-Agent

# 2. Copy env file and fill in secrets
cp .env.example .env          # set KEYCLOAK_*, OPENAI_API_KEY, etc.

# 3. Start infrastructure (Postgres, Kafka, MinIO, Weaviate, Keycloak)
docker compose up -d

# 4. Start all services
make dev                      # or: docker compose -f docker-compose.yml up

# 5. Seed initial knowledge bases
python scripts/seed_vectors.py --domain python-basics
```

Access the frontend at `http://localhost:3000`.

---

## Service-Only Setup (skip infra)

```bash
# Use KAFKA_SYNC_MODE=true to bypass broker
KAFKA_SYNC_MODE=true DATABASE_URL=postgresql://... uvicorn main:app --reload
```

---

## Project Structure

```
Ai-Tutor-Agent/
├── services/          # Independent FastAPI microservices
│   ├── chat-orchestrator/
│   ├── rag-pipeline/
│   ├── llm-gateway/
│   └── ...
├── libs/              # Shared libraries (copied into containers via Dockerfile)
│   ├── auth/          # JWT + ServiceAuthMiddleware
│   ├── kafka/         # Producer, consumer, schema registry
│   ├── model/         # LLM provider abstraction
│   └── ...
├── frontend/          # React + TypeScript + Vite
├── docs/adr/          # Architecture Decision Records
├── docs/runbooks/     # Operational runbooks
└── Dockerfile.service # Shared base image for all services
```

### When to add to `libs/` vs `services/`

- **`libs/`** — code used by 2+ services (auth, Kafka helpers, model providers)
- **`services/`** — code specific to one service's domain logic

---

## Kafka Communication vs HTTP APIs

This project uses **both** Kafka and HTTP. The rule is:

| Pattern | When to use |
|---|---|
| **HTTP (FastAPI)** | Synchronous request/response; user-facing or inter-service calls that need an immediate reply |
| **Kafka** | Async, fire-and-forget events; decoupled workflows (ingestion, analytics, audit) |

### Kafka Topic Topology

| Topic | Producer | Consumer(s) | Schema |
|---|---|---|---|
| `content-ingestion-events` | content-ingestion | rag-pipeline | `ContentIngestionEvent` |
| `content-update-events` | content-management | rag-pipeline | `ContentUpdateEvent` |
| `llm-usage-events` | llm-gateway | analytics | `LLMUsageEvent` |
| `cache-metrics` | chat-orchestrator | analytics | `CacheMetricsEvent` |
| `audit-events` | all services | audit | `AuditEvent` |
| `analytics-events` | all services | analytics | `AnalyticsEvent` |
| `admin-config-changes` | admin-config | all services | `AdminConfigChangeEvent` |
| `user-approval-events` | auth-service | admin-config | `UserApprovalRequestedEvent` |
| `course-approval-events` | content-management | admin-config | `CourseApprovalRequestedEvent` |

All schemas are defined in `libs/kafka/src/schemas/events.py` and registered in
`libs/kafka/src/schema_registry.py`. Every producer validates before emitting;
every consumer validates after receiving.

---

## Adding a New Service

1. Copy an existing service directory as a template
2. Update `Dockerfile.service` `ARG SERVICE=` default if needed
3. Add `ServiceAuthMiddleware` from `libs/auth` — all internal services require it
4. Register any new Kafka topics in `libs/kafka/src/topics.py` and add schemas to
   `libs/kafka/src/schemas/events.py` + `schema_registry.py`
5. Write an ADR in `docs/adr/` if the new service introduces a significant
   architectural choice

---

## Adding a New Knowledge Domain

Use `seed_vectors.py` — the canonical entry point for bootstrapping AI content:

```bash
python scripts/seed_vectors.py --domain <domain-name>
```

The structured JSON contract format means you only need to provide the content
file; the embedding mechanics are handled automatically.

---

## Commit Convention

This project follows [Conventional Commits](https://www.conventionalcommits.org/):

```
feat(service-name): add X
fix(lib-name): resolve Y
docs: update contributing guide
chore: bump dependency versions
```

Add `[skip ci]` to commit messages that only change docs or configuration.

---

## Running Tests

```bash
# All libs
cd libs/kafka && python -m pytest tests/
cd libs/auth  && python -m pytest tests/

# A specific service
cd services/rag-pipeline && DATABASE_URL=postgresql://test:test@localhost/test python -m pytest tests/unit/
```

---

## Architecture Decision Records

Significant decisions are documented in `docs/adr/`. Read these before
making changes to: Kafka event bus, Weaviate vector store, Keycloak auth,
the RAG architecture, or inter-service trust boundaries.
