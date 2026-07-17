# AI Tutor Agent

A virtual AI tutoring platform that delivers training using custom content, falls back to external sources when needed, and interactively answers learner queries in real time.

## Architecture

```
                    ┌─────────────────────────────┐
                    │       Nginx (port 80)        │  ← API Gateway + Rate Limiting
                    └──────────────┬──────────────┘
                                   │
          ┌────────────────────────┼────────────────────────┐
          │                        │                        │
   ┌──────▼──────┐        ┌────────▼───────┐      ┌────────▼────────┐
   │  Frontend   │        │ Chat           │      │  Content        │
   │  React/Vite │        │ Orchestrator   │      │  Ingestion      │
   │  :3000      │        │ :8004          │      │  :8003          │
   └─────────────┘        └────────┬───────┘      └────────┬────────┘
                                   │                        │
          ┌────────────────────────┼──────────────────┐     │
          │                        │                  │     │
   ┌──────▼──────┐        ┌────────▼────────┐  ┌─────▼─────▼──────┐
   │ LLM Gateway │        │  RAG Pipeline   │  │ Embedding Service │
   │ :8000       │        │  :8002          │  │ :8001             │
   └──────┬──────┘        └────────┬────────┘  └──────────────────┘
          │                        │
   ┌──────▼──────────────────────── ▼──────────────────────────────┐
   │              Infrastructure                                    │
   │  PostgreSQL:5432  Redis:6379  Weaviate:8080  MinIO:9000       │
   └───────────────────────────────────────────────────────────────┘
```

## Services

| Service | Port | Description |
|---|---|---|
| Nginx (API Gateway) | **80** | Rate limiting, routing, CORS |
| LLM Gateway | 8000 | Provider-agnostic LLM calls (OpenAI/Azure/Ollama) |
| Embedding Service | 8001 | Text → vector embedding |
| RAG Pipeline | 8002 | Retrieval-augmented generation |
| Content Ingestion | 8003 | Upload & chunk PDFs, DOCX, video |
| Chat Orchestrator | 8004 | Session management, SSE streaming |
| Agent Reasoning | 8005 | ReAct loop for complex queries |
| Confidence Grader | 8006 | Corrective RAG, hallucination mitigation |
| Content Management | 8007 | Knowledge base CRUD |
| Learner Profile | 8008 | Progress tracking |
| Admin Config | 8009 | Organization-level settings |
| Assessment | 8010 | Pre/post training evaluation |
| Analytics | 8011 | Usage analytics |
| Audit | 8012 | Compliance audit logging |
| Frontend | 3000 | React 18 + TypeScript chat UI |

## Quick Start

### Prerequisites
- Docker Desktop (4.x+)
- `make`
- An OpenAI API key (or set `EMBEDDING_BACKEND=mock` and `DEFAULT_PROVIDER=ollama` for fully local)

### 1. Configure environment

```bash
cp .env.local .env
# Edit .env and set your OPENAI_API_KEY
```

### 2. Start everything

```bash
make up
```

This starts:
- PostgreSQL, Redis, Weaviate, MinIO
- All 13 backend services
- Nginx API gateway on port 80
- React frontend on port 3000

> **Note:** Kafka runs in `KAFKA_SYNC_MODE=true` by default — no broker needed.
> Events are dispatched in-process via `LocalEventBus`.

### 3. Open the app

```
http://localhost
```

### 4. Check health

```bash
make health
```

## Running Without OpenAI

Set these in `.env`:

```bash
EMBEDDING_BACKEND=mock       # deterministic mock vectors
DEFAULT_PROVIDER=ollama      # local Ollama (start separately)
KAFKA_SYNC_MODE=true         # no Kafka broker needed
AUTH_DISABLED=true           # skip JWT validation locally
```

Then start Ollama separately:
```bash
ollama serve                  # http://localhost:11434
ollama pull llama3.2
```

## With Real Kafka

```bash
make up-kafka   # starts Zookeeper + Kafka alongside all services
```

