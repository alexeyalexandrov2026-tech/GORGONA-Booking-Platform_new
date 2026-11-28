"use client";

import { HoldingConsolidationHub } from "../../components/holding-consolidation-hub";
import { ManagementLayout } from "../../components/management-layout";
import "../us-release-v2.css";

export default function HoldingPage() {
  return (
    <ManagementLayout>
      {({ salonId }) => <HoldingConsolidationHub businessId={salonId} />}
    </ManagementLayout>
  );
}
