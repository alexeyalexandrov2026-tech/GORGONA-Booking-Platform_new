import { authorizedResponse } from "./management-api";

export type PaymentTerms =
  "Due on receipt" | "Net 15" | "Net 30" | "Net 45" | "Net 60";

export type QuoteStatus =
  | "draft"
  | "pending_approval"
  | "approved"
  | "sent"
  | "accepted"
  | "declined"
  | "converted"
  | "void";

export type PurchaseOrderStatus =
  | "draft"
  | "pending_approval"
  | "approved"
  | "issued"
  | "acknowledged"
  | "partially_received"
  | "received"
  | "matched"
  | "cancelled";

export type ThreeWayMatchStatus = "unmatched" | "variance" | "matched";
export type PolicyEntityKind = "quote" | "purchase_order";

export interface QuoteLineItem {
  description: string;
  sku: string | null;
  quantity: number;
  unit_price_cents: number;
  line_total_cents: number;
}

export interface QuoteView {
  id: string;
  quote_number: string;
  title: string;
  counterparty_id: string | null;
  counterparty_name: string;
  counterparty_email: string | null;
  currency: "USD";
  items: QuoteLineItem[];
  subtotal_cents: number;
  discount_cents: number;
  tax_cents: number;
  total_cents: number;
  payment_terms: PaymentTerms;
  valid_until: string | null;
  notes: string;
  status: QuoteStatus;
  approval_required: boolean;
  approved_at: string | null;
  accepted_by_name: string | null;
  accepted_at: string | null;
  declined_reason: string | null;
  payment_session_id: string | null;
  converted_invoice_ref: string | null;
  created_at: string;
  updated_at: string;
}

export interface PurchaseOrderLineItem {
  description: string;
  sku: string | null;
  quantity_ordered: number;
  quantity_received: number;
  unit_cost_cents: number;
  line_total_cents: number;
}

export interface PurchaseOrderView {
  id: string;
  po_number: string;
  title: string;
  vendor_counterparty_id: string | null;
  vendor_name: string;
  vendor_email: string | null;
  currency: "USD";
  items: PurchaseOrderLineItem[];
  total_cents: number;
  payment_terms: PaymentTerms;
  expected_delivery_date: string | null;
  notes: string;
  status: PurchaseOrderStatus;
  received_total_cents: number;
  vendor_bill_number: string | null;
  vendor_bill_cents: number | null;
  three_way_match_status: ThreeWayMatchStatus;
  variance_cents: number;
  approval_required: boolean;
  approved_at: string | null;
  vendor_acknowledged_by: string | null;
  vendor_acknowledged_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ApprovalPolicyView {
  entity_kind: PolicyEntityKind;
  threshold_cents: number;
  require_owner_above_threshold: boolean;
  auto_approve_below_threshold: boolean;
  updated_at: string | null;
}

export interface CommercialSummaryView {
  currency: "USD";
  quotes_open_count: number;
  quotes_pipeline_cents: number;
  quotes_accepted_count: number;
  quotes_accepted_cents: number;
  quotes_pending_approval_count: number;
  po_open_count: number;
  po_committed_cents: number;
  po_pending_approval_count: number;
  po_matched_count: number;
  po_variance_count: number;
}

export interface PortalShareResponse {
  entity_kind: PolicyEntityKind;
  entity_id: string;
  portal_url: string;
  token_prefix: string;
  expires_at: string;
}

export interface ConvertQuotePaymentResponse {
  quote: QuoteView;
  payment_session_id: string;
  checkout_url: string;
}

export interface PortalPublicDocument {
  entity_kind: PolicyEntityKind;
  business_name: string;
  expires_at: string;
  responded_at: string | null;
  quote: QuoteView | null;
  purchase_order: PurchaseOrderView | null;
  checkout_url: string | null;
}

async function commercialRequest<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (init.body !== undefined) headers["Content-Type"] = "application/json";
  const res = await authorizedResponse(path, { ...init, headers });
  return (await res.json()) as T;
}

const base = (businessId: string) =>
  `/v1/businesses/${encodeURIComponent(businessId)}/commercial`;

export function fetchCommercialSummary(
  businessId: string,
): Promise<CommercialSummaryView> {
  return commercialRequest<CommercialSummaryView>(
    `${base(businessId)}/summary`,
  );
}

export function fetchApprovalPolicies(
  businessId: string,
): Promise<ApprovalPolicyView[]> {
  return commercialRequest<ApprovalPolicyView[]>(
    `${base(businessId)}/policies`,
  );
}

export function updateApprovalPolicy(
  businessId: string,
  entityKind: PolicyEntityKind,
  input: {
    threshold_cents: number;
    require_owner_above_threshold: boolean;
    auto_approve_below_threshold: boolean;
  },
): Promise<ApprovalPolicyView> {
  return commercialRequest<ApprovalPolicyView>(
    `${base(businessId)}/policies/${entityKind}`,
    {
      method: "PUT",
      body: JSON.stringify(input),
    },
  );
}

export function fetchQuotes(businessId: string): Promise<QuoteView[]> {
  return commercialRequest<QuoteView[]>(`${base(businessId)}/quotes`);
}

