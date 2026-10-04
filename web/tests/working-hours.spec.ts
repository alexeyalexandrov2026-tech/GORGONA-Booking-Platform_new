import { expect, test } from "@playwright/test";
import { workingHoursDraft, workingHoursPayload } from "../lib/working-hours";

test("editing preserves split intervals and Sunday including midnight", () => {
  const hours = [
    { id: "a", weekday: 1, opens_minute: 540, closes_minute: 720 },
    { id: "b", weekday: 1, opens_minute: 780, closes_minute: 1020 },
    { id: "c", weekday: 7, opens_minute: 1200, closes_minute: 1440 },
  ];
  expect(workingHoursPayload(workingHoursDraft(hours))).toEqual(
    hours.map(({ weekday, opens_minute, closes_minute }) => ({
      weekday,
      opens_minute,
      closes_minute,
    })),
  );
});
test("new hours have to be entered rather than assumed", () => {
  expect(() =>
    workingHoursPayload([{ weekday: 1, open: "", close: "" }]),
  ).toThrow(/Enter both/);
  expect(() =>
    workingHoursPayload([{ weekday: 0, open: "09:00", close: "18:00" }]),
  ).toThrow(/weekday/);
  expect(() =>
    workingHoursPayload([{ weekday: 1, open: "18:00", close: "09:00" }]),
  ).toThrow(/after/);
  expect(() =>
    workingHoursPayload([
      { weekday: 1, open: "09:00", close: "12:00" },
      { weekday: 1, open: "11:00", close: "13:00" },
    ]),
  ).toThrow(/overlap/);
  expect(workingHoursPayload([])).toEqual([]);
});
