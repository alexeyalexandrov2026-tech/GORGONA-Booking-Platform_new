# K1a — architecture conformance and reuse

Source `7d25aa2d72874271a62e363817e0624fb502497c`. [Original K proposal](../../PACKAGE_K_PLAN_2026-10-15.md),
[planning inspection](../2026-10-15-package-k-plan/ARCHITECTURE_REUSE.md), [validation](VALIDATION.md).

The actual new flow is `raw bytes + signature + trusted decoder policy -> official
SDK signature check -> strict JSON -> minimal frozen snapshot facts`. It has no I/O,
database context, admitted connection, operation-state transition or financial caller.
An SDK import is not an integration with an account. K1a never constructs a StripeClient
or supplies an API key. The network-denial unit case verifies the parsing call stays offline.

Reuse: the existing `business.contracts.Strict/Versioned` supplies frozen, extra-forbidden
normalized models and strict schema versions. Existing `DomainError` carries only fixed
safe refusal/configuration messages. The official Stripe WebhookSignature handles MAC
comparison; the adapter adds bounded header grammar and a symmetric integer-second
300-second freshness window. The original gate runner is reused with separate fresh
clusters and structured required-check failures. No general event framework was added.

The decoder supports 11 explicitly listed snapshot event kinds for PaymentIntent,
Charge and Refund. JSON extras are accepted at the provider envelope for forward-safe
decoding of the selected fields, then discarded. Raw bytes are verified before any
JSON parse. Duplicate keys anywhere, non-finite numbers and non-UTF-8 bodies are refused.
No money floats/coercions are accepted. A legal integer snapshot does not certify a
currency's provider availability, a valid payment-state transition or a permissible posting.

Delivery SHA-256 identifies exact received bytes. The facts hash identifies selected
normalized facts of that event, including ID/type/account/version/resource. It deliberately
does not deduplicate charge and PaymentIntent events into one money operation. K2 needs
that separately reviewed canonical operation identity; K1b needs durable event uniqueness.

Dependency adoption evidence: public [official SDK](https://github.com/stripe/stripe-python),
[MIT license](https://github.com/stripe/stripe-python/blob/v16.0.0/LICENSE),
[signature implementation](https://github.com/stripe/stripe-python/blob/v16.0.0/stripe/_webhook.py)
and PyPI metadata were inspected. Version16.0.0 declares Python>=3.9 and was executed on
this checkout's Python3.14.6; existing requests/typing-extensions versions were retained.
No optional async extra, CLI or new HTTP stack was installed. The wheel is hash-locked.

[Stripe webhooks](https://docs.stripe.com/webhooks) require original bytes for signatures;
deliveries can repeat/reorder. [Event](https://docs.stripe.com/api/events/object),
[PaymentIntent](https://docs.stripe.com/api/payment_intents/object),
[Charge](https://docs.stripe.com/api/charges/object), [Refund](https://docs.stripe.com/api/refunds/object)
inform the selected snapshot fields. These checks are public documentation research,
not authenticated provider access or test-mode admission. SDK API-version candidate is
2026-09-30.endive; actual merchant/event-format pinning remains a K0/K1b gate.

Preserved: all existing G/H manual-attestation behavior, HTTP routes, RLS/roles,
admission all-false capabilities, readiness and migrations0001–0043; web/AI/infra/workflows
and other package sources are unchanged. No new branch is published. Independent
security/integration review remains NOT TESTED before exposing or accepting the ingress.
