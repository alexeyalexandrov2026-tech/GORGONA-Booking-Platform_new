import { managementFetch } from "./management-api";

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
  return (await managementFetch(
    `/v1/businesses/${businessId}/payments/sessions`,
  )) as PaymentSession[];
}

export async function createCheckoutSession(
  businessId: string,
  input: CreateCheckoutSessionInput,
): Promise<PaymentSession> {
  return (await managementFetch(
    `/v1/businesses/${businessId}/payments/checkout-sessions`,
    {
      method: "POST",
      body: JSON.stringify(input),
    },
  )) as PaymentSession;
}

export async function syncPaymentSession(
  businessId: string,
  sessionId: string,
): Promise<PaymentSession> {
  return (await managementFetch(
    `/v1/businesses/${businessId}/payments/sessions/${sessionId}/sync`,
    { method: "POST" },
  )) as PaymentSession;
}

export async function refundPaymentSession(
  businessId: string,
  sessionId: string,
): Promise<PaymentSession> {
  return (await managementFetch(
    `/v1/businesses/${businessId}/payments/sessions/${sessionId}/refund`,
    {
      method: "POST",
      body: JSON.stringify({ reason: "requested_by_customer" }),
    },
  )) as PaymentSession;
}
