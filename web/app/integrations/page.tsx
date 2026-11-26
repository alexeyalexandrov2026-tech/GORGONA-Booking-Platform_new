"use client";

import { AppHub } from "../../components/app-hub";
import { ManagementLayout } from "../../components/management-layout";
import { StripePaymentsPanel } from "../../components/stripe-payments-panel";

export default function IntegrationsPage() {
  return (
    <ManagementLayout>
      {({ salonId }) => (
        <>
          <AppHub key={salonId} businessId={salonId} />
          <StripePaymentsPanel key={`stripe-${salonId}`} businessId={salonId} />
        </>
      )}
    </ManagementLayout>
  );
}
