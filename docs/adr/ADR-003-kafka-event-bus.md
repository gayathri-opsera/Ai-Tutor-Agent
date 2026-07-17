# ADR-003: Kafka with LocalEventBus Development Fallback

**Date:** 2026-02-01  
**Status:** Accepted  
**Deciders:** Platform Team

## Context

Several platform events (course approval state transitions, analytics events, audit log emissions) benefit from an event-driven architecture. Running a full Kafka broker in local development adds significant setup friction.

## Decision

Use **Kafka** as the production event bus, but introduce a `LocalEventBus` in `libs/kafka/src/local_bus.py` that implements the same interface. Services check `KAFKA_SYNC_MODE=true` to switch to `LocalEventBus` without code changes.

## Consequences

**Positive:**
- `make up` starts the full system without a Kafka broker for development
- Identical event-publishing interface means no test doubles are needed in unit tests
- Gradual migration path: services can move to real Kafka independently

**Negative:**
- `LocalEventBus` is in-process and synchronous — does not replicate Kafka's delivery guarantees
- Risk that local-only tests pass but production Kafka integration is broken — mitigated by integration test suite
