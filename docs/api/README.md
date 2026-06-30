# AI Tutor API Documentation Index

Unified OpenAPI 3.1 documentation for all AI Tutor services.

| Service | Spec | Base URL |
|---------|------|----------|
| LLM Gateway | [llm-gateway.openapi.json](./llm-gateway.openapi.json) | `/api/v1/llm` |
| Embedding Service | [embedding-service.openapi.json](./embedding-service.openapi.json) | `/api/v1/embeddings` |
| RAG Pipeline | [rag-pipeline.openapi.json](./rag-pipeline.openapi.json) | `/api/internal/rag` |
| Content Ingestion | [content-ingestion.openapi.json](./content-ingestion.openapi.json) | `/api/v1/content` |
| Chat Orchestrator | [chat-orchestrator.openapi.json](./chat-orchestrator.openapi.json) | `/api/v1/chat` |
| Agent Reasoning | [agent-reasoning.openapi.json](./agent-reasoning.openapi.json) | `/api/internal/agent` |
| Confidence Grader | [confidence-grader.openapi.json](./confidence-grader.openapi.json) | `/api/internal/grader` |
| Learner Profile | [learner-profile.openapi.json](./learner-profile.openapi.json) | `/api/v1/learner` |
| Admin Config | [admin-config.openapi.json](./admin-config.openapi.json) | `/api/v1/admin/config` |
| Assessment | [assessment.openapi.json](./assessment.openapi.json) | `/api/v1/assessments` |
| Content Management | [content-management.openapi.json](./content-management.openapi.json) | `/api/v1/content-mgmt` |
| Analytics | [analytics.openapi.json](./analytics.openapi.json) | `/api/v1/analytics` |
| Semantic Cache | [cache.openapi.json](./cache.openapi.json) | `/api/internal/cache` |

Generate updated specs from running services:

```bash
curl http://localhost:8001/openapi.json > docs/api/llm-gateway.openapi.json
```
