"use client";
import { ManagementLayout } from "../../components/management-layout";
import { FinancialWorkspace } from "../../components/financial-workspace";
import "./finance.css";

export default function FinancePage() {
  return (
    <ManagementLayout>
      {({ salonId, me }) => {
        const member = me.memberships.find((x) => x.salon_id === salonId);
        const allowed =
          member?.status === "active" &&
          member.location_id === null &&
          !member.delegation &&
          ["owner", "manager"].includes(member.role);
        return allowed ? (
          <FinancialWorkspace
            key={`${me.user_id}:${salonId}`}
            businessId={salonId}
            actorId={me.user_id}
          />
        ) : (
          <section className="mgmt-empty">
            <h1>Financial documents</h1>
            <p>This area requires company-wide owner or manager access.</p>
          </section>
        );
      }}
    </ManagementLayout>
  );
}
