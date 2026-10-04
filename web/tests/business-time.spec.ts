import { expect, test } from "@playwright/test";
import {
  businessDateTime,
  businessTimeToInstant,
  shiftDate,
  WEEKDAYS,
} from "../lib/business-time";

test("ISO weekdays and local midnight use the business zone", () => {
  expect(WEEKDAYS[0]).toEqual({ index: 1, label: "Monday" });
  expect(WEEKDAYS[6]).toEqual({ index: 7, label: "Sunday" });
  expect(businessDateTime("2026-10-04T02:00:00Z", "America/New_York")).toEqual({
    date: "2026-10-03",
    time: "22:00",
  });
  expect(shiftDate("2026-03-08", 1)).toBe("2026-03-09");
});

test("entered time preserves non-hour offsets and round trips", () => {
  expect(businessTimeToInstant("2026-10-04", "09:30", "America/New_York")).toBe(
    "2026-10-04T13:30:00.000Z",
  );
  expect(
    businessTimeToInstant("2026-10-04", "09:30", "America/Los_Angeles"),
  ).toBe("2026-10-04T16:30:00.000Z");
  expect(businessTimeToInstant("2026-10-04", "09:30", "Asia/Kathmandu")).toBe(
    "2026-10-04T03:45:00.000Z",
  );
});

test("DST gaps and folds cannot silently create a shifted appointment", () => {
  expect(() =>
    businessTimeToInstant("2026-03-08", "02:30", "America/New_York"),
  ).toThrow(/does not exist/);
  expect(() =>
    businessTimeToInstant("2026-11-01", "01:30", "America/New_York"),
  ).toThrow(/occurs twice/);
  expect(businessTimeToInstant("2026-03-08", "03:30", "America/New_York")).toBe(
    "2026-03-08T07:30:00.000Z",
  );
});

test("invalid dates, times and unconfigured zones fail before saving", () => {
  for (const [date, time] of [
    ["2026-02-30", "09:00"],
    ["2026-10-04", "24:00"],
    ["", "09:00"],
  ])
    expect(() => businessTimeToInstant(date!, time!, "UTC")).toThrow();
  expect(() => businessTimeToInstant("2026-10-04", "09:00", "")).toThrow(
    /Configure/,
  );
});
