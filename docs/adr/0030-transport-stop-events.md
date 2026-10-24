# ADR-0030: Trip stop events as idempotent facts; partial delivery

Status: accepted for package M slice M3 (2026-10-24), under the owner's word for package M (2026-10-23):
«Да, добавь модуль «Транспорт и логистика» в реестр модулей как невключаемый до приёмки и начинай пакет M с первого
среза. Готовность BEAUTY-01 и main пока не трогай.» Builds on [ADR-0028](0028-transport-planning-model.md) and
[ADR-0029](0029-transport-assignments-occupancy.md).

## Context

TMS-01 needs partial delivery while the history stays; TMS-03 needs that "a repeated event never changes a
delivery twice". Package M's plan (decision 6) makes trip events idempotent facts with a source event id;
partial delivery records the delivered quantity per load and leaves the rest open (M-05, M-06).

## Decision

1. **Events are insert-only facts** of a trip at one of its stops: `arrived`, `departed`, `loaded`, `delivered`,
   `refused`, `damaged`, `exception`. Each carries its source (who reported it: a short code such as
   `dispatcher` or `telematics`) and the source's own event id, the moment it happened (stored in UTC) and an
   optional note. `(source, source_event_id)` is unique in the business.
2. **A repeat changes nothing.** The same source event id with the same content answers the recorded event and
   writes nothing; with different content it is `TRANSPORT_EVENT_CONFLICT` (409), never an overwrite.
3. **Quantities per leg.** `loaded` names legs whose pickup is this stop; `delivered`, `refused` and `damaged`
   name legs whose delivery is this stop; each with a whole quantity. For every leg, loaded never exceeds the
   planned quantity, and delivered plus refused plus damaged never exceed what was loaded
   (`TRANSPORT_QUANTITY_EXCEEDED`, 409). Whatever is loaded and not yet resolved stays open. Other kinds carry
   no quantities. The trip row is locked first; a deferred check repeats the rule at commit.
4. **The first event starts the trip.** Its status moves from `planned` to `in_transit` (only that move, only
   with an event). Once started, its plan (stops and legs) is frozen (`TRANSPORT_TRIP_STARTED`); drivers,
   trucks and trailers can still be replaced (TMS-01: replacement in transit keeps its history).
5. **Scope and gates** as in ADR-0028/0029: RLS by company, events and their quantities scoped by their trip's
   branch, inserts need the enabled transport module, the runtime role may only select and insert.

## Consequences

Closing a trip, proof of delivery documents and invoices (M7) build on these facts; dispatcher grants (M4)
decide who may record them; telematics freshness (M5) reads the same source codes.
