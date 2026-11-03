"use client";
import { ManagementLayout } from "../../components/management-layout";
import { ConstructionScreen } from "../../components/construction";
import "../construction.css";

export default function ConstructionPage() {
  return (
    <ManagementLayout>
      {({ salonId, me }) => {
        const member = me.memberships.find((m) => m.salon_id === salonId);
        // The server decides; this only avoids showing a screen every request refuses. Construction
        // rights belong to owners and managers and are not delegable (ADR-0035).
        const staff =
          member?.status === "active" &&
          !member.delegation &&
          ["owner", "manager"].includes(member.role);
        return staff ? (
          <ConstructionScreen
            key={`${me.user_id}:${salonId}`}
            businessId={salonId}
          />
        ) : (
          <div className="mgmt-empty">
            <h1>Construction</h1>
            <p>This area requires owner or manager access.</p>
          </div>
        );
      }}
    </ManagementLayout>
  );
}
