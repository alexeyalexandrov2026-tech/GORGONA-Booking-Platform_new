"use client";

import { ManagementLayout } from "../../components/management-layout";
import { WorkspaceStudio } from "../../components/workspace-studio";

export default function WorkspaceStudioPage() {
  return (
    <ManagementLayout>
      {({ salonId }) => <WorkspaceStudio key={salonId} businessId={salonId} />}
    </ManagementLayout>
  );
}
