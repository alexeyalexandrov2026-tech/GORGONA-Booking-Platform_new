"use client";

import { ManagementLayout } from "../../components/management-layout";
import { RestaurantScreen } from "../../components/restaurant";
import {
  canManageRestaurant,
  canOperateKitchen,
  canReadRestaurant,
  canRunCompanyFinance,
  canRunService,
} from "../../lib/restaurant-contracts";
import "../restaurant.css";

export default function RestaurantPage() {
  return (
    <ManagementLayout>
      {({ salonId, me }) => {
        const member = me.memberships.find((m) => m.salon_id === salonId);
        return canReadRestaurant(member) ? (
          <RestaurantScreen
            key={`${me.user_id}:${salonId}`}
            businessId={salonId}
            assignedLocationId={member?.location_id ?? null}
            canManage={canManageRestaurant(member)}
            canService={canRunService(member)}
            canKitchen={canOperateKitchen(member)}
            canCompanyFinance={canRunCompanyFinance(member)}
          />
        ) : (
          <div className="mgmt-empty">
            <h1>Restaurant</h1>
            <p>This area requires active restaurant staff access.</p>
          </div>
        );
      }}
    </ManagementLayout>
  );
}
