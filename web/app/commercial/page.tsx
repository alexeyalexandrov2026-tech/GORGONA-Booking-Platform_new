"use client";

import { CommercialHub } from "../../components/commercial-hub";
import { ManagementLayout } from "../../components/management-layout";

export default function CommercialPage() {
  return (
    <ManagementLayout>
      {({ salonId }) => <CommercialHub key={salonId} businessId={salonId} />}
    </ManagementLayout>
  );
}
