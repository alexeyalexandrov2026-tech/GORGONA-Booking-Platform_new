"use client";

import { useId, useRef, type KeyboardEvent, type ReactNode } from "react";

export interface TabSpec {
  readonly key: string;
  readonly label: string;
  readonly panel: ReactNode;
}

interface LandingTabsProps {
  readonly tabs: readonly TabSpec[];
  readonly value: string;
  readonly onValueChange: (key: string) => void;
  /** Names the tab list for assistive technology. */
  readonly label: string;
}

/**
 * Tabs with the WAI-ARIA tab pattern: one tab stop, arrow keys, Home and End move between tabs.
 * Every panel stays in the document (hidden), so the content is readable without scripting.
 */
export function LandingTabs({
  tabs,
  value,
  onValueChange,
  label,
}: LandingTabsProps) {
  const base = useId();
  const buttons = useRef<(HTMLButtonElement | null)[]>([]);
  const found = tabs.findIndex((tab) => tab.key === value);
  const current = found < 0 ? 0 : found;

  function select(index: number) {
    const next = (index + tabs.length) % tabs.length;
    const tab = tabs[next];
    if (!tab) return;
    onValueChange(tab.key);
    buttons.current[next]?.focus();
  }

  function onKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    if (event.key === "ArrowRight" || event.key === "ArrowDown") {
      event.preventDefault();
      select(index + 1);
    } else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
      event.preventDefault();
      select(index - 1);
    } else if (event.key === "Home") {
      event.preventDefault();
      select(0);
    } else if (event.key === "End") {
      event.preventDefault();
      select(tabs.length - 1);
    }
  }

  return (
    <div className="lp-tabs">
      <div role="tablist" aria-label={label} className="lp-tablist">
        {tabs.map((tab, index) => (
          <button
            key={tab.key}
            ref={(element) => {
              buttons.current[index] = element;
            }}
            type="button"
            role="tab"
            id={`${base}-tab-${tab.key}`}
            aria-selected={index === current}
            aria-controls={`${base}-panel-${tab.key}`}
            tabIndex={index === current ? 0 : -1}
            className="lp-tab"
            onClick={() => onValueChange(tab.key)}
            onKeyDown={(event) => onKeyDown(event, index)}
          >
            {tab.label}
          </button>
        ))}
      </div>
      {tabs.map((tab, index) => (
        <div
          key={tab.key}
          role="tabpanel"
          id={`${base}-panel-${tab.key}`}
          aria-labelledby={`${base}-tab-${tab.key}`}
          hidden={index !== current}
          className="lp-tabpanel"
        >
          {tab.panel}
        </div>
      ))}
    </div>
  );
}
