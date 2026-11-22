"use client";

import { ManagementLayout } from "../../components/management-layout";
import { MarketScreen } from "../../components/market";
import { canManageMarket, canReadMarket } from "../../lib/market-contracts";
import "../market.css";

export default function MarketplacePage() {
  return (
    <ManagementLayout>
      {({ salonId, me }) => {
        const member = me.memberships.find((m) => m.salon_id === salonId);
        return canReadMarket(member) ? (
          <MarketScreen
            key={`${me.user_id}:${salonId}`}
            businessId={salonId}
            assignedLocationId={member?.location_id ?? null}
            canManage={canManageMarket(member)}
          />
        ) : (
          <div className="mgmt-empty">
            <h1>Storefronts &amp; Client-Operated Marketplaces</h1>
            <p>This area requires active staff access.</p>
          </div>
        );
      }}
    </ManagementLayout>
  );
}
