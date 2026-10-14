"use client";
import { ManagementLayout } from "../../components/management-layout";
import { StockDocuments } from "../../components/stock-documents";
import "../inventory.css";

export default function StockDocumentsPage() {
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
          <StockDocuments
            key={`${me.user_id}:${salonId}`}
            actorId={me.user_id}
            businessId={salonId}
            finance={member.location_id === null}
          />
        ) : (
          <div className="mgmt-empty">
            <h1>Stock documents</h1>
            <p>This area requires owner or manager access.</p>
          </div>
        );
      }}
    </ManagementLayout>
  );
}
