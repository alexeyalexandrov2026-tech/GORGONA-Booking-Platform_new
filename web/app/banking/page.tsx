"use client";

import { BankFeedsHub } from "../../components/bank-feeds-hub";
import { ManagementLayout } from "../../components/management-layout";
import "../us-release-v2.css";

export default function BankingPage() {
  return (
    <ManagementLayout>
      {({ salonId }) => <BankFeedsHub businessId={salonId} />}
    </ManagementLayout>
  );
}
