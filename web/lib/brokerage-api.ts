// N6 (package N): the brokerage routes (N1-N5) the transport screen uses. Each command keeps its
// record id and Idempotency-Key until it succeeds (the shared transport command helper).
import { ManagementApiError, managementFetch } from "./management-api";
import { base, command } from "./transport-api";
import type {
  Authority,
  CarrierPay,
  CarrierProfile,
  Confirmation,
  Eligibility,
  Margin,
  Tender,
  TenderList,
} from "./brokerage-contracts";

async function orNull<T>(read: Promise<T>): Promise<T | null> {
  try {
    return await read;
  } catch (error) {
    if (error instanceof ManagementApiError && error.code === "NOT_FOUND")
      return null;
    throw error;
  }
}

export const fetchAuthority = (business: string): Promise<Authority> =>
  managementFetch<Authority>(`${base(business)}/broker-authority`);
export type AuthorityBody = {
  schema_version: 1;
  expected_revision: number;
  jurisdiction: string;
  authority_number: string;
  bond_reference: string;
  status: "active" | "withdrawn";
  effective_from: string;
  expires_on: string | null;
  source: string;
  checked_on: string;
};
export const saveAuthority = (
  business: string,
  body: AuthorityBody,
): Promise<Authority> =>
  command<Authority>(`${base(business)}/broker-authority`, "PUT", body);
export const fetchBrokerEligibility = (
  business: string,
  on: string,
): Promise<Eligibility> =>
  managementFetch<Eligibility>(
    `${base(business)}/broker-authority/eligibility?on=${encodeURIComponent(on)}`,
  );

export const fetchProfile = (
  business: string,
  carrier: string,
): Promise<CarrierProfile> =>
  managementFetch<CarrierProfile>(
    `${base(business)}/carriers/${carrier}/profile`,
  );
export type ProfileBody = {
  schema_version: 1;
  expected_revision: number;
  jurisdiction: string;
  authority_number: string | null;
  liability_expires_on: string | null;
  cargo_expires_on: string | null;
  safety_rating: "satisfactory" | "conditional" | "unsatisfactory" | "unrated";
  source: string;
  checked_on: string;
};
export const saveProfile = (
  business: string,
  carrier: string,
  body: ProfileBody,
): Promise<CarrierProfile> =>
  command<CarrierProfile>(
    `${base(business)}/carriers/${carrier}/profile`,
    "PUT",
    body,
  );
export const fetchCarrierEligibility = (
  business: string,
  carrier: string,
  on: string,
): Promise<Eligibility> =>
  managementFetch<Eligibility>(
    `${base(business)}/carriers/${carrier}/eligibility?on=${encodeURIComponent(on)}`,
  );

export const fetchTenders = (
  business: string,
  trip: string,
): Promise<TenderList> =>
  managementFetch<TenderList>(`${base(business)}/trips/${trip}/tenders`);
export type TenderBody = {
  schema_version: 1;
  trip_id: string;
  legs: number[];
  counterparty_id: string;
  currency: string;
  basis: "fixed" | "per_mile";
  amount: string;
  terms: string;
  offered_at: string;
  expires_at: string;
};
export const saveTender = (
  business: string,
  tender: string,
  body: TenderBody,
): Promise<Tender> =>
  command<Tender>(`${base(business)}/tenders/${tender}`, "PUT", body);
export type AnswerBody = {
  schema_version: 1;
  kind: "accepted" | "declined" | "withdrawn";
  source: "email" | "phone" | "load_board" | "other";
  occurred_at: string;
};
export const answerTender = (
  business: string,
  tender: string,
  body: AnswerBody,
): Promise<Tender> =>
  command<Tender>(`${base(business)}/tenders/${tender}/answers`, "POST", body);

export const fetchConfirmation = (
  business: string,
  tender: string,
): Promise<Confirmation | null> =>
  orNull(
    managementFetch<Confirmation>(
      `${base(business)}/tenders/${tender}/rate-confirmation`,
    ),
  );
export type ProposalBody = {
  schema_version: 1;
  expected_revision: number;
  basis: "fixed" | "per_mile";
  amount: string;
  terms: string;
  document_id: null;
  proposed_at: string;
};
export const proposeVersion = (
  business: string,
  tender: string,
  body: ProposalBody,
): Promise<Confirmation> =>
  command<Confirmation>(
    `${base(business)}/tenders/${tender}/rate-confirmation`,
    "PUT",
    body,
  );
export type VersionAnswerBody = {
  schema_version: 1;
  kind: "agreed" | "declined";
  source: "email" | "phone" | "load_board" | "other";
  occurred_at: string;
};
export const answerVersion = (
  business: string,
  tender: string,
  revision: number,
  body: VersionAnswerBody,
): Promise<Confirmation> =>
  command<Confirmation>(
    `${base(business)}/tenders/${tender}/rate-confirmation/${revision}/answers`,
    "POST",
    body,
  );

export const fetchCarrierPay = (
  business: string,
  tender: string,
): Promise<CarrierPay | null> =>
  orNull(
    managementFetch<CarrierPay>(`${base(business)}/tenders/${tender}/accrual`),
  );
export type CarrierPayBody = {
  schema_version: 1;
  book_id: string;
  expense_account_id: string;
  payable_account_id: string;
  accrual_date: string;
  number: string;
  miles: string | null;
};
export const accrueCarrierPay = (
  business: string,
  tender: string,
  body: CarrierPayBody,
): Promise<CarrierPay> =>
  command<CarrierPay>(
    `${base(business)}/tenders/${tender}/accrual`,
    "POST",
    body,
  );

export const fetchMargin = (business: string, order: string): Promise<Margin> =>
  managementFetch<Margin>(`${base(business)}/orders/${order}/margin`);
