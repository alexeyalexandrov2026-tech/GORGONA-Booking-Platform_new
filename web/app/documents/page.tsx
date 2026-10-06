"use client";

import { ManagementLayout } from "../../components/management-layout";
import { Documents } from "../../components/documents";

export default function DocumentsPage() {
  return (
    <ManagementLayout>
      {({ salonId, me }) => {
        const member = me.memberships.find((m) => m.salon_id === salonId);
        const allowed =
          member?.status === "active" &&
          member.location_id === null &&
          !member.delegation &&
          ["owner", "manager"].includes(member.role);
        return allowed ? (
          <Documents key={salonId} businessId={salonId} />
        ) : (
          <div className="mgmt-empty">
            <h1>Documents</h1>
            <p>This area requires company-wide owner or manager access.</p>
          </div>
        );
      }}
    </ManagementLayout>
  );
}
