"use client";
import { ManagementLayout } from "../../components/management-layout";
import { Materials } from "../../components/materials";
import "../inventory.css";

export default function MaterialsPage() {
  return (
    <ManagementLayout>
      {({ salonId, me }) => {
        const member = me.memberships.find((m) => m.salon_id === salonId);
        // The server decides; this only avoids showing a screen every request refuses.
        const allowed =
          member?.status === "active" &&
          !member.delegation &&
          ["owner", "manager"].includes(member.role);
        const companyWide = allowed && member.location_id === null;
        return allowed ? (
          <Materials
            key={`${me.user_id}:${salonId}`}
            actorId={me.user_id}
            businessId={salonId}
            companyWide={companyWide}
            finance={companyWide}
          />
        ) : (
          <div className="mgmt-empty">
            <h1>Materials</h1>
            <p>This area requires owner or manager access.</p>
          </div>
        );
      }}
    </ManagementLayout>
  );
}
