"use client";

import { ManagementLayout } from "../../components/management-layout";
import { GlobalFinanceHub } from "../../components/global-finance-hub";
import "../us-release-v2.css";

export default function GlobalFinancePage() {
  return (
    <ManagementLayout>
      {({ salonId }) => <GlobalFinanceHub key={salonId} businessId={salonId} />}
    </ManagementLayout>
  );
}
