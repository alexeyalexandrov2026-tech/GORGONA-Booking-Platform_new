import { authorizedResponse } from "./management-api";

async function paymentsRequest<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (init.body !== undefined) headers["Content-Type"] = "application/json";
  const res = await authorizedResponse(path, { ...init, headers });
  return (await res.json()) as T;
}

export interface PaymentsConfig {
  stripe_configured: boolean;
  stripe_livemode: boolean;
  stripe_publishable_key: string | null;
  webhook_configured: boolean;
  paypal_configured: boolean;
  currency: "USD";
  payment_methods: string[];
}

export interface PaymentSession {
  id: string;
  provider: "stripe" | "paypal";
  livemode: boolean;
  provider_session_id: string;
  provider_payment_intent_id: string | null;
  connected_account_id: string | null;
  reference_kind: "invoice" | "order" | "deposit" | "service" | "custom";
  reference_id: string | null;
  customer_name: string;
  customer_email: string | null;
  description: string;
  amount_cents: number;
  currency: "USD";
  status: "open" | "paid" | "expired" | "failed" | "refunded";
  checkout_url: string;
  paid_at: string | null;
  refunded_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface CreateCheckoutSessionInput {
  amount_cents: number;
  description: string;
  reference_kind: "invoice" | "order" | "deposit" | "service" | "custom";
  reference_id?: string | null;
  customer_name?: string;
  customer_email?: string | null;
  allow_ach?: boolean;
  connected_account_id?: string | null;
}

export async function fetchPaymentsConfig(): Promise<PaymentsConfig> {
  const res = await fetch("/v1/payments/config", { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`Unable to read payments configuration (${res.status}).`);
  }
  return (await res.json()) as PaymentsConfig;
}

export async function fetchPaymentSessions(
  businessId: string,
): Promise<PaymentSession[]> {
  return paymentsRequest<PaymentSession[]>(
    `/v1/businesses/${encodeURIComponent(businessId)}/payments/sessions`,
  );
}

export async function createCheckoutSession(
  businessId: string,
  input: CreateCheckoutSessionInput,
): Promise<PaymentSession> {
  return paymentsRequest<PaymentSession>(
    `/v1/businesses/${encodeURIComponent(businessId)}/payments/checkout-sessions`,
    {
      method: "POST",
      body: JSON.stringify(input),
    },
  );
}

export async function syncPaymentSession(
  businessId: string,
  sessionId: string,
): Promise<PaymentSession> {
  return paymentsRequest<PaymentSession>(
    `/v1/businesses/${encodeURIComponent(businessId)}/payments/sessions/${encodeURIComponent(sessionId)}/sync`,
    { method: "POST" },
  );
}

export async function refundPaymentSession(
  businessId: string,
  sessionId: string,
): Promise<PaymentSession> {
  return paymentsRequest<PaymentSession>(
    `/v1/businesses/${encodeURIComponent(businessId)}/payments/sessions/${encodeURIComponent(sessionId)}/refund`,
    {
      method: "POST",
      body: JSON.stringify({ reason: "requested_by_customer" }),
    },
  );
}

export interface UnmatchedStripeSession {
  id: string;
  provider_session_id: string;
  amount_cents: number;
  reference_kind: string;
  reference_id: string | null;
  description: string;
}

export interface StripeLedgerReconciliation {
  currency: "USD";
  stripe_paid_count: number;
  stripe_paid_cents: number;
  stripe_open_count: number;
  stripe_open_cents: number;
  stripe_refunded_count: number;
  stripe_refunded_cents: number;
  fin03_issued_invoices_count: number;
  fin03_issued_total_cents: number;
  matched_invoice_sessions_count: number;
  unmatched_paid_sessions: UnmatchedStripeSession[];
}

export interface SaasPlan {
  id: "starter" | "growth" | "scale";
  name: string;
  monthly_price_cents: number;
  currency: "USD";
  transaction_commission_bps: 0;
  tagline: string;
  features: string[];
}

export interface SaasCheckoutResult {
  plan_id: "starter" | "growth" | "scale";
  session_id: string;
  checkout_url: string;
  livemode: boolean;
}

export async function fetchStripeReconciliation(
  businessId: string,
): Promise<StripeLedgerReconciliation> {
  return paymentsRequest<StripeLedgerReconciliation>(
    `/v1/businesses/${encodeURIComponent(businessId)}/payments/reconciliation`,
  );
}

export async function fetchSaasPlans(): Promise<SaasPlan[]> {
  const res = await fetch("/v1/billing/plans", { cache: "no-store" });
  if (!res.ok) throw new Error("Unable to load AMARKAL plans.");
  return (await res.json()) as SaasPlan[];
}

export async function startSaasSubscriptionCheckout(
  businessId: string,
  planId: "starter" | "growth" | "scale",
  customerEmail?: string | null,
): Promise<SaasCheckoutResult> {
  return paymentsRequest<SaasCheckoutResult>(
    `/v1/businesses/${encodeURIComponent(businessId)}/billing/checkout`,
    {
      method: "POST",
      body: JSON.stringify({
        plan_id: planId,
        customer_email: customerEmail || null,
      }),
    },
  );
}
