# Service Restart Runbook

## Symptoms
Service unhealthy, `/health` returns non-200, elevated error rates.

## Steps
1. Check pod/container status: `kubectl get pods -l app=<service>`
2. Review logs: `kubectl logs -l app=<service> --tail=200`
3. Restart deployment: `kubectl rollout restart deployment/<service>`
4. Verify `/health` and `/ready` endpoints return 200
5. Monitor metrics for 5 minutes

# Database Failover Runbook

## Steps
1. Confirm primary DB unreachable via health checks
2. Promote read replica: `pg_ctl promote -D /var/lib/postgresql/data`
3. Update connection strings in service configs
4. Restart all services connecting to DB
5. Verify Alembic migration version consistency

# Kafka Consumer Lag Runbook

## Steps
1. Check consumer group lag: `kafka-consumer-groups --bootstrap-server $BROKER --describe --group <group>`
2. Scale consumer replicas if lag > 10,000
3. Review dead-letter queue for poison messages
4. Reset offset only after root cause fix

# LLM Provider Failover Runbook

## Steps
1. Check circuit breaker state in LLM Gateway metrics
2. Verify fallback provider credentials
3. Set `LLM_PRIMARY_PROVIDER=azure` env var and restart gateway
4. Monitor token latency and error rate

# Circuit Breaker Reset

```bash
curl -X POST http://llm-gateway:8001/api/v1/admin/circuit-breaker/reset
```

# PII Data Subject Erasure Request

## Steps
1. Locate user by email hash in `users` table
2. Run retention purge with `retention_days=0` for user scope
3. Delete vector DB entries for user's sessions
4. Write audit log entry: `data_subject.erasure`
5. Confirm erasure within 30 days per policy
