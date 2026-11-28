"use client";

import { AbacAccessControlHub } from "../../components/abac-access-control-hub";
import { ManagementLayout } from "../../components/management-layout";
import "../us-release-v2.css";

export default function AccessControlPage() {
  return (
    <ManagementLayout>
      {({ salonId }) => <AbacAccessControlHub businessId={salonId} />}
    </ManagementLayout>
  );
}
