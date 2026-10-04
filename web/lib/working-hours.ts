import type { ResourceHours } from "./management-api";

export interface WorkingHourDraft {
  weekday: number;
  open: string;
  close: string;
}
const minuteTime = (minutes: number) =>
  `${Math.floor(minutes / 60)
    .toString()
    .padStart(2, "0")}:${(minutes % 60).toString().padStart(2, "0")}`;
export function workingHoursDraft(hours: ResourceHours[]): WorkingHourDraft[] {
  return hours.map((hour) => ({
    weekday: hour.weekday,
    open: minuteTime(hour.opens_minute),
    close: minuteTime(hour.closes_minute),
  }));
}
export function workingHoursPayload(drafts: WorkingHourDraft[]) {
  if (drafts.length > 50) throw new Error("Use at most 50 weekly intervals.");
  const minute = (text: string, closing: boolean) => {
    if (closing && text === "24:00") return 1440;
    if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(text))
      throw new Error(
        "Enter both opening and closing times for every interval.",
      );
    const [hours, minutes] = text.split(":").map(Number);
    return hours! * 60 + minutes!;
  };
  const hours = drafts
    .map((draft) => {
      if (
        !Number.isInteger(draft.weekday) ||
        draft.weekday < 1 ||
        draft.weekday > 7
      )
        throw new Error("Invalid weekday.");
      const opens_minute = minute(draft.open, false),
        closes_minute = minute(draft.close, true);
      if (closes_minute <= opens_minute)
        throw new Error(
          "Closing time must be after opening time. Split overnight hours between days.",
        );
      return { weekday: draft.weekday, opens_minute, closes_minute };
    })
    .sort((a, b) => a.weekday - b.weekday || a.opens_minute - b.opens_minute);
  hours.forEach((hour, index) => {
    const previous = hours[index - 1];
    if (
      previous?.weekday === hour.weekday &&
      previous.closes_minute > hour.opens_minute
    )
      throw new Error("Intervals on the same day cannot overlap.");
  });
  return hours;
}
