"use client";
import { ManagementLayout } from "../../components/management-layout";
import { Timesheets } from "../../components/timesheets";
import "../workforce.css";

export default function TimesheetsPage() {
  return (
    <ManagementLayout>
      {({ salonId, me }) => {
        const member = me.memberships.find((m) => m.salon_id === salonId);
        // Every own member of the business; access under another company's grant has none.
        const allowed = member?.status === "active" && !member.delegation;
        return allowed ? (
          <Timesheets
            key={`${me.user_id}:${salonId}`}
            businessId={salonId}
            actorId={me.user_id}
            role={member.role}
          />
        ) : (
          <section className="mgmt-empty-state">
            <h1>Timesheets</h1>
            <p>Timesheets are available only to members of this business.</p>
          </section>
        );
      }}
    </ManagementLayout>
  );
}
