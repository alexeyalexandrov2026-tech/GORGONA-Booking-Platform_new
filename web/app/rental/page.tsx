"use client";
import { ManagementLayout } from "../../components/management-layout";
import { RentalScreen } from "../../components/rental";
import { canManageRental } from "../../lib/rental-contracts";
import "../rental.css";

export default function RentalPage() {
  return (
    <ManagementLayout>
      {({ salonId, me }) => {
        const member = me.memberships.find((m) => m.salon_id === salonId);
        // The server decides; this only avoids showing a screen every request refuses. Rental
        // rights belong to owners and managers and are not delegable (R8a decision 1).
        return canManageRental(member) ? (
          <RentalScreen key={`${me.user_id}:${salonId}`} businessId={salonId} />
        ) : (
          <div className="mgmt-empty">
            <h1>Rental</h1>
            <p>This area requires owner or manager access.</p>
          </div>
        );
      }}
    </ManagementLayout>
  );
}
