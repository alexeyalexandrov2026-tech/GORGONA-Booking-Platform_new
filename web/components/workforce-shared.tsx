"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { businessDateTime, businessTimeToInstant } from "../lib/business-time";
import {
  fetchWorkspace,
  ManagementApiError,
  type LocationItem,
  type Workspace,
} from "../lib/management-api";
import {
  executeWorkforceCommand,
  fetchDesk,
  resolveWorkforceCommand,
  type WorkforceResult,
} from "../lib/workforce-api";
import {
  workforceCommandSchema,
  type Desk,
  type WorkforceCommand,
  type WriteState,
} from "../lib/workforce-contracts";
import {
  clearWorkforceRecovery,
  discardUnreadableRecovery,
  preserveWorkforceRecovery,
  readWorkforceRecovery,
  type WorkforceRecovery,
} from "../lib/workforce-recovery";

const REFUSALS: Record<string, string> = {
  WORKFORCE_CONFLICT:
    "This record changed or overlaps another one. The latest version is shown; check it and try again.",
  WORKFORCE_SKILL_REQUIRED:
    "This person does not hold a required skill at the start of the shift.",
  PERMISSION_DENIED: "You do not have permission for this action.",
  TENANT_ACCESS_DENIED: "You do not have access to this business.",
  MODULE_DISABLED:
    "Scheduling is turned off for this business. New actions are unavailable.",
  MODULE_NOT_READY:
    "Scheduling is not available for this business yet. New actions are unavailable.",
  IDEMPOTENCY_KEY_REUSED:
    "This action was already discarded. Start it again from the current record.",
};
export const explain = (error: unknown) =>
  error instanceof ManagementApiError
    ? (REFUSALS[error.code] ?? error.message)
    : error instanceof Error
      ? error.message
      : "Unable to complete this action.";
/** No answer, a broken answer or a server fault: the command may have been recorded. */
const uncertain = (error: unknown) =>
  !(error instanceof ManagementApiError) ||
  error.status === undefined ||
  error.status >= 500;
const closing = (error: unknown) =>
  error instanceof ManagementApiError &&
  ["MODULE_DISABLED", "MODULE_NOT_READY"].includes(error.code);

export function useDesk(businessId: string) {
  const [desk, setDesk] = useState<Desk | null>(null);
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const reload = useCallback(async () => {
    try {
      const [loaded, places] = await Promise.all([
        fetchDesk(businessId),
        fetchWorkspace(businessId),
      ]);
      setDesk(loaded);
      setWorkspace(places);
      setFailed(null);
    } catch (error) {
      setFailed(explain(error));
    }
  }, [businessId]);
  useEffect(() => {
    void Promise.resolve().then(reload);
  }, [reload]);
  return { desk, workspace, failed, reload };
}

export interface CommandCenter {
  busy: boolean;
  /** Nothing new may start: a command is running or an outcome is unknown. */
  blocked: boolean;
  error: string | null;
  message: string | null;
  recovery: WorkforceRecovery | null;
  unresolved: boolean;
  canResend: boolean;
  run(command: WorkforceCommand, done: string): Promise<WorkforceResult | null>;
  check(): Promise<void>;
  resend(): Promise<void>;
  discard(): Promise<void>;
  report(text: string | null): void;
}

/**
 * One command at a time. Its key and expected version are saved before sending;
 * a lost answer is settled with the server by that key, never by a new one.
 */
