"use client";

import { ManagementLayout } from "../../components/management-layout";
import { PluginMarketplaceHub } from "../../components/plugin-marketplace-hub";
import "../us-release-v2.css";

export default function AppMarketplacePage() {
  return (
    <ManagementLayout>
      {({ salonId }) => <PluginMarketplaceHub businessId={salonId} />}
    </ManagementLayout>
  );
}
