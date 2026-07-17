# Runbook: Chat Responses Degraded

**Symptoms:** Chat responses are slow, returning demo/fallback answers, or stream stops mid-response.

## Diagnosis

```bash
# 1. Check chat-orchestrator health
curl http://localhost:8003/health

# 2. Check recent logs for errors
make logs-chat-orchestrator | tail -50

# 3. Check LLM gateway health
curl http://localhost:8004/health

# 4. Check if demo mode is active (look for DEMO_MODE env var)
kubectl get deployment chat-orchestrator -o jsonpath='{.spec.template.spec.containers[0].env}' | jq .
```

## Common Causes and Fixes

### 1. LLM Gateway down or rate-limited
- Check `make logs-llm-gateway`
- Verify `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` are set correctly
- Check API provider status pages

### 2. RAG pipeline returning no context (falls back to demo)
- See [rag-empty-results runbook](./rag-empty-results.md)

### 3. Chat session cache miss (Redis down)
- `make logs-redis`
- Sessions will re-load from PostgreSQL on cache miss — degraded but functional

### 4. Streaming disconnect
- Check client-side SSE timeout settings
- Verify `ANTHROPIC_API_KEY` has streaming permissions
