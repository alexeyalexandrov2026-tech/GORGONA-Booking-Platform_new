import type { PayrollRun } from "./global-finance-api";

const FORMULA_TRIGGER_RE = /^[=+\-@\t\r]/;

export function escapeCsvCell(value: string | number): string {
  let raw = String(value);
  if (typeof value === "string" && FORMULA_TRIGGER_RE.test(raw)) {
    raw = `'${raw}`;
  }
  if (/[",\n\r]/.test(raw)) {
    return `"${raw.replace(/"/g, '""')}"`;
  }
  return raw;
}

function centsToUsd(cents: number): string {
  return (cents / 100).toFixed(2);
}

function milliToHours(milli: number): string {
  return (milli / 1000).toFixed(2);
}

export function buildPayrollRunCsv(run: PayrollRun): string {
  const headers = [
    "Run Number",
    "Period Start",
    "Period End",
    "Pay Date",
    "Status",
    "Employee Name",
    "Work State",
    "Regular Hours",
    "Overtime Hours",
    "Doubletime Hours",
    "Bonus USD",
    "Gross Pay USD",
    "Federal Tax USD",
    "State Tax USD",
    "Social Security USD",
    "Medicare USD",
    "Pre-Tax Health USD",
    "Pre-Tax 401k USD",
    "Union Dues USD",
    "Net Pay USD",
    "Employer FICA USD",
    "Employer FUTA/SUTA USD",
    "Compliance Notes",
  ];
  const rows = [headers.map(escapeCsvCell).join(",")];
  for (const line of run.lines) {
    rows.push(
      [
        run.run_number,
        run.period_start,
        run.period_end,
        run.pay_date,
        run.status,
        line.employee_name,
        line.work_state,
        milliToHours(line.regular_hours_milli),
        milliToHours(line.overtime_hours_milli),
        milliToHours(line.doubletime_hours_milli),
        centsToUsd(line.bonus_cents),
        centsToUsd(line.gross_pay_cents),
        centsToUsd(line.federal_income_tax_cents),
        centsToUsd(line.state_income_tax_cents),
        centsToUsd(line.social_security_cents),
        centsToUsd(line.medicare_cents),
        centsToUsd(line.pretax_health_cents),
        centsToUsd(line.pretax_401k_cents),
        centsToUsd(line.union_dues_cents),
        centsToUsd(line.net_pay_cents),
        centsToUsd(line.employer_fica_cents),
        centsToUsd(line.employer_futa_suta_cents),
        line.compliance_notes,
      ]
        .map(escapeCsvCell)
        .join(","),
    );
  }
  return `${rows.join("\r\n")}\r\n`;
}

export function triggerCsvDownload(filename: string, csvContent: string): void {
  const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.style.display = "none";
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
