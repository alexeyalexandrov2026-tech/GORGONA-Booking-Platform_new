"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { ManagementApiError } from "../lib/management-api";
import {
  executeInventoryCommand,
  settleInventoryCommand,
} from "../lib/inventory-api";
import type { InventoryCommand } from "../lib/inventory-contracts";
import {
  clearInventoryRecovery,
  discardUnreadableInventoryRecovery,
  preserveInventoryRecovery,
  readInventoryRecovery,
  type InventoryRecovery,
} from "../lib/inventory-recovery";

const REFUSALS: Record<string, string> = {
  MODULE_DISABLED:
    "Materials are switched off for this business. What was recorded stays readable; new changes are unavailable.",
  MODULE_NOT_READY: "Materials are not available for this business yet.",
  IDEMPOTENCY_KEY_REUSED:
    "This change was already discarded. Start it again from the current record.",
  TOO_MANY_DISCARDED_COMMANDS:
    "Too many changes were discarded today. Check the result again later.",
  PERMISSION_DENIED: "Your access does not allow this change.",
  STOCK_INSUFFICIENT: "There is not enough of this material at this place.",
  STOCK_BOOK_REQUIRED:
    "This owner has no ledger book yet. Create it in the ledger first.",
  STOCK_RULES_REQUIRED:
    "Choose the accounts of materials for this owner's book first, on the Materials screen.",
  STOCK_ACCOUNT_ARCHIVED:
    "An account of materials is archived. Choose another on the Materials screen.",
  STOCK_ARCHIVED:
    "An archived material or storage place cannot take part in a new document.",
  STOCK_RETURN_EXCEEDED:
    "More would be returned than the source line still holds.",
  STOCK_DATE_INVALID:
    "This date is in a closed period, in the future or before the books start.",
  STOCK_BUSY:
    "The stock was busy with another document. Nothing was recorded; post it again.",
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

export type CommandCenter = {
  busy: boolean;
  blocked: boolean;
  error: string | null;
  message: string | null;
  /** Grows each time a change is settled, so a form can start afresh. */
  generation: number;
  recovery: InventoryRecovery | null;
  unresolved: boolean;
  canResend: boolean;
  run: (command: InventoryCommand, done: string) => Promise<boolean>;
  check: () => Promise<void>;
  resend: () => Promise<void>;
  discard: () => Promise<void>;
};

/**
 * One inventory change at a time, on every inventory screen of this person and business.
 * Its key and the result it should produce are saved before sending; a lost answer is
 * settled with the server by that key, never by a new one.
 */
export function useInventoryCommands(
  businessId: string,
  actorId: string,
  refresh: () => Promise<void>,
): CommandCenter {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [generation, setGeneration] = useState(0);
  const [recovery, setRecovery] = useState<InventoryRecovery | null>(null);
  const [unresolved, setUnresolved] = useState(false);
  const [canResend, setCanResend] = useState(false);
  const pending = useRef<{ command: InventoryCommand; done: string } | null>(
    null,
  );
  const running = useRef(false);
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
      clearInventoryRecovery(actorId, businessId, key);
      pending.current = null;
      setRecovery(null);
      setUnresolved(false);
      setCanResend(false);
      setMessage(text);
      setGeneration((value) => value + 1);
    },
    [actorId, businessId],
  );
  const settle = useCallback(
    async (saved: InventoryRecovery, cancel: boolean) => {
      if (running.current) return;
      running.current = true;
      setBusy(true);
      setError(null);
      try {
        const outcome = await settleInventoryCommand(
          businessId,
          saved.key,
          saved.reference,
          cancel,
        );
        if (outcome.state === "unresolved") setUnresolved(true);
        else {
          await reloaded();
          finish(
            saved.key,
            outcome.state === "committed"
              ? "Your earlier change was recorded."
              : "The earlier change was discarded. Nothing was recorded.",
          );
        }
      } catch (failure) {
        setError(explain(failure));
      } finally {
        running.current = false;
        setBusy(false);
      }
    },
    [businessId, finish, reloaded],
  );
  useEffect(() => {
    let active = true;
    void Promise.resolve().then(async () => {
      let saved: InventoryRecovery | null;
      try {
        saved = readInventoryRecovery(actorId, businessId);
      } catch {
        discardUnreadableInventoryRecovery(actorId, businessId);
        if (active)
          setError(
            "A saved reference to an earlier change could not be read and was removed. Check the lists.",
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

  async function send(command: InventoryCommand, done: string) {
    try {
      await executeInventoryCommand(businessId, command);
      await reloaded();
      finish(command.key, done);
      return true;
    } catch (failure) {
      if (uncertain(failure)) {
        pending.current = { command, done };
        setCanResend(true);
        setUnresolved(false);
        setRecovery(readInventoryRecovery(actorId, businessId));
        return false;
      }
      clearInventoryRecovery(actorId, businessId, command.key);
      pending.current = null;
      setRecovery(null);
      setUnresolved(false);
      setCanResend(false);
      setError(explain(failure));
      await reloaded();
      return false;
    }
  }
  return {
    busy,
    blocked: busy || recovery !== null,
    error,
    message,
    generation,
    recovery,
    unresolved,
    canResend,
    run: async (command, done) => {
      // A second activation before the screen re-renders is ignored, not queued.
      if (running.current) return false;
      if (recovery) {
        setError("Settle the earlier change before starting another.");
        return false;
      }
      running.current = true;
      setBusy(true);
      setError(null);
      setMessage(null);
      try {
        preserveInventoryRecovery(actorId, businessId, command);
        return await send(command, done);
      } catch (failure) {
        setError(explain(failure));
        return false;
      } finally {
        running.current = false;
        setBusy(false);
      }
    },
    check: async () => {
      if (recovery && !busy) await settle(recovery, false);
    },
    resend: async () => {
      const again = pending.current;
      if (!again || running.current) return;
      running.current = true;
      setBusy(true);
      setError(null);
      try {
        await send(again.command, again.done);
      } finally {
        running.current = false;
        setBusy(false);
      }
    },
    discard: async () => {
      if (recovery && !busy) await settle(recovery, true);
    },
  };
}

/** What became of the last change; `withError: false` leaves the refusal to a form. */
export function InventoryNotices({
  center,
  label,
  withError = true,
}: {
  center: CommandCenter;
  label: string;
  withError?: boolean;
}) {
  return (
    <>
      {withError && center.error && (
        <p role="alert" className="error">
          {center.error}
        </p>
      )}
      {center.message && <p role="status">{center.message}</p>}
      {center.recovery && (
        <section aria-label={label} className="warning">
          <h2>Result not confirmed</h2>
          <p>
            {center.unresolved
              ? "The server has no record of your last change yet. It may still be in progress: check again in a moment, send the same change again, or discard it before starting anything else."
              : "We could not confirm whether your last change was recorded. Check the result before starting anything else."}
          </p>
          <button disabled={center.busy} onClick={() => void center.check()}>
            Check the result
          </button>
          {center.unresolved && center.canResend && (
            <button disabled={center.busy} onClick={() => void center.resend()}>
              Send the same change again
            </button>
          )}
          {center.unresolved && (
            <button
              className="secondary"
              disabled={center.busy}
              onClick={() => void center.discard()}
            >
              Discard this change
            </button>
          )}
        </section>
      )}
    </>
  );
}
