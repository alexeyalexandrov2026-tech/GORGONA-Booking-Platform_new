import { expect, test } from "@playwright/test";
import { buildPayrollRunCsv, escapeCsvCell } from "../lib/csv-export";
import type { PayrollRun } from "../lib/global-finance-api";

test("escapeCsvCell neutralizes spreadsheet formula injection and quotes RFC-4180 delimiters", () => {
  expect(escapeCsvCell("=SUM(A1:A2)")).toBe("'=SUM(A1:A2)");
  expect(escapeCsvCell("+1234")).toBe("'+1234");
  expect(escapeCsvCell("-evil")).toBe("'-evil");
  expect(escapeCsvCell("@cmd")).toBe("'@cmd");
  expect(escapeCsvCell('Doe, "Jane"')).toBe('"Doe, ""Jane"""');
  expect(escapeCsvCell(42.5)).toBe("42.5");
});

test("buildPayrollRunCsv outputs Gusto/ADP-ready RFC-4180 CSV with exact USD totals", () => {
  const run: PayrollRun = {
    id: "run-1",
    run_number: "PR-2026-48",
    period_start: "2026-11-23",
    period_end: "2026-11-27",
    pay_date: "2026-11-28",
    status: "approved",
    total_gross_cents: 221000,
    total_employee_taxes_cents: 48200,
    total_employer_taxes_cents: 21000,
    total_deductions_cents: 24500,
    total_net_cents: 148300,
    export_provider: "csv_adp_gusto",
    approved_at: "2026-11-28T06:00:00Z",
    notes: "Week 48",
    created_at: "2026-11-28T05:00:00Z",
    lines: [
      {
        id: "line-1",
        run_id: "run-1",
        profile_id: "prof-1",
        employee_name: "Vance, Jordan",
        work_state: "CA",
        regular_hours_milli: 40000,
        overtime_hours_milli: 6000,
        doubletime_hours_milli: 2000,
        bonus_cents: 10000,
        regular_pay_cents: 168000,
        overtime_pay_cents: 37800,
        doubletime_pay_cents: 16800,
        gross_pay_cents: 221000,
        pretax_health_cents: 15000,
        pretax_401k_cents: 5000,
        federal_income_tax_cents: 22000,
        state_income_tax_cents: 9300,
        social_security_cents: 13702,
        medicare_cents: 3205,
        union_dues_cents: 4500,
        net_pay_cents: 148300,
        employer_fica_cents: 16907,
        employer_futa_suta_cents: 4093,
        compliance_notes: "=CA §510 daily OT, IBT Local 705",
      },
    ],
  };

  const csv = buildPayrollRunCsv(run);
  const lines = csv.trimEnd().split("\r\n");
  expect(lines).toHaveLength(2);
  expect(lines[0]).toContain("Run Number,Period Start,Period End");
  expect(lines[1]).toContain('"Vance, Jordan"');
  expect(lines[1]).toContain(",CA,40.00,6.00,2.00,100.00,2210.00,");
  expect(lines[1]).toContain('"\'=CA §510 daily OT, IBT Local 705"');
});
