"use client";

import { ManagementLayout } from "../../components/management-layout";
import { EnterpriseScreen } from "../../components/enterprise";
import {
  canManageEnterprise,
  canReadEnterprise,
} from "../../lib/enterprise-contracts";
import "../enterprise.css";

export default function EnterprisePage() {
  return (
    <ManagementLayout>
      {({ salonId, me }) => {
        const member = me.memberships.find((m) => m.salon_id === salonId);
        return canReadEnterprise(member) ? (
          <EnterpriseScreen
            key={`${me.user_id}:${salonId}`}
            businessId={salonId}
            canManage={canManageEnterprise(member)}
          />
        ) : (
          <div className="mgmt-empty">
            <h1>Enterprise SSO, Lifecycle &amp; Group Reporting</h1>
            <p>This area requires active staff access.</p>
          </div>
        );
      }}
    </ManagementLayout>
  );
}
