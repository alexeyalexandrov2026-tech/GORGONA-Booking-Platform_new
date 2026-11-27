/**
 * The 39 industry directions of the GORGONA catalog, grouped by NAICS 2022 sector.
 *
 * Mirror of `api/src/gorgona_booking/business/catalog.py` (`_IDENTITIES`, `_EXAMPLES`). The
 * landing page is a static export and cannot call `/v1/onboarding/presets` at build time, so the
 * public descriptions are kept here; the API stays the runtime source of truth for onboarding.
 * Numbers are stable identifiers, never positions. The NAICS mapping is a discovery aid, not a
 * company's legal registration or a regulatory approval.
 */
export interface Industry {
  readonly id: number;
  readonly name: string;
  /** NAICS 2022 sector codes this direction maps to ("44-45" is one sector). */
  readonly naics: readonly string[];
  readonly examples: string;
}

export interface NaicsSector {
  readonly code: string;
  /** Short label for filter chips. */
  readonly label: string;
}

export const NAICS_SECTORS: readonly NaicsSector[] = [
  { code: "11", label: "Agriculture" },
  { code: "21", label: "Mining" },
  { code: "22", label: "Utilities" },
  { code: "23", label: "Construction" },
  { code: "31-33", label: "Manufacturing" },
  { code: "42", label: "Wholesale" },
  { code: "44-45", label: "Retail" },
  { code: "48-49", label: "Transportation" },
  { code: "51", label: "Information" },
  { code: "52", label: "Finance" },
  { code: "53", label: "Real estate" },
  { code: "54", label: "Professional services" },
  { code: "55", label: "Management" },
  { code: "56", label: "Admin and support" },
  { code: "61", label: "Education" },
  { code: "62", label: "Health and social care" },
  { code: "71", label: "Arts and recreation" },
  { code: "72", label: "Food and lodging" },
  { code: "81", label: "Personal and other services" },
  { code: "92", label: "Public administration" },
];

