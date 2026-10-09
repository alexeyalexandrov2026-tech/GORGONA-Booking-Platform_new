"use client";
import { ManagementLayout } from "../../components/management-layout";
import { ProviderAdmission } from "../../components/provider-admission";
import "./provider-admission.css";
export default function ProviderAdmissionPage() {
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
          <ProviderAdmission
            key={`${me.user_id}:${salonId}`}
            businessId={salonId}
            actorId={me.user_id}
          />
        ) : (
          <div className="mgmt-empty">
            <h1>Provider admission</h1>
            <p>This area requires company-wide owner or manager access.</p>
          </div>
        );
      }}
    </ManagementLayout>
  );
}