export function createQuote(
  businessId: string,
  input: {
    quote_number?: string | null;
    title: string;
    counterparty_name: string;
    counterparty_email?: string | null;
    items: Array<{
      description: string;
      sku?: string | null;
      quantity: number;
      unit_price_cents: number;
    }>;
    discount_cents?: number;
    tax_rate_bps?: number;
    payment_terms?: PaymentTerms;
    valid_until?: string | null;
    notes?: string;
  },
): Promise<QuoteView> {
  return commercialRequest<QuoteView>(`${base(businessId)}/quotes`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function approveQuote(
  businessId: string,
  quoteId: string,
): Promise<QuoteView> {
  return commercialRequest<QuoteView>(
    `${base(businessId)}/quotes/${encodeURIComponent(quoteId)}/approve`,
    { method: "POST" },
  );
}

export function shareQuotePortal(
  businessId: string,
  quoteId: string,
): Promise<PortalShareResponse> {
  return commercialRequest<PortalShareResponse>(
    `${base(businessId)}/quotes/${encodeURIComponent(quoteId)}/share`,
    { method: "POST" },
  );
}

export function convertQuoteToStripePayment(
  businessId: string,
  quoteId: string,
): Promise<ConvertQuotePaymentResponse> {
  return commercialRequest<ConvertQuotePaymentResponse>(
    `${base(businessId)}/quotes/${encodeURIComponent(quoteId)}/convert-payment`,
    { method: "POST" },
  );
}

export function fetchPurchaseOrders(
  businessId: string,
): Promise<PurchaseOrderView[]> {
  return commercialRequest<PurchaseOrderView[]>(
    `${base(businessId)}/purchase-orders`,
  );
}

export function createPurchaseOrder(
  businessId: string,
  input: {
    po_number?: string | null;
    title: string;
    vendor_name: string;
    vendor_email?: string | null;
    items: Array<{
      description: string;
      sku?: string | null;
      quantity_ordered: number;
      unit_cost_cents: number;
    }>;
    payment_terms?: PaymentTerms;
    expected_delivery_date?: string | null;
    notes?: string;
  },
): Promise<PurchaseOrderView> {
  return commercialRequest<PurchaseOrderView>(
    `${base(businessId)}/purchase-orders`,
    {
      method: "POST",
      body: JSON.stringify(input),
    },
  );
}

export function approvePurchaseOrder(
  businessId: string,
  poId: string,
): Promise<PurchaseOrderView> {
  return commercialRequest<PurchaseOrderView>(
    `${base(businessId)}/purchase-orders/${encodeURIComponent(poId)}/approve`,
    { method: "POST" },
  );
}

export function sharePurchaseOrderPortal(
  businessId: string,
  poId: string,
): Promise<PortalShareResponse> {
  return commercialRequest<PortalShareResponse>(
    `${base(businessId)}/purchase-orders/${encodeURIComponent(poId)}/share`,
    { method: "POST" },
  );
}

export function recordPurchaseOrderReceipt(
  businessId: string,
  poId: string,
  receivedQuantities: number[],
): Promise<PurchaseOrderView> {
  return commercialRequest<PurchaseOrderView>(
    `${base(businessId)}/purchase-orders/${encodeURIComponent(poId)}/receive`,
    {
      method: "POST",
      body: JSON.stringify({ received_quantities: receivedQuantities }),
    },
  );
}

export function matchPurchaseOrderVendorBill(
  businessId: string,
  poId: string,
  vendorBillNumber: string,
  vendorBillCents: number,
): Promise<PurchaseOrderView> {
  return commercialRequest<PurchaseOrderView>(
    `${base(businessId)}/purchase-orders/${encodeURIComponent(poId)}/match-bill`,
    {
      method: "POST",
      body: JSON.stringify({
        vendor_bill_number: vendorBillNumber,
        vendor_bill_cents: vendorBillCents,
      }),
    },
  );
}

export async function fetchPublicPortalDocument(
  token: string,
): Promise<PortalPublicDocument> {
  const res = await fetch(`/v1/portal/${encodeURIComponent(token)}`, {
    cache: "no-store",
  });
  if (!res.ok) {
    const errBody = (await res.json().catch(() => null)) as {
      detail?: string;
    } | null;
    throw new Error(
      errBody?.detail || `Portal link is unavailable (${res.status}).`,
    );
  }
  return (await res.json()) as PortalPublicDocument;
}

export async function respondPublicPortalDocument(
  token: string,
  input: {
    action: "accept" | "decline" | "acknowledge";
    actor_name: string;
    reason?: string | null;
  },
): Promise<PortalPublicDocument> {
  const res = await fetch(`/v1/portal/${encodeURIComponent(token)}/respond`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(input),
  });
  if (!res.ok) {
    const errBody = (await res.json().catch(() => null)) as {
      detail?: string;
    } | null;
    throw new Error(
      errBody?.detail || `Could not submit portal response (${res.status}).`,
    );
  }
  return (await res.json()) as PortalPublicDocument;
}
