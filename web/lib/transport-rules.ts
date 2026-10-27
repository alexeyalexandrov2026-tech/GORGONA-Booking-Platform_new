import { businessDateTime, businessTimeToInstant } from "./business-time";

// Package M review fixes R-02 and R-04 (docs/plan/PACKAGE_M_REVIEW_FIXES_2026-10-26.md).

type LegQuantities = {
  quantity: number;
  loaded: number;
  delivered: number;
  refused: number;
  damaged: number;
  pickup_stop: number;
};

/** What is still open on a leg: planned, or loaded once the trip has departed its pickup. */
export function legOpen(
  leg: LegQuantities,
  events: { kind: string; stop_position: number }[],
): number {
  const departed = events.some(
    (e) => e.kind === "departed" && e.stop_position === leg.pickup_stop,
  );
  return (
    (departed ? leg.loaded : leg.quantity) -
    leg.delivered -
    leg.refused -
    leg.damaged
  );
}

/** A stop window as the form shows it: start date and time, end date and time, in its zone. */
export function stopWindowFields(start: string, end: string, zone: string) {
  const from = businessDateTime(start, zone);
  const to = businessDateTime(end, zone);
  return { date: from.date, from: from.time, endDate: to.date, to: to.time };
}

function nextDay(date: string): string {
  return new Date(Date.parse(`${date}T00:00:00Z`) + 86_400_000)
    .toISOString()
    .slice(0, 10);
}

/**
 * The window's instants. Without an end date the window ends on its start day, or on the next
 * local day when it would otherwise end before it starts.
 */
export function stopWindowInstants(
  date: string,
  from: string,
  endDate: string,
  to: string,
  zone: string,
): { start: string; end: string } {
  const start = businessTimeToInstant(date, from, zone);
  if (endDate) return { start, end: businessTimeToInstant(endDate, to, zone) };
  const sameDay = businessTimeToInstant(date, to, zone);
  return {
    start,
    end:
      Date.parse(sameDay) > Date.parse(start)
        ? sameDay
        : businessTimeToInstant(nextDay(date), to, zone),
  };
}
