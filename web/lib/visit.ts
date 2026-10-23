import type { Bootstrap, Quote, Selection } from "./contracts";

// L7c (package L): a visit is an ordered list of services, each with its own add-ons
// (L2 design decisions 11-15, L7 decisions 48-53). The server decides; these only shape
// the request and what is offered.
export type Line = { variant_id: string; add_on_ids: string[] };
type Catalog = Pick<Bootstrap, "variants" | "add_ons">;
export const MAX_EXTRA_LINES = 4;
// Refusals of the visit itself: retrying the same request cannot help.
export const REFUSALS = [
  "INCOMPATIBLE_SELECTION",
  "SERVICE_NOT_BOOKABLE",
  "ADD_ON_NOT_BOOKABLE",
];

/** The request of a visit; one service stays byte-identical to the request before L7c. */
export function selectionOf(
  location_id: string,
  lines: Line[],
  resource_id: string | null,
): Selection {
  const [first, ...extra] = lines;
  return {
    location_id,
    variant_id: first?.variant_id ?? "",
    add_on_ids: first?.add_on_ids ?? [],
    resource_id,
    ...(extra.length
      ? {
          extra_lines: extra.map((line) => ({
            variant_id: line.variant_id,
            add_on_ids: line.add_on_ids,
          })),
        }
      : {}),
  };
}

/** Services a line may choose: a further line takes one not yet in the visit, in its currency. */
export function servicesOffered(
  catalog: Catalog,
  lines: Line[],
  index: number,
): Catalog["variants"] {
  if (index === 0) return catalog.variants;
  const first = catalog.variants.find((v) => v.id === lines[0]?.variant_id);
  return catalog.variants.filter(
    (v) =>
      (!first || v.currency === first.currency) &&
      !lines.some((line, i) => i !== index && line.variant_id === v.id),
  );
}

/** An add-on is offered on a line when the composition rules hold across the whole visit. */
export function addOnOffered(
  catalog: Catalog,
  lines: Line[],
  index: number,
  addOnId: string,
): boolean {
  const addOn = catalog.add_ons.find((a) => a.id === addOnId);
  const first = catalog.variants.find((v) => v.id === lines[0]?.variant_id);
  if (!addOn || !first || addOn.currency !== first.currency) return false;
  if (lines.some((line, i) => i !== index && line.add_on_ids.includes(addOnId)))
    return false;
  const provided = new Set([
    ...lines.flatMap(
      (line) =>
        catalog.variants.find((v) => v.id === line.variant_id)?.provides ?? [],
    ),
    ...lines
      .flatMap((line) => line.add_on_ids)
      .filter((id) => id !== addOnId)
      .flatMap(
        (id) => catalog.add_ons.find((a) => a.id === id)?.provides ?? [],
      ),
  ]);
  return (
    addOn.requires.every((c) => provided.has(c)) &&
    !addOn.provides.some((c) => provided.has(c)) &&
    !addOn.conflicts_with.some((c) => provided.has(c))
  );
}

/** One specialist serves the whole visit (L2 decision 14). */
export function servingAll<
  T extends { location_id: string; service_ids: string[] },
>(artists: T[], locationId: string, serviceIds: string[]): T[] {
  return artists.filter(
    (a) =>
      a.location_id === locationId &&
      serviceIds.every((id) => a.service_ids.includes(id)),
  );
}

type StageKind = Extract<Quote, { version: 2 }>["stages"][number]["kind"];
const stageWords: Record<StageKind, string> = {
  active: "With your specialist",
  processing: "Processing — your specialist is free meanwhile",
  finish: "Finish",
};

export function stageText(kind: StageKind): string {
  return stageWords[kind];
}
