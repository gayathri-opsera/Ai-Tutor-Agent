# Runbook: PostgreSQL Connection Pool Exhausted

**Symptoms:** `asyncpg.exceptions.TooManyConnectionsError` in service logs; HTTP 500 errors from any service that uses PostgreSQL.

## Diagnosis

```bash
# 1. Check current connection count
psql $DATABASE_URL -c "SELECT count(*), state FROM pg_stat_activity GROUP BY state;"

# 2. Identify which services hold the most connections
psql $DATABASE_URL -c "SELECT application_name, count(*) FROM pg_stat_activity GROUP BY application_name ORDER BY count DESC;"

# 3. Check pool settings per service
grep -r "max_size\|DB_POOL_MAX" services/*/src/main.py
```

## Resolution

### Immediate: Kill idle connections
```sql
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE state = 'idle'
  AND state_change < NOW() - INTERVAL '10 minutes';
```

### Tuning pool sizes
Each service reads `DB_POOL_MAX` from the environment (default: 5 for audit, 10 for rag-pipeline).
PostgreSQL default `max_connections` is 100. With 14 services × 5 max connections = 70 connections at peak.

Reduce pool sizes in high-service-count deployments or increase PostgreSQL `max_connections`.

### Long-term: PgBouncer
Add a PgBouncer connection pooler in front of PostgreSQL for production deployments with >20 service instances.
