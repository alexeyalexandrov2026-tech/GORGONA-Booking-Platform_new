"use client";

import { ManagementLayout } from "../../components/management-layout";
import { OmnichannelInbox } from "../../components/omnichannel-inbox";
import "../us-release-v2.css";

export default function OmnichannelInboxPage() {
  return (
    <ManagementLayout>
      {({ salonId }) => <OmnichannelInbox key={salonId} businessId={salonId} />}
    </ManagementLayout>
  );
}
