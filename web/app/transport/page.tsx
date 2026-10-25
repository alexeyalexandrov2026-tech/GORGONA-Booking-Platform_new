"use client";
import { ManagementLayout } from "../../components/management-layout";
import { TransportScreen } from "../../components/transport";

export default function TransportPage() {
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
          <TransportScreen
            key={`${me.user_id}:${salonId}`}
            businessId={salonId}
          />
        ) : (
          <div className="mgmt-empty">
            <h1>Transport</h1>
            <p>This area requires owner or manager access.</p>
          </div>
        );
      }}
    </ManagementLayout>
  );
}
