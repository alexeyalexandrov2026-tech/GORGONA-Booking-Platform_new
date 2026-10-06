"use client";
import { ManagementLayout } from "../../components/management-layout";
import { Ledger } from "../../components/ledger";

export default function LedgerPage() {
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
          <Ledger
            key={`${me.user_id}:${salonId}`}
            actorId={me.user_id}
            businessId={salonId}
          />
        ) : (
          <div className="mgmt-empty">
            <h1>Ledger</h1>
            <p>This area requires company-wide owner or manager access.</p>
          </div>
        );
      }}
    </ManagementLayout>
  );
}
