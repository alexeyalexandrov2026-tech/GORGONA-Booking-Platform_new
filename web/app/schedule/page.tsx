"use client";
import { ManagementLayout } from "../../components/management-layout";
import { Schedule } from "../../components/schedule";
import "../workforce.css";

export default function SchedulePage() {
  return (
    <ManagementLayout>
      {({ salonId, me }) => {
        const member = me.memberships.find((m) => m.salon_id === salonId);
        // Owners and managers, also of one location; never a delegate. The server decides.
        const allowed =
          member?.status === "active" &&
          !member.delegation &&
          ["owner", "manager"].includes(member.role);
        return allowed ? (
          <Schedule
            key={`${me.user_id}:${salonId}`}
            businessId={salonId}
            actorId={me.user_id}
            companyWide={member.location_id === null}
          />
        ) : (
          <section className="mgmt-empty-state">
            <h1>Schedule</h1>
            <p>This area requires owner or manager access.</p>
          </section>
        );
      }}
    </ManagementLayout>
  );
}