export const INDUSTRIES: readonly Industry[] = [
  {
    id: 1,
    name: "Beauty and personal care",
    naics: ["81"],
    examples:
      "Hair, barbering, nails, brows, lashes, makeup, skin care, spa, massage, tattoos, piercing, permanent makeup, mobile beauty, chair rental and training; clinical aesthetics requires a separately accepted clinical workflow",
  },
  {
    id: 2,
    name: "Restaurants and food service",
    naics: ["72"],
    examples:
      "Independent restaurants, chains, cafes, bars, bakeries, food trucks, catering and delivery kitchens",
  },
  {
    id: 3,
    name: "Retail",
    naics: ["44-45"],
    examples:
      "Grocery, clothing, cosmetics, electronics, furniture, flowers and building materials",
  },
  {
    id: 4,
    name: "E-commerce",
    naics: ["44-45", "51"],
    examples:
      "Online shops, digital goods, subscriptions and external marketplace sellers",
  },
  {
    id: 5,
    name: "Wholesale",
    naics: ["42"],
    examples:
      "Distributors and suppliers of food, materials, equipment and parts",
  },
  {
    id: 6,
    name: "Legal services",
    naics: ["54"],
    examples:
      "Law firms, attorneys, immigration practices and notarial services",
  },
  {
    id: 7,
    name: "Accounting and tax",
    naics: ["54"],
    examples:
      "Accountants, auditors, tax consultants and outsourced accounting",
  },
  {
    id: 8,
    name: "Consulting",
    naics: ["54"],
    examples: "Management, financial, human resources and industry consultants",
  },
  {
    id: 9,
    name: "Marketing and creative services",
    naics: ["54"],
    examples:
      "Agencies, designers, photographers, video studios and production services",
  },
  {
    id: 10,
    name: "IT and software",
    naics: ["51", "54"],
    examples: "Developers, SaaS companies, integrators and IT support",
  },
  {
    id: 11,
    name: "Media and telecommunications",
    naics: ["51"],
    examples:
      "Publishers, digital content, media companies and connectivity providers",
  },
  {
    id: 12,
    name: "Education",
    naics: ["61"],
    examples:
      "Tutors, schools, colleges, training centers, driving schools and online courses",
  },
  {
    id: 13,
    name: "Sports and fitness",
    naics: ["71"],
    examples: "Gyms, studios, coaches, sports schools, facilities and clubs",
  },
  {
    id: 14,
    name: "Healthcare and rehabilitation",
    naics: ["62"],
    examples:
      "Practices, clinics, dental offices, laboratories, therapists and medical aesthetics",
  },
  {
    id: 15,
    name: "Veterinary and animal services",
    naics: ["54", "81"],
    examples: "Veterinary clinics, grooming, training and animal boarding",
  },
  {
    id: 16,
    name: "Social services and care",
    naics: ["62"],
    examples: "Home care, elder care, childcare and support services",
  },
  {
    id: 17,
    name: "Hospitality and tourism",
    naics: ["72", "56"],
    examples:
      "Hotels, resorts, yacht charters, marinas, travel agencies and tour operators",
  },
  {
    id: 18,
    name: "Events, culture and entertainment",
    naics: ["71"],
    examples: "Organizers, venues, theaters, museums and entertainment centers",
  },
  {
    id: 19,
    name: "Construction and design",
    naics: ["23", "54"],
    examples:
      "General contractors, subcontractors, renovation, architects, engineers and developers",
  },
  {
    id: 20,
    name: "Field and home services",
    naics: ["23", "56", "81"],
    examples:
      "Electricians, plumbers, HVAC, appliance repair, landscaping and installation",
  },
  {
    id: 21,
    name: "Automotive sales and services",
    naics: ["44-45", "81"],
    examples: "Repair shops, tires, detailing, car washes and dealerships",
  },
  {
    id: 22,
    name: "Real estate",
    naics: ["53"],
    examples:
      "Agents, property managers, residential and commercial rentals and coworking",
  },
  {
    id: 23,
    name: "Rental and leasing",
    naics: ["53"],
    examples:
      "Cars, trucks, equipment, tools, yachts, yacht charters, boats, marinas, clothing, inventory and self-storage",
  },
  {
    id: 24,
    name: "Transportation and logistics",
    naics: ["48-49"],
    examples:
      "Owner-operators, fleets, dispatchers, freight brokers, forwarders, 3PL, interstate trucking, couriers, last mile, movers, passenger, international and multimodal transport",
  },
  {
    id: 25,
    name: "Warehouse operators",
    naics: ["48-49"],
    examples:
      "Customer-owned warehouses, 3PL, fulfillment and distribution centers",
  },
  {
    id: 26,
    name: "Manufacturing",
    naics: ["31-33"],
    examples: "Food, furniture, textiles, metalworking and assembly",
  },
  {
    id: 27,
    name: "Agriculture, forestry and fishing",
    naics: ["11"],
    examples: "Farms, greenhouses, nurseries, livestock, forestry and fishing",
  },
  {
    id: 28,
    name: "Energy and utilities",
    naics: ["22"],
    examples:
      "Electricity, gas, water, heating, solar and infrastructure maintenance",
  },
  {
    id: 29,
    name: "Mining and extraction",
    naics: ["21"],
    examples: "Quarries, mining, oil and gas operators and contractors",
  },
  {
    id: 30,
    name: "Finance and insurance",
    naics: ["52"],
    examples:
      "Agencies, brokers, advisers, banks, lenders, investment and payment companies",
  },
  {
    id: 31,
    name: "Recruiting and staffing",
    naics: ["56"],
    examples:
      "Recruiters, staffing agencies, temporary labor and outsourced HR",
  },
  {
    id: 32,
    name: "Security services",
    naics: ["56"],
    examples: "Guard services, security installation and maintenance",
  },
  {
    id: 33,
    name: "Cleaning and facilities services",
    naics: ["56", "81"],
    examples: "Cleaning, laundry, dry cleaning and building operations",
  },
  {
    id: 34,
    name: "Environmental and waste services",
    naics: ["56"],
    examples:
      "Waste collection, recycling, environmental services and remediation",
  },
  {
    id: 35,
    name: "Other personal services",
    naics: ["81"],
    examples:
      "Tailors, shoe repair, home organizers, funeral and other personal services",
  },
  {
    id: 36,
    name: "Organizations and associations",
    naics: ["81"],
    examples:
      "Foundations, associations, professional, religious and membership organizations",
  },
  {
    id: 37,
    name: "Scientific and research services",
    naics: ["54"],
    examples: "Research centers, testing laboratories and product development",
  },
  {
    id: 38,
    name: "Management of companies",
    naics: ["55"],
    examples: "Holding management, corporate centers and shared services",
  },
  {
    id: 39,
    name: "Public administration",
    naics: ["92"],
    examples:
      "Government institutions, municipal services and public service departments",
  },
];

const SECTOR_LABELS = new Map(
  NAICS_SECTORS.map((sector) => [sector.code, sector.label] as const),
);

/** "44-45" is shown as "44–45" (en dash) to read as a range. */
export function formatSectorCode(code: string): string {
  return code.replace("-", "–");
}

export function sectorLabel(code: string): string {
  return SECTOR_LABELS.get(code) ?? code;
}
