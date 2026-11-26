"use client";

import { AppHub } from "../../components/app-hub";
import { ManagementLayout } from "../../components/management-layout";

export default function IntegrationsPage() {
  return (
    <ManagementLayout>
      {({ salonId }) => <AppHub key={salonId} businessId={salonId} />}
    </ManagementLayout>
  );
}
