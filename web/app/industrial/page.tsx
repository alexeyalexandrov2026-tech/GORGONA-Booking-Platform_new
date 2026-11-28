"use client";

import { ManagementLayout } from "../../components/management-layout";
import { IndustrialErpHub } from "../../components/industrial-erp-hub";
import "../us-release-v2.css";

export default function IndustrialErpPage() {
  return (
    <ManagementLayout>
      {({ salonId }) => <IndustrialErpHub key={salonId} businessId={salonId} />}
    </ManagementLayout>
  );
}
