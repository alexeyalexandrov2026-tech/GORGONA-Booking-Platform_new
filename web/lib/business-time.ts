/** ISO weekdays match Python isoweekday() and the persisted 1..7 contract. */
export const WEEKDAYS = [
  { index: 1, label: "Monday" },
  { index: 2, label: "Tuesday" },
  { index: 3, label: "Wednesday" },
  { index: 4, label: "Thursday" },
  { index: 5, label: "Friday" },
  { index: 6, label: "Saturday" },
  { index: 7, label: "Sunday" },
] as const;

export function businessDateTime(instant: Date | string, timezone: string) {
  if (!timezone) throw new Error("Configure the location timezone first.");
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: timezone,
    calendar: "gregory",
    numberingSystem: "latn",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(new Date(instant));
  const part = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((entry) => entry.type === type)?.value ?? "";
  return {
    date: `${part("year")}-${part("month")}-${part("day")}`,
    time: `${part("hour")}:${part("minute")}`,
  };
}

/** Calendar arithmetic, independent of the browser's local timezone and DST. */
export function shiftDate(date: string, days: number): string {
  const value = new Date(`${date}T12:00:00Z`);
  value.setUTCDate(value.getUTCDate() + days);
  return value.toISOString().slice(0, 10);
}

/** Resolve a wall-clock minute only if it identifies exactly one instant.
 * The server still validates availability. Gaps and folds never silently shift a booking.
 */
export function businessTimeToInstant(
  date: string,
  time: string,
  timezone: string,
): string {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || !/^\d{2}:\d{2}$/.test(time))
    throw new Error("Enter a valid date and time.");
  const wall = Date.parse(`${date}T${time}:00Z`);
  if (
    !Number.isFinite(wall) ||
    new Date(wall).toISOString().slice(0, 16) !== `${date}T${time}`
  )
    throw new Error("Enter a valid date and time.");
  // Sample both sides of a modern offset transition, including non-hour offsets.
  const offsets = new Set<number>();
  for (const hours of [-48, -24, 0, 24, 48]) {
    const sample = wall + hours * 3_600_000;
    const local = businessDateTime(new Date(sample), timezone);
    offsets.add(Date.parse(`${local.date}T${local.time}:00Z`) - sample);
  }
  const matches = [...offsets]
    .map((offset) => wall - offset)
    .filter((candidate) => {
      const local = businessDateTime(new Date(candidate), timezone);
      return local.date === date && local.time === time;
    });
  if (matches.length === 0)
    throw new Error(
      "This local time does not exist because the clocks change. Choose another time.",
    );
  if (matches.length !== 1)
    throw new Error(
      "This local time occurs twice because the clocks change. Choose an unambiguous time.",
    );
  return new Date(matches[0]!).toISOString();
}
