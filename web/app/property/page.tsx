"use client";
import { ManagementLayout } from "../../components/management-layout";
import { PropertyScreen } from "../../components/property";
import {
  canManageProperty,
  canReadProperty,
} from "../../lib/property-contracts";
import "../property.css";

export default function PropertyPage() {
  return (
    <ManagementLayout>
      {({ salonId, me }) => {
        const member = me.memberships.find((m) => m.salon_id === salonId);
        // The server decides; this only avoids showing what every request refuses. Branch
        // members read their branch; company-wide owners and managers also write and see history.
        return canReadProperty(member) ? (
          <PropertyScreen
            key={`${me.user_id}:${salonId}`}
            businessId={salonId}
            canManage={canManageProperty(member)}
          />
        ) : (
          <div className="mgmt-empty">
            <h1>Property</h1>
            <p>This area requires owner or manager access.</p>
          </div>
        );
      }}
    </ManagementLayout>
  );
}
