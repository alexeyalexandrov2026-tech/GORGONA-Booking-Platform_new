import type { Delegation } from "./delegation-contracts";
import type { CustomerProposalLink } from "./construction-contracts";

export function customerGrantMatches(
  grant: Delegation,
  business: string,
  company: string | null,
  location: string,
  now = Date.now(),
): boolean {
  return (
    grant.owner_business_id === business &&
    grant.servicer_business_id === company &&
    grant.status === "active" &&
    !grant.expired &&
    Date.parse(grant.expires_at) > now &&
    grant.permissions.includes("construction.customer_answer") &&
    (grant.location_id === null || grant.location_id === location) &&
    grant.delegates.length > 0
  );
}

export function customerDocumentLinks(
  reference: CustomerProposalLink,
  changes: readonly number[],
) {
  const query = new URLSearchParams(reference).toString();
  return {
    proposal: `/construction/customer/?${query}`,
    acceptance: `/construction/customer/acceptance/?${query}`,
    changes: changes.map((number) => ({
      number,
      href: `/construction/customer/change/?${query}&number=${number}`,
    })),
  };
}
