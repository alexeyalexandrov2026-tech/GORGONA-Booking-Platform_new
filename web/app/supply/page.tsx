"use client";

import { ManagementLayout } from "../../components/management-layout";
import { SupplyScreen } from "../../components/supply";
import {
  canManageSupply,
  canReadSupply,
  canWorkSupply,
} from "../../lib/supply-contracts";
import "../supply.css";

export default function SupplyPage() {
  return (
    <ManagementLayout>
      {({ salonId, me }) => {
        const member = me.memberships.find((m) => m.salon_id === salonId);
        return canReadSupply(member) ? (
          <SupplyScreen
            key={`${me.user_id}:${salonId}`}
            businessId={salonId}
            assignedLocationId={member?.location_id ?? null}
            canWork={canWorkSupply(member)}
            canManage={canManageSupply(member)}
          />
        ) : (
          <div className="mgmt-empty">
            <h1>Supply Chain, 3PL WMS &amp; Manufacturing</h1>
            <p>This area requires active staff access.</p>
          </div>
        );
      }}
    </ManagementLayout>
  );
}
