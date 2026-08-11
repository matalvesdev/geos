# SPEC-004 — Event Bus

- **State**: IMPLEMENTED + TESTED (2026-08-11) · **Status**: ACCEPTED
- **Layer**: Phase 0 Foundation · ADR-0003

## Context / Problem
Domains must communicate through events (publish/subscribe) with an audit trail, without external
brokers.

## Goals
- `EventBus` with `publish`, `subscribe`, `unsubscribe`, `dispatch`.
- Every published event persisted to `events` (type, payload, trace_id) unless opted out.
- Subscribers are deterministic callables; exceptions are captured, never crash the bus.
- Adapter protocol so production brokers can replace the in-process transport (ADR-0003).

## Non-goals
- At-least-once delivery across processes; ordering guarantees beyond insertion order; retries
  (delegated to Job System, SPEC-005).

## Requirements
R4.1 `publish(type, payload, trace_id=None)` → returns `Event` with id; persisted by default.
R4.2 `subscribe(type, handler)`, `unsubscribe(type, handler)`; wildcard `*` supported.
R4.3 `dispatch` synchronous; handler errors logged via telemetry, bus continues.
R4.4 `EventBus` protocol: `publish/subscribe/unsubscribe/dispatch` (adapter path).
R4.5 Named business events (spec §49) documented in `geos/core/events.py` constants.

## Interfaces
```
bus = EventBus(db)
bus.publish("lead.created", {"lead_id": ...}, trace_id=t)
bus.subscribe("lead.created", handler)
```

## Security
Payloads validated as JSON-serializable; no secrets in payloads.

## Failure modes
Handler raising → recorded, not propagated. DB write failure → event still dispatched in-memory,
warning logged.

## Tests / Acceptance
`test_events.py`: subscribe→publish→handler called; persisted row; unsubscribe stops delivery;
handler exception doesn't break subsequent handlers; wildcard subscription.
