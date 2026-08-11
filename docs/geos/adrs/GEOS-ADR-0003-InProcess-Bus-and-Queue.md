# GEOS-ADR-0003 — In-Process Event Bus and Job Queue with Adapter Path

- **Status**: Accepted
- **Date**: 2026-08-11
- **Context**: The master spec (§48–§52) requires an event bus and job system, while the
  installation model demands zero mandatory infrastructure. Brownfield Rule Zero says never create a
  parallel production queue when a compatible one exists.
- **Decision**:
  1. Bootstrap implements an **in-process EventBus** (sync dispatch + optional persisted event
     log in SQLite) and an **in-process JobQueue/Worker** with statuses, retry, timeout and
     dead-letter handling (SPEC-004/005).
  2. `EventBus` and `JobQueue` are defined behind protocols; production deployments may supply
     adapter implementations (Kafka/RabbitMQ/Redis/Celery/NATS…) without touching domains.
  3. The Workflow Engine is **infrastructure-agnostic**: it schedules through the same
     `JobQueue`/`Scheduler` interfaces.
- **Alternatives**: external broker from day one (rejected: violates local-first); no bus at all
  (rejected: spec requires decoupling).
- **Consequences**: (+): works everywhere, trivially testable. (−): in-process dispatch has no
  cross-process durability; the persisted event log provides auditability, and adapters close the
  gap later.
