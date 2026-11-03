// O7a (package O): money and quantity rules of the construction forms. Money is typed in the
// project currency's major units and sent as exact minor units (no float); the decimal places come
// from ISO 4217 through Intl. Totals are never computed here: the server derives them.
export const MONEY_MAX = 1_000_000_000_000;

/** The ISO 4217 decimal places of a currency, or null for a code Intl does not know. */
export function currencyPlaces(code: string): number | null {
  try {
    return new Intl.NumberFormat("en", {
      style: "currency",
      currency: code,
    }).resolvedOptions().maximumFractionDigits!;
  } catch {
    return null;
  }
}

/** A non-negative amount in major units as exact minor units, or null if it is not one. */
export function toMinor(text: string, places: number): number | null {
  const match = /^(0|[1-9]\d{0,15})(?:\.(\d+))?$/.exec(text.trim());
  if (!match) return null;
  const fraction = match[2] ?? "";
  if (fraction.length > places) return null;
  const minor =
    BigInt(match[1]!) * 10n ** BigInt(places) +
    BigInt(fraction.padEnd(places, "0") || "0");
  return minor <= BigInt(MONEY_MAX) ? Number(minor) : null;
}

/** Minor units as major units with the currency's places, e.g. -2500 at 2 is "-25.00". */
export function formatMinor(minor: number, places: number): string {
  const sign = minor < 0 ? "-" : "";
  const digits = Math.abs(minor)
    .toString()
    .padStart(places + 1, "0");
  return places
    ? `${sign}${digits.slice(0, -places)}.${digits.slice(-places)}`
    : `${sign}${digits}`;
}

/** A server quantity without its padding: "10.0000" is "10", "2.5000" is "2.5". */
export function quantityText(quantity: string): string {
  return quantity.includes(".")
    ? quantity.replace(/0+$/, "").replace(/\.$/, "")
    : quantity;
}

/** A quantity the server takes: above 0, at most 999999999.9999, at most 4 decimal places. */
export function validQuantity(text: string): boolean {
  return /^(0|[1-9]\d{0,8})(\.\d{1,4})?$/.test(text) && /[1-9]/.test(text);
}
