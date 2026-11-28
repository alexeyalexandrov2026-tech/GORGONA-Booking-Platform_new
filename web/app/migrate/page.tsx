"use client";

import { ManagementLayout } from "../../components/management-layout";
import { MigrationSandboxHub } from "../../components/migration-sandbox-hub";
import "../us-release-v2.css";

export default function MigratePage() {
  return (
    <ManagementLayout>
      {({ salonId }) => <MigrationSandboxHub businessId={salonId} />}
    </ManagementLayout>
  );
}
