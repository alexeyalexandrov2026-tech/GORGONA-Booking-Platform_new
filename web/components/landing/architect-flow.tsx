"use client";

import Link from "next/link";
import { useId, useState } from "react";
import { LandingTabs, type TabSpec } from "./landing-tabs";

type StepKey = "describe" | "draft" | "approve";
type PartKey = "services" | "resources" | "hours";

const STEPS: readonly { key: StepKey; label: string }[] = [
  { key: "describe", label: "1. Describe or upload" },
  { key: "draft", label: "2. AI drafts your setup" },
  { key: "approve", label: "3. You approve" },
];

const PARTS: readonly { key: PartKey; label: string }[] = [
  { key: "services", label: "Services and prices" },
  { key: "resources", label: "Resources" },
  { key: "hours", label: "Hours and time zone" },
];

/**
 * The AI Business Architect as a three-step walk-through. Every value shown is an example; the
 * real flow lives in onboarding, where nothing goes live before the owner approves it.
 */
export function ArchitectFlow() {
  const approvalId = useId();
  const [step, setStep] = useState<StepKey>("describe");
  const [approved, setApproved] = useState<Record<PartKey, boolean>>({
    services: false,
    resources: false,
    hours: false,
  });
  const count = PARTS.filter((part) => approved[part.key]).length;
  const index = STEPS.findIndex((item) => item.key === step);
  const previous = STEPS[index - 1];
  const next = STEPS[index + 1];

  const nav = (
    <div className="lp-step-nav">
      {previous ? (
        <button
          type="button"
          className="lp-btn lp-btn--outline"
          onClick={() => setStep(previous.key)}
        >
          Back
        </button>
      ) : null}
      {next ? (
        <button
          type="button"
          className="lp-btn lp-btn--primary"
          onClick={() => setStep(next.key)}
        >
          Next: {next.label.slice(3)}
        </button>
      ) : null}
    </div>
  );

  const tabs: TabSpec[] = [
    {
      key: "describe",
      label: STEPS[0]?.label ?? "",
      panel: (
        <>
          <p className="lp-example-label">Example input</p>
          <blockquote className="lp-bubble">
            Mobile dog groomer in Austin, Texas. Two vans, Tuesday to Saturday,
            8 AM to 5 PM. Bath and brush is $65, full groom is $95.
          </blockquote>
          <p>
            Or take a photo of your price list or menu. The AI reads the
            services and prices from the picture, so you do not retype them.
          </p>
          <p className="lp-tags">
            <span className="lp-tag">Plain English</span>
            <span className="lp-tag">Price-list photo</span>
          </p>
          {nav}
        </>
      ),
    },
    {
      key: "draft",
      label: STEPS[1]?.label ?? "",
      panel: (
        <>
          <p className="lp-example-label">Example draft, for your review</p>
          <dl className="lp-draft">
            <div>
              <dt>Industry</dt>
              <dd>Veterinary and animal services · NAICS 54, 81</dd>
            </div>
            <div>
              <dt>Services</dt>
              <dd>Bath and brush · $65</dd>
              <dd>Full groom · $95</dd>
            </div>
            <div>
              <dt>Resources</dt>
              <dd>Van 1</dd>
              <dd>Van 2</dd>
            </div>
            <div>
              <dt>Hours</dt>
              <dd>Tuesday to Saturday · 8:00 AM to 5:00 PM</dd>
              <dd>Central Time (America/Chicago)</dd>
            </div>
          </dl>
          {nav}
        </>
      ),
    },
    {
      key: "approve",
      label: STEPS[2]?.label ?? "",
      panel: (
        <>
          <p className="lp-example-label">You stay in control</p>
          <p>
            The AI only drafts. Nothing goes live until you approve it. Review
            each part, change what you like, then create your business.
          </p>
          <fieldset className="lp-approve">
            <legend>Approve the draft</legend>
            {PARTS.map((part) => (
              <label key={part.key} className="lp-approve-row">
                <input
                  type="checkbox"
                  checked={approved[part.key]}
                  aria-describedby={approvalId}
                  onChange={(event) =>
                    setApproved((current) => ({
                      ...current,
                      [part.key]: event.target.checked,
                    }))
                  }
                />
                <span>{part.label}</span>
              </label>
            ))}
            <p className="lp-approve-count" id={approvalId} aria-live="polite">
              {count} of {PARTS.length} approved
              {count === PARTS.length ? " · ready to launch" : ""}
            </p>
          </fieldset>
          <div className="lp-step-nav">
            {previous ? (
              <button
                type="button"
                className="lp-btn lp-btn--outline"
                onClick={() => setStep(previous.key)}
              >
                Back
              </button>
            ) : null}
            <Link className="lp-btn lp-btn--primary" href="/onboarding/">
              Try it with your business
            </Link>
          </div>
        </>
      ),
    },
  ];

  return (
    <div className="lp-card lp-architect">
      <LandingTabs
        tabs={tabs}
        value={step}
        onValueChange={(key) => setStep(key as StepKey)}
        label="How the AI Business Architect works"
      />
    </div>
  );
}
