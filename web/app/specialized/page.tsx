"use client";

import { ManagementLayout } from "../../components/management-layout";
import { SpecializedScreen } from "../../components/specialized";
import {
  canManageSpecialized,
  canReadSpecialized,
} from "../../lib/specialized-contracts";
import "../specialized.css";

export default function SpecializedPage() {
  return (
    <ManagementLayout>
      {({ salonId, me }) => {
        const member = me.memberships.find((m) => m.salon_id === salonId);
        return canReadSpecialized(member) ? (
          <SpecializedScreen
            key={`${me.user_id}:${salonId}`}
            businessId={salonId}
            canManage={canManageSpecialized(member)}
          />
        ) : (
          <div className="mgmt-empty">
            <h1>Specialized Industry Operations</h1>
            <p>This area requires active staff access.</p>
          </div>
        );
      }}
    </ManagementLayout>
  );
}
