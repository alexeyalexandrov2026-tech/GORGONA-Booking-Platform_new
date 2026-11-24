"use client";

import { ManagementLayout } from "../../components/management-layout";
import { ProjectsScreen } from "../../components/projects";
import {
  canBillProjects,
  canManageProjects,
  canReadProjects,
  canWorkProjects,
} from "../../lib/projects-contracts";
import "../projects.css";

export default function ProjectsPage() {
  return (
    <ManagementLayout>
      {({ salonId, me }) => {
        const member = me.memberships.find((m) => m.salon_id === salonId);
        return canReadProjects(member) ? (
          <ProjectsScreen
            key={`${me.user_id}:${salonId}`}
            businessId={salonId}
            assignedLocationId={member?.location_id ?? null}
            canWork={canWorkProjects(member)}
            canManage={canManageProjects(member)}
            canBill={canBillProjects(member)}
          />
        ) : (
          <div className="mgmt-empty">
            <h1>Projects &amp; Legal Matters</h1>
            <p>This area requires active staff access.</p>
          </div>
        );
      }}
    </ManagementLayout>
  );
}
