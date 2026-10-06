"use client";

import { ManagementLayout } from "../../components/management-layout";
import { Reservations } from "../../components/reservations";

export default function ReservationsPage() {
  return (
    <ManagementLayout>
      {({ salonId, me }) => {
        const member = me.memberships.find((m) => m.salon_id === salonId);
        // Staff management: owners and managers, also of one branch; never delegates.
        const allowed =
          member?.status === "active" &&
          !member.delegation &&
          ["owner", "manager"].includes(member.role);
        return allowed ? (
          <Reservations key={salonId} businessId={salonId} />
        ) : (
          <div className="mgmt-empty">
            <h1>Resource reservations</h1>
            <p>This area requires owner or manager access.</p>
          </div>
        );
      }}
    </ManagementLayout>
  );
}
