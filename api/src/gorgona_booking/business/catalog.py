"""Stable industry identities from the owner's 39-sector master plan.

Catalog revision is separate from workflow acceptance: `workflow_readiness` is read
from the readiness registry (ADR-0019). The NAICS sector mapping is a discovery aid,
not a company's legal registration or regulatory approval.
"""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from gorgona_booking.business.readiness_registry import PROFILE_READINESS, Readiness

CATALOG_VERSION: Literal[1] = 1


class BusinessFormat(StrEnum):
    B2B = "b2b"
    B2C = "b2c"
    MARKETPLACE = "marketplace"
    FRANCHISE = "franchise"
    HOLDING = "holding"


class Industry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: int = Field(ge=1, le=39)
    code: str
    name: str
    examples: str
    naics_sectors: tuple[str, ...]
    workflow_readiness: Readiness = Readiness.PLANNED


class IndustryCatalog(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1] = 1
    catalog_version: int = CATALOG_VERSION
    classification: Literal["NAICS-2022-sector-mapping"] = "NAICS-2022-sector-mapping"
    industries: tuple[Industry, ...]
    business_formats: tuple[BusinessFormat, ...] = tuple(BusinessFormat)


# Numbers are stable identifiers, not positions to renumber when translations change.
_IDENTITIES: tuple[tuple[int, str, str, tuple[str, ...]], ...] = (
    (1, "beauty", "Beauty and personal care", ("81",)),
    (2, "restaurants", "Restaurants and food service", ("72",)),
    (3, "retail", "Retail", ("44-45",)),
    (4, "ecommerce", "E-commerce", ("44-45", "51")),
    (5, "wholesale", "Wholesale", ("42",)),
    (6, "legal", "Legal services", ("54",)),
    (7, "accounting", "Accounting and tax", ("54",)),
    (8, "consulting", "Consulting", ("54",)),
    (9, "creative", "Marketing and creative services", ("54",)),
    (10, "technology", "IT and software", ("51", "54")),
    (11, "media", "Media and telecommunications", ("51",)),
    (12, "education", "Education", ("61",)),
    (13, "fitness", "Sports and fitness", ("71",)),
    (14, "healthcare", "Healthcare and rehabilitation", ("62",)),
    (15, "animal_services", "Veterinary and animal services", ("54", "81")),
    (16, "social_care", "Social services and care", ("62",)),
    (17, "hospitality", "Hospitality and tourism", ("72", "56")),
    (18, "events", "Events, culture and entertainment", ("71",)),
    (19, "construction", "Construction and design", ("23", "54")),
    (20, "field_services", "Field and home services", ("23", "56", "81")),
    (21, "automotive", "Automotive sales and services", ("44-45", "81")),
    (22, "real_estate", "Real estate", ("53",)),
    (23, "rental", "Rental and leasing", ("53",)),
    (24, "logistics", "Transportation and logistics", ("48-49",)),
    (25, "warehousing", "Warehouse operators", ("48-49",)),
    (26, "manufacturing", "Manufacturing", ("31-33",)),
    (27, "agriculture", "Agriculture, forestry and fishing", ("11",)),
    (28, "utilities", "Energy and utilities", ("22",)),
    (29, "mining", "Mining and extraction", ("21",)),
    (30, "finance", "Finance and insurance", ("52",)),
    (31, "staffing", "Recruiting and staffing", ("56",)),
    (32, "security", "Security services", ("56",)),
    (33, "facilities", "Cleaning and facilities services", ("56", "81")),
    (34, "environment", "Environmental and waste services", ("56",)),
    (35, "personal_services", "Other personal services", ("81",)),
    (36, "organizations", "Organizations and associations", ("81",)),
    (37, "research", "Scientific and research services", ("54",)),
    (38, "company_management", "Management of companies", ("55",)),
    (39, "public_administration", "Public administration", ("92",)),
)

_EXAMPLES = (
    "Hair, barbering, nails, brows, lashes, makeup, skin care, spa, massage, tattoos, "
    "piercing, permanent makeup, mobile beauty, chair rental and training; clinical aesthetics "
    "requires a separately accepted clinical workflow",
    "Independent restaurants, chains, cafes, bars, bakeries, food trucks, "
    "catering and delivery kitchens",
    "Grocery, clothing, cosmetics, electronics, furniture, flowers and building materials",
    "Online shops, digital goods, subscriptions and external marketplace sellers",
    "Distributors and suppliers of food, materials, equipment and parts",
    "Law firms, attorneys, immigration practices and notarial services",
    "Accountants, auditors, tax consultants and outsourced accounting",
    "Management, financial, human resources and industry consultants",
    "Agencies, designers, photographers, video studios and production services",
    "Developers, SaaS companies, integrators and IT support",
    "Publishers, digital content, media companies and connectivity providers",
    "Tutors, schools, colleges, training centers, driving schools and online courses",
    "Gyms, studios, coaches, sports schools, facilities and clubs",
    "Practices, clinics, dental offices, laboratories, therapists and medical aesthetics",
    "Veterinary clinics, grooming, training and animal boarding",
    "Home care, elder care, childcare and support services",
    "Hotels, resorts, travel agencies and tour operators",
    "Organizers, venues, theaters, museums and entertainment centers",
    "General contractors, subcontractors, renovation, architects, engineers and developers",
    "Electricians, plumbers, HVAC, appliance repair, landscaping and installation",
    "Repair shops, tires, detailing, car washes and dealerships",
    "Agents, property managers, residential and commercial rentals and coworking",
    "Cars, trucks, equipment, tools, boats, clothing, inventory and self-storage",
    "Owner-operators, fleets, dispatchers, freight brokers, forwarders, 3PL, interstate trucking, "
    "couriers, last mile, movers, passenger, international and multimodal transport",
    "Customer-owned warehouses, 3PL, fulfillment and distribution centers",
    "Food, furniture, textiles, metalworking and assembly",
    "Farms, greenhouses, nurseries, livestock, forestry and fishing",
    "Electricity, gas, water, heating, solar and infrastructure maintenance",
    "Quarries, mining, oil and gas operators and contractors",
    "Agencies, brokers, advisers, banks, lenders, investment and payment companies",
    "Recruiters, staffing agencies, temporary labor and outsourced HR",
    "Guard services, security installation and maintenance",
    "Cleaning, laundry, dry cleaning and building operations",
    "Waste collection, recycling, environmental services and remediation",
    "Tailors, shoe repair, home organizers, funeral and other personal services",
    "Foundations, associations, professional, religious and membership organizations",
    "Research centers, testing laboratories and product development",
    "Holding management, corporate centers and shared services",
    "Government institutions, municipal services and public service departments",
)

INDUSTRIES = tuple(
    Industry(
        id=number,
        code=code,
        name=name,
        examples=examples,
        naics_sectors=sectors,
        workflow_readiness=PROFILE_READINESS[number],
    )
    for (number, code, name, sectors), examples in zip(_IDENTITIES, _EXAMPLES, strict=True)
)
INDUSTRY_IDS = frozenset(industry.id for industry in INDUSTRIES)
CATALOG = IndustryCatalog(industries=INDUSTRIES)
