"use client";
import { ManagementLayout } from "../../components/management-layout";
import { MyShifts } from "../../components/my-shifts";
import "../workforce.css";

export default function MyShiftsPage() {
  return (
    <ManagementLayout>
      {({ salonId, me }) => {
        const member = me.memberships.find((m) => m.salon_id === salonId);
        // Every own member of the business; access under another company's grant has none.
        const allowed = member?.status === "active" && !member.delegation;
        return allowed ? (
          <MyShifts
            key={`${me.user_id}:${salonId}`}
            businessId={salonId}
            actorId={me.user_id}
          />
        ) : (
          <section className="mgmt-empty-state">
            <h1>My shifts</h1>
            <p>Shifts are available only to members of this business.</p>
          </section>
        );
      }}
    </ManagementLayout>
  );
}
