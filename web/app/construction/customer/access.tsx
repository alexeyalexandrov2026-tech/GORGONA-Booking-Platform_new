"use client";

import { useState } from "react";
import { signIn } from "../../../lib/auth";
import { ManagementApiError } from "../../../lib/management-api";

export type CustomerProblem = {
  message: string;
  needsSignIn?: boolean;
  needsReload?: boolean;
  hideDocument?: boolean;
};

export function customerFailure(
  error: unknown,
  submitting: boolean,
  document: "proposal" | "change order" | "work acceptance" | "rental change",
): CustomerProblem {
  if (error instanceof ManagementApiError) {
    if (error.status === 401 || error.code === "AUTHENTICATION_REQUIRED")
      return {
        message: `Sign in to view and answer this ${document}.`,
        needsSignIn: true,
        hideDocument: true,
      };
    if (error.status === 403 || error.status === 404)
      return {
        message: `This ${document} is unavailable for your account.`,
        hideDocument: true,
      };
    if (error.status === 409)
      return {
        message: `Reload this ${document} before answering.`,
        needsReload: true,
        hideDocument: true,
      };
  }
  return submitting
    ? {
        message: `We could not confirm your ${document === "proposal" ? "acceptance" : "answer"}. Try again to check whether it was received.`,
      }
    : {
        message: `We could not load the ${document}.`,
        needsReload: true,
        hideDocument: true,
      };
}

export function CustomerAccessFeedback({
  problem,
  returnPath,
  onReload,
}: {
  problem: CustomerProblem;
  returnPath: string;
  onReload: () => void;
}) {
  const [signingIn, setSigningIn] = useState(false);
  const [signInFailed, setSignInFailed] = useState(false);

  async function authenticate() {
    setSigningIn(true);
    setSignInFailed(false);
    try {
      await signIn(returnPath);
    } catch {
      setSignInFailed(true);
    } finally {
      setSigningIn(false);
    }
  }

  return (
    <div>
      <p role={problem.needsSignIn && !signInFailed ? "status" : "alert"}>
        {signInFailed ? "Sign-in could not start. Try again." : problem.message}
      </p>
      {problem.needsSignIn && (
        <button
          type="button"
          disabled={signingIn}
          onClick={() => void authenticate()}
        >
          {signingIn ? "Starting sign-in…" : "Sign in"}
        </button>
      )}
      {problem.needsReload && (
        <button type="button" onClick={onReload}>
          Reload document
        </button>
      )}
    </div>
  );
}