export function useWorkforceCommands(
  businessId: string,
  actorId: string,
  refresh: () => Promise<void>,
): CommandCenter {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [recovery, setRecovery] = useState<WorkforceRecovery | null>(null);
  const [unresolved, setUnresolved] = useState(false);
  const [canResend, setCanResend] = useState(false);
  const pending = useRef<{ command: WorkforceCommand; done: string } | null>(
    null,
  );
  const latest = useRef(refresh);
  useEffect(() => {
    latest.current = refresh;
  }, [refresh]);

  const reloaded = useCallback(async () => {
    try {
      await latest.current();
    } catch (failure) {
      setError(explain(failure));
    }
  }, []);
  const finish = useCallback(
    (key: string, text: string) => {
      clearWorkforceRecovery(actorId, businessId, key);
      pending.current = null;
      setRecovery(null);
      setUnresolved(false);
      setCanResend(false);
      setMessage(text);
    },
    [actorId, businessId],
  );
  const settle = useCallback(
    async (saved: WorkforceRecovery, cancel: boolean) => {
      setBusy(true);
      setError(null);
      try {
        const outcome = await resolveWorkforceCommand(
          businessId,
          saved.key,
          saved.reference,
          cancel,
        );
        if (outcome.state === "committed") {
          finish(saved.key, "Your earlier action was recorded.");
          await reloaded();
        } else if (outcome.state === "cancelled") {
          finish(
            saved.key,
            "The earlier action was discarded. Nothing was recorded.",
          );
          await reloaded();
        } else setUnresolved(true);
      } catch (failure) {
        setError(explain(failure));
      } finally {
        setBusy(false);
      }
    },
    [businessId, finish, reloaded],
  );

  useEffect(() => {
    let active = true;
    void Promise.resolve().then(async () => {
      let saved: WorkforceRecovery | null;
      try {
        saved = readWorkforceRecovery(actorId, businessId);
      } catch {
        discardUnreadableRecovery(actorId, businessId);
        if (active)
          setError(
            "A saved reference to an earlier action could not be read and was removed. Check your latest records.",
          );
        return;
      }
      if (!saved || !active) return;
      setRecovery(saved);
      // After a reload the body is gone; the server answers by the original key.
      await settle(saved, false);
    });
    return () => {
      active = false;
    };
  }, [actorId, businessId, settle]);

  async function send(command: WorkforceCommand, done: string) {
    try {
      const result = await executeWorkforceCommand(businessId, command);
      finish(command.key, done);
      await reloaded();
      return result;
    } catch (failure) {
      if (uncertain(failure)) {
        pending.current = { command, done };
        setCanResend(true);
        setUnresolved(false);
        setRecovery(readWorkforceRecovery(actorId, businessId));
        return null;
      }
      clearWorkforceRecovery(actorId, businessId, command.key);
      pending.current = null;
      setRecovery(null);
      setUnresolved(false);
      setCanResend(false);
      setError(explain(failure));
      // A refusal means the record or the gate changed: show the current state.
      if (closing(failure) || (failure as ManagementApiError).status === 409)
        await reloaded();
      return null;
    }
  }
  async function run(command: WorkforceCommand, done: string) {
    if (busy || recovery) {
      setError("Settle the earlier action before starting another.");
      return null;
    }
    if (!workforceCommandSchema.safeParse(command).success) {
      setError("Check the entered values and try again.");
      return null;
    }
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      preserveWorkforceRecovery(actorId, businessId, command);
      return await send(command, done);
    } catch (failure) {
      setError(explain(failure));
      return null;
    } finally {
      setBusy(false);
    }
  }
  async function resend() {
    const again = pending.current;
    if (!again || busy) return;
    setBusy(true);
    setError(null);
    try {
      await send(again.command, again.done);
    } finally {
      setBusy(false);
    }
  }
  return {
    busy,
    blocked: busy || recovery !== null,
    error,
    message,
    recovery,
    unresolved,
    canResend,
    run,
    check: async () => {
      if (recovery && !busy) await settle(recovery, false);
    },
    resend,
    discard: async () => {
      if (recovery && !busy) await settle(recovery, true);
    },
    report: (text) => {
      setMessage(null);
      setError(text);
    },
  };
}

export function CommandNotices({ center }: { center: CommandCenter }) {
  return (
    <>
      {center.error && (
        <p role="alert" className="error">
          {center.error}
        </p>
      )}
      {center.message && <p role="status">{center.message}</p>}
      {center.recovery && (
        <section
          aria-label="Workforce command recovery"
          className="warning workforce-recovery"
        >
          <h2>Result not confirmed</h2>
          <p>
            {center.unresolved
              ? "The server has no record of your last action, so nothing was changed. Send it again or discard it before starting anything else."
              : "We could not confirm whether your last action was recorded. Check the result before starting anything else."}
          </p>
          <div className="workforce-actions">
            <button disabled={center.busy} onClick={() => void center.check()}>
              Check the result
            </button>
            {center.unresolved && center.canResend && (
              <button
                disabled={center.busy}
                onClick={() => void center.resend()}
              >
                Send the same action again
              </button>
            )}
            {center.unresolved && (
              <button
                className="secondary"
                disabled={center.busy}
                onClick={() => void center.discard()}
              >
                Discard this action
              </button>
            )}
          </div>
        </section>
      )}
    </>
  );
}

