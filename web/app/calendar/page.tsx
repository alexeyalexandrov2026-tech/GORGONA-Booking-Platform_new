"use client";

import React, { useEffect, useState, useCallback } from "react";
import { ManagementLayout } from "../../components/management-layout";
import { LocationFilter } from "../../components/location-filter";
import {
  businessDateTime,
  businessTimeToInstant,
  shiftDate,
} from "../../lib/business-time";
import {
  BookingSummary,
  cancelBooking,
  createStaffBooking,
  fetchBookings,
  fetchWorkspace,
  SalonSettings,
  fetchServices,
  fetchStaff,
  formatDate,
  formatPrice,
  formatTime,
  rescheduleBooking,
  ServiceView,
  StaffView,
} from "../../lib/management-api";

export default function CalendarPage() {
  return (
    <ManagementLayout>
      {({ salonId, refresh: triggerRefresh }) => (
        <CalendarContent
          key={salonId}
          salonId={salonId}
          onRefresh={triggerRefresh}
        />
      )}
    </ManagementLayout>
  );
}

function CalendarContent({
  salonId,
  onRefresh,
}: {
  salonId: string;
  onRefresh: () => void;
}) {
  const [selectedDate, setSelectedDate] = useState("");
  const [locations, setLocations] = useState<SalonSettings["locations"]>([]);
  const [selectedLocationId, setSelectedLocationId] = useState("");
  const [selectedStaffFilter, setSelectedStaffFilter] = useState("all");
  const [selectedStatusFilter, setSelectedStatusFilter] = useState("all");

  const [bookings, setBookings] = useState<BookingSummary[]>([]);
  const [staffList, setStaffList] = useState<StaffView[]>([]);
  const [servicesList, setServicesList] = useState<ServiceView[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  // Modals
  const [inspectBooking, setInspectBooking] = useState<BookingSummary | null>(
    null,
  );
  const [rescheduleTarget, setRescheduleTarget] =
    useState<BookingSummary | null>(null);
  const [rescheduleDate, setRescheduleDate] = useState("");
  const [rescheduleTime, setRescheduleTime] = useState("10:00");
  const [rescheduleStaffId, setRescheduleStaffId] = useState("");
  const [isRescheduling, setIsRescheduling] = useState(false);
  const [rescheduleError, setRescheduleError] = useState<string | null>(null);

  const [cancelTarget, setCancelTarget] = useState<BookingSummary | null>(null);
  const [cancelReason, setCancelReason] = useState(
    "Customer requested cancellation",
  );
  const [isCancelling, setIsCancelling] = useState(false);
  const [cancelError, setCancelError] = useState<string | null>(null);

  // New Booking Modal
  const [showNewBookingModal, setShowNewBookingModal] = useState(false);
  const [newStaffId, setNewStaffId] = useState("");
  const [newVariantId, setNewVariantId] = useState("");
  const [newBookingDate, setNewBookingDate] = useState("");
  const [newBookingTime, setNewBookingTime] = useState("10:00");
  const [newClientName, setNewClientName] = useState("");
  const [newClientEmail, setNewClientEmail] = useState("");
  const [newClientPhone, setNewClientPhone] = useState("");
  const [isCreating, setIsCreating] = useState(false);
  const [newBookingError, setNewBookingError] = useState<string | null>(null);

  useEffect(() => {
    let isSubscribed = true;
    Promise.all([
      fetchWorkspace(salonId),
      fetchStaff(salonId),
      fetchServices(salonId),
    ])
      .then(async ([settings, staff, services]) => {
        const location =
          settings.locations.find((item) => item.id === selectedLocationId) ??
          settings.locations[0];
        if (!location)
          throw new Error("Configure a business location and timezone first.");
        const day =
          selectedDate || businessDateTime(new Date(), location.timezone).date;
        const bList = await fetchBookings(salonId, {
          localDay: day,
          locationId: location.id,
          resourceId:
            selectedStaffFilter !== "all" ? selectedStaffFilter : undefined,
          status:
            selectedStatusFilter !== "all" ? selectedStatusFilter : undefined,
        });
        return {
          bList,
          sList: staff.filter(
            (item) => item.location_id === location.id && item.is_active,
          ),
          vList: services,
          settings,
          location,
          day,
        };
      })
      .then(({ bList, sList, vList, settings, location, day }) => {
        if (!isSubscribed) return;
        setLocations(settings.locations);
        setSelectedLocationId(location.id);
        setSelectedDate(day);
        setNewBookingDate(
          (current) =>
            current || businessDateTime(new Date(), location.timezone).date,
        );
        setBookings(bList);
        setStaffList(sList);
        setServicesList(
          vList.filter(
            (v) => v.is_bookable && v.booking_duration_minutes !== null,
          ),
        );
        setNewStaffId((current) =>
          sList.some((item) => item.id === current)
            ? current
            : (sList[0]?.id ?? ""),
        );
        const bookable = vList.filter(
          (v) => v.is_bookable && v.booking_duration_minutes !== null,
        );
        setNewVariantId((current) =>
          bookable.some((item) => item.id === current)
            ? current
            : (bookable[0]?.id ?? ""),
        );
        setError(null);
      })
      .catch((err: unknown) => {
        if (!isSubscribed) return;
        setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        if (isSubscribed) setLoading(false);
      });

    return () => {
      isSubscribed = false;
    };
  }, [
    salonId,
    selectedLocationId,
    selectedDate,
    selectedStaffFilter,
    selectedStatusFilter,
    refreshKey,
  ]);

  const loadCalendarData = useCallback(() => {
    setLoading(true);
    setRefreshKey((k) => k + 1);
  }, []);

  const handleDayShift = (days: number) => {
    if (!selectedDate) return;
    setSelectedDate(shiftDate(selectedDate, days));
  };

  const handleToday = () => {
    const location = locations.find((item) => item.id === selectedLocationId);
    if (location)
      setSelectedDate(businessDateTime(new Date(), location.timezone).date);
  };

  const handleOpenReschedule = (b: BookingSummary) => {
    setRescheduleTarget(b);
    setRescheduleStaffId(b.resource_id);
    const local = businessDateTime(b.starts_at, b.location_timezone);
    setRescheduleDate(local.date);
    setRescheduleTime(local.time);
    setRescheduleError(null);
  };

  const handleExecuteReschedule = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!rescheduleTarget) return;
    setIsRescheduling(true);
    setRescheduleError(null);
    try {
      const newStartsAt = businessTimeToInstant(
        rescheduleDate,
        rescheduleTime,
        rescheduleTarget.location_timezone,
      );
      await rescheduleBooking(salonId, rescheduleTarget.booking_id, {
        new_starts_at: newStartsAt,
        new_resource_id:
          rescheduleStaffId !== rescheduleTarget.resource_id
            ? rescheduleStaffId
            : undefined,
      });
      setRescheduleTarget(null);
      setInspectBooking(null);
      setToastMessage("Appointment rescheduled successfully!");
      loadCalendarData();
      onRefresh();
    } catch (err: unknown) {
      setRescheduleError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsRescheduling(false);
    }
  };

  const handleOpenCancel = (b: BookingSummary) => {
    setCancelTarget(b);
    setCancelError(null);
  };

  const handleExecuteCancel = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!cancelTarget) return;
    setIsCancelling(true);
    setCancelError(null);
    try {
      await cancelBooking(salonId, cancelTarget.booking_id, cancelReason);
      setCancelTarget(null);
      setInspectBooking(null);
      setToastMessage("Appointment cancelled successfully.");
      loadCalendarData();
      onRefresh();
    } catch (err: unknown) {
      setCancelError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsCancelling(false);
    }
  };

  const handleCreateNewBooking = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newStaffId || !newVariantId) return;
    setIsCreating(true);
    setNewBookingError(null);

    const locationId =
      staffList.find((s) => s.id === newStaffId)?.location_id ||
      bookings[0]?.location_id;

    if (!locationId) {
      setNewBookingError("No location available for this staff member");
      setIsCreating(false);
      return;
    }

    try {
      const timezone = locations.find(
        (item) => item.id === locationId,
      )?.timezone;
      if (!timezone)
        throw new Error("Configure the staff location timezone first.");
      const startsAt = businessTimeToInstant(
        newBookingDate,
        newBookingTime,
        timezone,
      );
      await createStaffBooking(salonId, {
        location_id: locationId,
        resource_id: newStaffId,
        variant_id: newVariantId,
        starts_at: startsAt,
        customer_name: newClientName.trim(),
        customer_email: newClientEmail.trim(),
        customer_phone: newClientPhone.trim(),
      });
      setShowNewBookingModal(false);
      setToastMessage("New appointment created successfully!");
      setNewClientName("");
      setNewClientEmail("");
      setNewClientPhone("");
      loadCalendarData();
      onRefresh();
    } catch (err: unknown) {
      setNewBookingError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsCreating(false);
    }
  };

  return (
    <div>
      {toastMessage && (
        <div className="hold-note" style={{ marginBottom: "20px" }}>
          <strong>Notice:</strong> {toastMessage}
        </div>
      )}

      <div className="mgmt-section-header">
        <div>
          <h2>Salon Calendar</h2>
          <p className="muted">
            Live appointment schedule and capacity management
          </p>
        </div>
        <button
          type="button"
          disabled={loading}
          onClick={() => {
            setNewBookingDate(selectedDate);
            setShowNewBookingModal(true);
          }}
        >
          + Book Appointment
        </button>
      </div>

      <div className="mgmt-filter-bar">
        <LocationFilter
          locations={locations}
          value={selectedLocationId}
          onChange={(value) => {
            setSelectedLocationId(value);
            setSelectedStaffFilter("all");
            setNewStaffId("");
            setShowNewBookingModal(false);
            setRescheduleTarget(null);
            setInspectBooking(null);
            setLoading(true);
          }}
        />
        <div className="mgmt-filter-group">
          <button
            type="button"
            className="secondary mgmt-btn-small"
            onClick={() => handleDayShift(-1)}
          >
            &larr; Prev
          </button>
          <button
            type="button"
            className="secondary mgmt-btn-small"
            onClick={handleToday}
          >
            Today
          </button>
          <button
            type="button"
            className="secondary mgmt-btn-small"
            onClick={() => handleDayShift(1)}
          >
            Next &rarr;
          </button>
          <input
            type="date"
            value={selectedDate}
            onChange={(e) => setSelectedDate(e.target.value)}
            aria-label="Selected Calendar Date"
          />
        </div>

        <div className="mgmt-filter-group">
          <label htmlFor="staff-filter">Staff:</label>
          <select
            id="staff-filter"
            value={selectedStaffFilter}
            onChange={(e) => setSelectedStaffFilter(e.target.value)}
          >
            <option value="all">All Staff</option>
            {staffList.map((s) => (
              <option key={s.id} value={s.id}>
                {s.display_name}
              </option>
            ))}
          </select>
        </div>

        <div className="mgmt-filter-group">
          <label htmlFor="status-filter">Status:</label>
          <select
            id="status-filter"
            value={selectedStatusFilter}
            onChange={(e) => setSelectedStatusFilter(e.target.value)}
          >
            <option value="all">All Statuses</option>
            <option value="CONFIRMED">Confirmed</option>
            <option value="HOLD">Hold</option>
            <option value="CANCELLED">Cancelled</option>
          </select>
        </div>
      </div>

      {loading ? (
        <p className="muted">Loading calendar appointments...</p>
      ) : error ? (
        <div className="mgmt-error-banner" role="alert">
          <h3>Error loading calendar</h3>
          <p>{error}</p>
          <button type="button" onClick={loadCalendarData}>
            Retry
          </button>
        </div>
      ) : bookings.length === 0 ? (
        <div className="mgmt-empty-state">
          <h3>No Appointments Scheduled</h3>
          <p className="muted">
            There are no appointments on {selectedDate} matching your filters.
          </p>
          <button type="button" onClick={() => setShowNewBookingModal(true)}>
            Schedule Appointment
          </button>
        </div>
      ) : (
        <div className="mgmt-table-container">
          <table className="mgmt-table" aria-label="Calendar Appointments">
            <thead>
              <tr>
                <th scope="col">Time</th>
                <th scope="col">Client</th>
                <th scope="col">Service</th>
                <th scope="col">Staff</th>
                <th scope="col">Total</th>
                <th scope="col">Status</th>
                <th scope="col">Actions</th>
              </tr>
            </thead>
            <tbody>
              {bookings.map((b) => (
                <tr key={b.booking_id}>
                  <td>
                    <strong>
                      {formatTime(b.starts_at, b.location_timezone)}
                    </strong>{" "}
                    - {formatTime(b.ends_at, b.location_timezone)}
                  </td>
                  <td>
                    <div>{b.customer_name || "Guest Client"}</div>
                    <small className="muted">
                      {b.customer_phone || b.customer_email || "No contact"}
                    </small>
                  </td>
                  <td>
                    <div>{b.service_name}</div>
                    <small className="muted">{b.variant_name}</small>
                  </td>
                  <td>{b.resource_name}</td>
                  <td>{formatPrice(b.total_cents, b.currency)}</td>
                  <td>
                    <span
                      className={`mgmt-status-pill status-${b.status.toLowerCase()}`}
                    >
                      {b.status}
                    </span>
                  </td>
                  <td>
                    <div style={{ display: "flex", gap: "6px" }}>
                      <button
                        type="button"
                        className="secondary mgmt-btn-small"
                        onClick={() => setInspectBooking(b)}
                      >
                        Details
                      </button>
                      {b.status !== "CANCELLED" && (
                        <>
                          <button
                            type="button"
                            className="secondary mgmt-btn-small"
                            onClick={() => handleOpenReschedule(b)}
                          >
                            Reschedule
                          </button>
                          <button
                            type="button"
                            className="secondary mgmt-btn-small"
                            style={{ color: "#c5221f" }}
                            onClick={() => handleOpenCancel(b)}
                          >
                            Cancel
                          </button>
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Details Modal */}
      {inspectBooking && (
        <div
          className="mgmt-modal-backdrop"
          role="dialog"
          aria-modal="true"
          aria-labelledby="inspect-booking-title"
        >
          <div className="mgmt-modal-card">
            <h2 id="inspect-booking-title">Appointment Details</h2>
            <dl className="review-details" style={{ marginBottom: "20px" }}>
              <dt>Status</dt>
              <dd>
                <span
                  className={`mgmt-status-pill status-${inspectBooking.status.toLowerCase()}`}
                >
                  {inspectBooking.status}
                </span>
              </dd>
              <dt>Time</dt>
              <dd>
                {formatDate(
                  inspectBooking.starts_at,
                  inspectBooking.location_timezone,
                )}{" "}
                &bull;{" "}
                {formatTime(
                  inspectBooking.starts_at,
                  inspectBooking.location_timezone,
                )}{" "}
                -{" "}
                {formatTime(
                  inspectBooking.ends_at,
                  inspectBooking.location_timezone,
                )}
              </dd>
              <dt>Client</dt>
              <dd>
                {inspectBooking.customer_name || "Guest"} &bull;{" "}
                {inspectBooking.customer_phone} &bull;{" "}
                {inspectBooking.customer_email}
              </dd>
              <dt>Service</dt>
              <dd>
                {inspectBooking.service_name} ({inspectBooking.variant_name})
              </dd>
              <dt>Staff</dt>
              <dd>{inspectBooking.resource_name}</dd>
              <dt>Price</dt>
              <dd>
                {formatPrice(
                  inspectBooking.total_cents,
                  inspectBooking.currency,
                )}
              </dd>
              <dt>Created By</dt>
              <dd>{inspectBooking.created_by}</dd>
              <dt>Booking ID</dt>
              <dd>
                <code>{inspectBooking.booking_id}</code>
              </dd>
            </dl>

            <div className="mgmt-form-actions">
              {inspectBooking.status !== "CANCELLED" && (
                <>
                  <button
                    type="button"
                    className="secondary"
                    onClick={() => {
                      const target = inspectBooking;
                      setInspectBooking(null);
                      handleOpenReschedule(target);
                    }}
                  >
                    Reschedule
                  </button>
                  <button
                    type="button"
                    className="secondary"
                    style={{ color: "#c5221f" }}
                    onClick={() => {
                      const target = inspectBooking;
                      setInspectBooking(null);
                      handleOpenCancel(target);
                    }}
                  >
                    Cancel Appointment
                  </button>
                </>
              )}
              <button type="button" onClick={() => setInspectBooking(null)}>
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Reschedule Modal */}
      {rescheduleTarget && (
        <div
          className="mgmt-modal-backdrop"
          role="dialog"
          aria-modal="true"
          aria-labelledby="reschedule-modal-title"
        >
          <div className="mgmt-modal-card">
            <h2 id="reschedule-modal-title">Reschedule Appointment</h2>
            <p className="muted">
              Move <strong>{rescheduleTarget.customer_name || "Client"}</strong>
              ’s appointment for{" "}
              <strong>{rescheduleTarget.service_name}</strong> to a new time
              slot.
            </p>

            {rescheduleError && (
              <div className="error" style={{ marginBottom: "16px" }}>
                {rescheduleError}
              </div>
            )}

            <form onSubmit={handleExecuteReschedule}>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "1fr 1fr",
                  gap: "16px",
                }}
              >
                <label htmlFor="reschedule-date">
                  New Date:
                  <input
                    id="reschedule-date"
                    type="date"
                    value={rescheduleDate}
                    onChange={(e) => setRescheduleDate(e.target.value)}
                    required
                  />
                </label>
                <label htmlFor="reschedule-time">
                  New Start Time ({rescheduleTarget.location_timezone}):
                  <input
                    id="reschedule-time"
                    type="time"
                    value={rescheduleTime}
                    onChange={(e) => setRescheduleTime(e.target.value)}
                    required
                  />
                </label>
              </div>

              <label htmlFor="reschedule-staff">
                Assign Staff Member:
                <select
                  id="reschedule-staff"
                  value={rescheduleStaffId}
                  onChange={(e) => setRescheduleStaffId(e.target.value)}
                  required
                >
                  {staffList.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.display_name} ({s.kind})
                    </option>
                  ))}
                </select>
              </label>

              <div className="mgmt-form-actions">
                <button
                  type="button"
                  className="secondary"
                  onClick={() => setRescheduleTarget(null)}
                  disabled={isRescheduling}
                >
                  Keep Existing Slot
                </button>
                <button type="submit" disabled={isRescheduling}>
                  {isRescheduling ? "Rescheduling..." : "Confirm New Slot"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Cancel Modal */}
      {cancelTarget && (
        <div
          className="mgmt-modal-backdrop"
          role="dialog"
          aria-modal="true"
          aria-labelledby="cancel-modal-title"
        >
          <div className="mgmt-modal-card">
            <h2 id="cancel-modal-title">Cancel Appointment</h2>
            <p className="muted">
              Are you sure you want to cancel the appointment for{" "}
              <strong>{cancelTarget.customer_name || "Guest"}</strong> on{" "}
              {formatDate(
                cancelTarget.starts_at,
                cancelTarget.location_timezone,
              )}{" "}
              at{" "}
              {formatTime(
                cancelTarget.starts_at,
                cancelTarget.location_timezone,
              )}
              ?
            </p>

            {cancelError && (
              <div className="error" style={{ marginBottom: "16px" }}>
                {cancelError}
              </div>
            )}

            <form onSubmit={handleExecuteCancel}>
              <label htmlFor="cancel-reason">
                Reason for Cancellation:
                <input
                  id="cancel-reason"
                  type="text"
                  value={cancelReason}
                  onChange={(e) => setCancelReason(e.target.value)}
                  required
                />
              </label>

              <div className="mgmt-form-actions">
                <button
                  type="button"
                  className="secondary"
                  onClick={() => setCancelTarget(null)}
                  disabled={isCancelling}
                >
                  Keep Appointment
                </button>
                <button
                  type="submit"
                  style={{ background: "#c5221f", borderColor: "#c5221f" }}
                  disabled={isCancelling}
                >
                  {isCancelling ? "Cancelling..." : "Confirm Cancellation"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* New Booking Modal */}
      {showNewBookingModal && (
        <div
          className="mgmt-modal-backdrop"
          role="dialog"
          aria-modal="true"
          aria-labelledby="calendar-new-booking-title"
        >
          <div className="mgmt-modal-card">
            <h2 id="calendar-new-booking-title">Create Appointment</h2>
            <p className="muted">
              Schedule a direct appointment for a customer.
            </p>

            {newBookingError && (
              <div className="error" style={{ marginBottom: "16px" }}>
                {newBookingError}
              </div>
            )}

            <form onSubmit={handleCreateNewBooking}>
              <label htmlFor="cal-booking-service">
                Service:
                <select
                  id="cal-booking-service"
                  value={newVariantId}
                  onChange={(e) => setNewVariantId(e.target.value)}
                  required
                >
                  {servicesList.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name} ({s.booking_duration_minutes}m) &bull;{" "}
                      {formatPrice(s.price_cents, s.currency)}
                    </option>
                  ))}
                </select>
              </label>

              <label htmlFor="cal-booking-staff">
                Staff Member:
                <select
                  id="cal-booking-staff"
                  value={newStaffId}
                  onChange={(e) => setNewStaffId(e.target.value)}
                  required
                >
                  {staffList.map((st) => (
                    <option key={st.id} value={st.id}>
                      {st.display_name} ({st.kind})
                    </option>
                  ))}
                </select>
              </label>

              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "1fr 1fr",
                  gap: "16px",
                }}
              >
                <label htmlFor="cal-booking-date">
                  Date:
                  <input
                    id="cal-booking-date"
                    type="date"
                    value={newBookingDate}
                    onChange={(e) => setNewBookingDate(e.target.value)}
                    required
                  />
                </label>
                <label htmlFor="cal-booking-time">
                  Start Time:
                  <input
                    id="cal-booking-time"
                    type="time"
                    value={newBookingTime}
                    onChange={(e) => setNewBookingTime(e.target.value)}
                    required
                  />
                </label>
              </div>

              <label htmlFor="cal-booking-name">
                Client Name:
                <input
                  id="cal-booking-name"
                  type="text"
                  placeholder="Full name"
                  value={newClientName}
                  onChange={(e) => setNewClientName(e.target.value)}
                  required
                />
              </label>

              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "1fr 1fr",
                  gap: "16px",
                }}
              >
                <label htmlFor="cal-booking-email">
                  Email:
                  <input
                    id="cal-booking-email"
                    type="email"
                    placeholder="email@example.com"
                    value={newClientEmail}
                    onChange={(e) => setNewClientEmail(e.target.value)}
                    required
                  />
                </label>
                <label htmlFor="cal-booking-phone">
                  Phone:
                  <input
                    id="cal-booking-phone"
                    type="tel"
                    placeholder="+1 555 123 4567"
                    value={newClientPhone}
                    onChange={(e) => setNewClientPhone(e.target.value)}
                    required
                  />
                </label>
              </div>

              <div className="mgmt-form-actions">
                <button
                  type="button"
                  className="secondary"
                  onClick={() => setShowNewBookingModal(false)}
                  disabled={isCreating}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={
                    isCreating || loading || !newStaffId || !newVariantId
                  }
                >
                  {isCreating ? "Saving..." : "Create Appointment"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
