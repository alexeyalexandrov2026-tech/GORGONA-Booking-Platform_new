"use client";
import { ManagementLayout } from "../../components/management-layout";
import { TransportScreen } from "../../components/transport";

export default function TransportPage() {
  return (
    <ManagementLayout>
      {({ salonId, me }) => {
        const member = me.memberships.find((m) => m.salon_id === salonId);
        // The server decides; this only avoids showing a screen every request refuses.
        const staff =
          member?.status === "active" &&
          !member.delegation &&
          ["owner", "manager"].includes(member.role);
        // M6b (ADR-0031): a carrier's dispatcher works here through its grant, only as granted.
        const granted = (right: string) =>
          member?.delegation?.permissions.some((p) => p === right) ?? false;
        return staff || granted("transport.read") ? (
          <TransportScreen
            key={`${me.user_id}:${salonId}`}
            businessId={salonId}
            rights={
              staff
                ? {
                    plan: true,
                    assign: true,
                    events: true,
                    fleet: true,
                    // Money routes refuse a branch-limited member (company-wide finance).
                    money: !member?.location_id,
                  }
                : {
                    plan: false,
                    assign: granted("transport.assign"),
                    events: granted("transport.events"),
                    fleet: false,
                    money: false,
                  }
            }
          />
        ) : (
          <div className="mgmt-empty">
            <h1>Transport</h1>
            <p>
              This area requires owner or manager access or a transport grant.
            </p>
          </div>
        );
      }}
    </ManagementLayout>
  );
}