export function ClosedNotice({ writes }: { writes: WriteState }) {
  if (writes === "open") return null;
  return (
    <p className="warning" role="note">
      {writes === "module_disabled"
        ? "Scheduling is turned off for this business."
        : "Scheduling is not available for this business yet."}{" "}
      Saved shifts, requests and time records stay readable, and an open time
      record can still be closed. New actions are unavailable.
    </p>
  );
}

export function zoneOf(
  locations: LocationItem[] | undefined,
  locationId: string,
): string {
  return locations?.find((item) => item.id === locationId)?.timezone ?? "UTC";
}
export function placeOf(
  locations: LocationItem[] | undefined,
  locationId: string,
): string {
  return (
    locations?.find((item) => item.id === locationId)?.name ??
    "another location"
  );
}
/** Local wall-clock time of the record's own location, never the browser's. */
export function moment(instant: string, zone: string): string {
  const local = businessDateTime(instant, zone);
  return `${local.date} ${local.time}`;
}
export function span(starts: string, ends: string, zone: string): string {
  const from = businessDateTime(starts, zone);
  const to = businessDateTime(ends, zone);
  return `${from.date} ${from.time}–${to.date === from.date ? "" : `${to.date} `}${to.time}`;
}
export function worked(microseconds: number): string {
  const minutes = Math.floor(microseconds / 60_000_000);
  return `${Math.floor(minutes / 60)} h ${(minutes % 60).toString().padStart(2, "0")} min`;
}
/** A calendar day of one location as a UTC window wide enough for any offset. */
export function dayWindow(date: string, days: number) {
  const midnight = Date.parse(`${date}T00:00:00Z`);
  return {
    starts: new Date(midnight - 15 * 3_600_000).toISOString(),
    ends: new Date(midnight + (days * 24 + 15) * 3_600_000).toISOString(),
  };
}
export const today = (zone: string) => businessDateTime(new Date(), zone).date;

export interface Moment {
  date: string;
  time: string;
}
export const toFields = (instant: string, zone: string): Moment =>
  businessDateTime(instant, zone);
export const toInstant = (value: Moment, zone: string) =>
  businessTimeToInstant(value.date, value.time, zone);
/** A date and a time of one location; each control carries its own label. */
export function MomentFields({
  legend,
  value,
  onChange,
}: {
  legend: string;
  value: Moment;
  onChange: (value: Moment) => void;
}) {
  return (
    <div className="cp-fields">
      <label>
        {legend} date
        <input
          type="date"
          required
          value={value.date}
          onChange={(event) => onChange({ ...value, date: event.target.value })}
        />
      </label>
      <label>
        {legend} time
        <input
          type="time"
          required
          value={value.time}
          onChange={(event) => onChange({ ...value, time: event.target.value })}
        />
      </label>
    </div>
  );
}

/**
 * A detail or form opened from a list. Focus moves to its heading, Escape closes
 * it, and focus returns to the control that opened it.
 */
export function Panel({
  label,
  onClose,
  children,
}: {
  label: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    const opener = document.activeElement;
    heading.current?.focus();
    return () => {
      if (opener instanceof HTMLElement && opener.isConnected) opener.focus();
    };
  }, []);
  return (
    <section
      aria-label={label}
      className="workforce-panel"
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          event.stopPropagation();
          onClose();
        }
      }}
    >
      <div className="workforce-panel-head">
        <h3 tabIndex={-1} ref={heading}>
          {label}
        </h3>
        <button type="button" className="secondary" onClick={onClose}>
          Close
        </button>
      </div>
      {children}
    </section>
  );
}
