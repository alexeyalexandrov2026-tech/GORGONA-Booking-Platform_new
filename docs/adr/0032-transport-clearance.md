# ADR-0032: Clearance is never positive on stale or unknown data

Status: accepted for package M slice M5 (2026-10-24), under the owner's word for package M (2026-10-23):
«Да, добавь модуль «Транспорт и логистика» в реестр модулей как невключаемый до приёмки и начинай пакет M с первого
среза. Готовность BEAUTY-01 и main пока не трогай.» and 2026-10-24: «Делай как считаешь нужным я доверяю тебе».
Builds on ADR-0028..0031; package M's plan, decisions 7 and 10.

## Context

TMS-03: "stale telematics and unknown hours-of-service never give a positive clearance". Hours-of-service
rules differ by country and change over time, so they must be data, not code. No real ELD or telematics
provider is connected in package M; facts arrive through the API from FAKE sources in tests.

## Decision

1. **Versioned rule profiles.** A business keeps one current hours-of-service profile, replaced whole with its
   expected revision and kept as insert-only versions: a code, the maximum driving minutes and on-duty window
   minutes since the last reset, the reset (consecutive off-duty or sleeper minutes), the cycle (minutes over a
   number of days) and the maximum age of data. The US property-carrier 11/14/10 and 70-hour/8-day rules are one
   such profile, not code.
2. **Duty records and telematics pings are insert-only facts** with a source and the source's record id
   (unique per business): a driver's duty status (`off_duty`, `sleeper`, `driving`, `on_duty`) over an
   interval, and a vehicle's last observation time. A repeat with the same content changes nothing; other
   content is `TRANSPORT_FACT_CONFLICT`; a driver's records never overlap.
3. **Clearance is computed, never stored or assumed.** For a trip at a moment: each assigned driver, truck and
   trailer is `cleared`, `not_cleared` (a limit is exceeded) or `unknown` (no profile, no data, stale data,
   a gap in the driver's records over the cycle, no telematics, stale telematics). The trip is `cleared` only if
   a driver and a truck are assigned and every role is `cleared`; any `not_cleared` makes it `not_cleared`;
   otherwise it is `unknown`. Reasons are listed per role.
4. **Freshness** is measured against the requested moment: the driver's records must reach within the profile's
   maximum data age of it and cover the cycle without gaps; a vehicle's last ping must be within the same age.
5. **Scope and gates** as before; recording facts needs `transport.events` (delegable); profiles need
   `transport.manage` (never delegable); reading clearance needs `transport.read`.

## Consequences

Per-driver rule sets, exemptions, split sleeper berth and real ELD connectors come later; the same facts and the
same never-positive rule carry them. Dispatching a trip (M6 screens) will show the clearance before departure.
