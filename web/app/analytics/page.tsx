"use client";

import { AnalyticsBiHub } from "../../components/analytics-bi-hub";
import { ManagementLayout } from "../../components/management-layout";
import "../us-release-v2.css";

export default function AnalyticsBiPage() {
  return (
    <ManagementLayout>
      {({ salonId }) => <AnalyticsBiHub businessId={salonId} />}
    </ManagementLayout>
  );
}
