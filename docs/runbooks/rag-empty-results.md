# Runbook: RAG Pipeline Returning No Chunks

**Symptoms:** Chat responses lack source attribution; confidence scores are low; answers look generic.

## Diagnosis

```bash
# 1. Check RAG pipeline health and vector sync status
curl http://localhost:8006/health
curl http://localhost:8006/api/v1/rag/health

# 2. Check Weaviate connectivity
curl http://localhost:18080/v1/.well-known/ready

# 3. Check how many vectors are indexed
curl "http://localhost:18080/v1/objects?class=CourseChunk&limit=1" \
  -H "Authorization: Bearer local-dev-key"

# 4. Check RAG pipeline logs for bootstrap errors
make logs-rag-pipeline | grep -i "bootstrap\|weaviate\|error"
```

## Common Causes and Fixes

### 1. Weaviate unavailable — using in-memory fallback
- In-memory store is empty after restart
- Fix: ensure `WEAVIATE_URL` points to a running Weaviate with a PersistentVolume
- See [weaviate-down runbook](./weaviate-down.md)

### 2. Knowledge base not indexed
- Content was uploaded but embedding failed
- Check `make logs-embedding-service` for errors
- Re-trigger ingestion: `POST /api/v1/content/reindex/{knowledge_base_id}`

### 3. Query not matching any chunks (relevance threshold too high)
- Check `SIMILARITY_THRESHOLD` env var on rag-pipeline (default: 0.7)
- Lower threshold for broader recall, raise for precision