## Development Commands

```bash
make logs                      # follow all logs
make logs-llm-gateway          # follow one service
make restart-chat-orchestrator # hot-restart one service
make shell-llm-gateway         # open shell in container
make test                      # run all unit tests locally
make health                    # check all service health endpoints
make down                      # stop everything
make down-volumes              # stop + wipe all data
```

## API Docs

Each FastAPI service exposes Swagger UI at `/docs`:

| Service | Swagger |
|---|---|
| LLM Gateway | http://localhost:8000/docs |
| Embedding | http://localhost:8001/docs |
| RAG | http://localhost:8002/docs |
| Chat | http://localhost:8004/docs |

## Environment Variables

See `.env.local` for full reference. Key variables:

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | — | OpenAI API key |
| `KAFKA_SYNC_MODE` | `true` | Use LocalEventBus instead of broker |
| `AUTH_DISABLED` | `true` | Skip JWT validation (dev only) |
| `EMBEDDING_BACKEND` | `openai_gateway` | `openai_gateway` \| `sentence_transformers` \| `mock` |
| `CONFIDENCE_THRESHOLD` | `0.6` | Min score before external search fallback |
| `RAG_TOP_K` | `5` | Chunks retrieved per query |

## Data Classification

All PostgreSQL tables include a `data_classification` column:

| Level | Examples |
|---|---|
| `PUBLIC` | Knowledge base names |
| `INTERNAL` | Documents, configurations |
| `CONFIDENTIAL` | Chat sessions, messages |
| `RESTRICTED` | User PII (encrypted at rest), audit logs |

PII fields (`email`, `full_name`, `notes`) are stored as AES-256 encrypted `bytea` with a separate SHA-256 hash column for lookups.

## Shared Libraries (`libs/`)

All cross-cutting concerns live in `libs/` and are copied into every service container via `Dockerfile.service`.

| Library | Purpose | Key File |
|---|---|---|
| `libs/auth` | JWT validation + inter-service trust | `src/service_middleware.py` |
| `libs/kafka` | Producers, consumers, schema registry | `src/schema_registry.py` |
| `libs/model` | LLM provider abstraction (strategy pattern) | `src/gateway_provider.py` |
| `libs/secrets` | Secrets provider with prod-safety guards | `src/provider.py` |
| `libs/db` | Shared asyncpg pool factory | `src/pool.py` |
| `libs/contracts` | Pydantic contracts shared between services | `src/` |

### Inter-Service Trust (`ServiceAuthMiddleware`)

Every internal-facing service applies `ServiceAuthMiddleware` from `libs/auth`.  
Requests must carry either:
- `Authorization: Bearer <user-jwt>` — for user-initiated requests
- `X-Service-Token: <token>` + `X-Service-Name: <name>` — for service-to-service calls (value from `SERVICE_INTERNAL_TOKEN` env var)

### Kafka Schema Registry (`libs/kafka/src/schema_registry.py`)

`schema_registry.py` maps every topic name to a canonical Pydantic model from `libs/kafka/src/schemas/events.py`.  
Producers validate payloads before signing; consumers validate after signature verification.  
Add a new topic by:
1. Define the event model in `src/schemas/events.py`
2. Add the mapping in `src/schema_registry.py`
3. Reference the `TopicSpec` in `src/topics.py`

### Content Knowledge Domain Seeding (`seed_vectors.py`)

`seed_vectors.py` is the canonical entry point for bootstrapping any knowledge domain.  
It follows a structured JSON contract — one file per domain — meaning any engineer can add a new subject area without knowing the embedding mechanics.  
See `docs/adr/ADR-006-rag-architecture.md` for the full design rationale.

### AI Model Abstraction (`libs/model`)

All LLM calls go through `GatewayModelProvider` (implements `ModelProvider` interface).  
Services never import a concrete provider SDK directly.  
Swap models or add routing by changing `LLM_GATEWAY_URL` — no service code changes needed.  
See `docs/adr/` for the full Architecture Decision Record set.
