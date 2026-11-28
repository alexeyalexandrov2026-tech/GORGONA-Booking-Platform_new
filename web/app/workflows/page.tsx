"use client";

import { ManagementLayout } from "../../components/management-layout";
import { WorkflowBpmnHub } from "../../components/workflow-bpmn-hub";
import "../us-release-v2.css";

export default function WorkflowsPage() {
  return (
    <ManagementLayout>
      {({ salonId }) => <WorkflowBpmnHub businessId={salonId} />}
    </ManagementLayout>
  );
}
