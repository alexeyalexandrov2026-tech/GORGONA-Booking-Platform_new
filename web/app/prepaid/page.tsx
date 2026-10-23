"use client";
import { ManagementLayout } from "../../components/management-layout";
import { PrepaidScreen } from "../../components/prepaid-screen";

export default function PrepaidPage() {
  return (
    <ManagementLayout>
      {({ salonId, me }) => {
        const member = me.memberships.find((m) => m.salon_id === salonId);
        // The server decides; this only avoids showing a screen every request refuses.
        const allowed =
          member?.status === "active" &&
          !member.delegation &&
          ["owner", "manager"].includes(member.role);
        return allowed ? (
          <PrepaidScreen key={`${me.user_id}:${salonId}`} salonId={salonId} />
        ) : (
          <div className="mgmt-empty">
            <h1>Prepaid balances</h1>
            <p>This area requires owner or manager access.</p>
          </div>
        );
      }}
    </ManagementLayout>
  );
}
