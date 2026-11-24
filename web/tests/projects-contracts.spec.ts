import { expect, test } from "@playwright/test";
import {
  canBillProjects,
  canManageProjects,
  canReadProjects,
  formatMinor,
  parseMajorToMinor,
  projectsResponseSchema,
} from "../lib/projects-contracts";

test("projects role helpers gate non-delegated roles and company-wide billing", () => {
  expect(
    canReadProjects({
      salon_id: "01900000-0000-7000-8000-000000000001",
      salon_slug: "firm",
      salon_name: "Firm",
      role: "artist",
      location_id: "01900000-0000-7000-8000-000000000002",
      delegated: false,
    }),
  ).toBe(true);
  expect(
    canManageProjects({
      salon_id: "01900000-0000-7000-8000-000000000001",
      salon_slug: "firm",
      salon_name: "Firm",
      role: "artist",
      location_id: null,
      delegated: false,
    }),
  ).toBe(false);
  expect(
    canBillProjects({
      salon_id: "01900000-0000-7000-8000-000000000001",
      salon_slug: "firm",
      salon_name: "Firm",
      role: "manager",
      location_id: "01900000-0000-7000-8000-000000000002",
      delegated: false,
    }),
  ).toBe(false);
  expect(
    canBillProjects({
      salon_id: "01900000-0000-7000-8000-000000000001",
      salon_slug: "firm",
      salon_name: "Firm",
      role: "owner",
      location_id: null,
      delegated: false,
    }),
  ).toBe(true);
  expect(
    canReadProjects({
      salon_id: "01900000-0000-7000-8000-000000000001",
      salon_slug: "firm",
      salon_name: "Firm",
      role: "owner",
      location_id: null,
      delegated: true,
    }),
  ).toBe(false);
});

test("projectsResponseSchema routes every projects endpoint cleanly", () => {
  const uid = "01900000-0000-7000-8000-000000000010";
  expect(projectsResponseSchema("/projects/matters", "GET")).not.toBeNull();
  expect(
    projectsResponseSchema(`/projects/matters/${uid}`, "PUT"),
  ).not.toBeNull();
  expect(
    projectsResponseSchema("/projects/search?q=helios", "GET"),
  ).not.toBeNull();
  expect(
    projectsResponseSchema(`/projects/matters/${uid}/stages`, "GET"),
  ).not.toBeNull();
  expect(
    projectsResponseSchema(`/projects/matters/${uid}/tasks`, "GET"),
  ).not.toBeNull();
  expect(
    projectsResponseSchema(`/projects/matters/${uid}/files`, "GET"),
  ).not.toBeNull();
  expect(
    projectsResponseSchema(`/projects/matters/${uid}/time-entries`, "GET"),
  ).not.toBeNull();
  expect(
    projectsResponseSchema(`/projects/matters/${uid}/invoices`, "POST"),
  ).not.toBeNull();
  expect(projectsResponseSchema("/projects/exports", "POST")).not.toBeNull();
  expect(projectsResponseSchema("/other/route", "GET")).toBeNull();
});

test("money helpers format and parse minor units strictly", () => {
  expect(formatMinor(365000, "USD")).toBe("3650.00 USD");
  expect(parseMajorToMinor("1200.50")).toBe(120050);
  expect(parseMajorToMinor("-5")).toBeNull();
});
