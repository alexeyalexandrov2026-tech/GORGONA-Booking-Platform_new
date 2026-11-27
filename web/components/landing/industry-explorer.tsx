"use client";

import Link from "next/link";
import { useId, useState } from "react";
import {
  INDUSTRIES,
  NAICS_SECTORS,
  formatSectorCode,
  sectorLabel,
  type Industry,
} from "./industries";

const ALL = "all";
const INITIAL_VISIBLE = 12;

function normalize(value: string): string {
  return value.toLowerCase().replace(/[–—]/g, "-");
}

function matches(industry: Industry, query: string, sector: string): boolean {
  if (sector !== ALL && !industry.naics.includes(sector)) return false;
  const tokens = normalize(query).split(/\s+/).filter(Boolean);
  if (tokens.length === 0) return true;
  const haystack = normalize(
    `${industry.name} ${industry.examples} ${industry.naics.join(" ")}`,
  );
  return tokens.every((token) => haystack.includes(token));
}

function pad(id: number): string {
  return String(id).padStart(2, "0");
}

function naicsText(industry: Industry): string {
  return `NAICS ${industry.naics.map(formatSectorCode).join(", ")}`;
}

export function IndustryExplorer() {
  const searchId = useId();
  const sectorId = useId();
  const [query, setQuery] = useState("");
  const [sector, setSector] = useState<string>(ALL);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [expanded, setExpanded] = useState(false);

  const visible = INDUSTRIES.filter((industry) =>
    matches(industry, query, sector),
  );
  const isFiltered = query.trim().length > 0 || sector !== ALL;
  const displayed =
    isFiltered || expanded ? visible : visible.slice(0, INITIAL_VISIBLE);
  const hiddenCount = visible.length - displayed.length;
  const selected = INDUSTRIES.find((industry) => industry.id === selectedId);

  return (
    <div className="lp-explorer">
      <div className="lp-explorer-controls">
        <div className="lp-field">
          <label htmlFor={searchId}>Search industries</label>
          <input
            id={searchId}
            type="search"
            value={query}
            autoComplete="off"
            placeholder="Try yacht, restaurant, trucking or NAICS 54"
            onChange={(event) => setQuery(event.target.value)}
          />
        </div>
        <div className="lp-field lp-sector-select">
          <label htmlFor={sectorId}>NAICS sector</label>
          <select
            id={sectorId}
            value={sector}
            onChange={(event) => setSector(event.target.value)}
          >
            <option value={ALL}>All sectors</option>
            {NAICS_SECTORS.map((item) => (
              <option key={item.code} value={item.code}>
                {formatSectorCode(item.code)} · {item.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div
        className="lp-chips"
        role="group"
        aria-label="Filter by NAICS sector"
      >
        <button
          type="button"
          className="lp-chip"
          aria-pressed={sector === ALL}
          onClick={() => setSector(ALL)}
        >
          All sectors
        </button>
        {NAICS_SECTORS.map((item) => (
          <button
            key={item.code}
            type="button"
            className="lp-chip"
            aria-pressed={sector === item.code}
            onClick={() => setSector(item.code)}
          >
            <span className="lp-chip-code">{formatSectorCode(item.code)}</span>
            {item.label}
          </button>
        ))}
      </div>

      <p className="lp-count" role="status">
        Showing {visible.length} of {INDUSTRIES.length} industries
      </p>

      <div className="lp-detail" aria-live="polite">
        {selected ? (
          <>
            <p className="lp-eyebrow">Industry {pad(selected.id)}</p>
            <h3>{selected.name}</h3>
            <p className="lp-tags">
              {selected.naics.map((code) => (
                <span key={code} className="lp-tag">
                  NAICS {formatSectorCode(code)} · {sectorLabel(code)}
                </span>
              ))}
            </p>
            <p>{selected.examples}</p>
            <p className="lp-detail-note">
              Choosing a profile sets up your modules. Each workflow is switched
              on only after it is verified, and onboarding shows the readiness
              of every module.
            </p>
            <Link className="lp-btn lp-btn--primary" href="/onboarding/">
              Create your business
            </Link>
          </>
        ) : (
          <p className="lp-detail-placeholder">
            Select an industry to see what it covers. One business can combine
            several industries.
          </p>
        )}
      </div>

      {visible.length === 0 ? (
        <div className="lp-empty">
          <p>
            No industry matches that search. Describe your business to the AI
            Business Architect instead and it will pick the closest profile for
            you.
          </p>
          <Link className="lp-btn lp-btn--outline" href="/onboarding/">
            Describe my business
          </Link>
        </div>
      ) : (
        <>
          <ul className="lp-industry-grid">
            {displayed.map((industry) => (
              <li key={industry.id}>
                <button
                  type="button"
                  className="lp-industry"
                  aria-pressed={selectedId === industry.id}
                  onClick={() =>
                    setSelectedId((current) =>
                      current === industry.id ? null : industry.id,
                    )
                  }
                >
                  <span className="lp-industry-id" aria-hidden="true">
                    {pad(industry.id)}
                  </span>
                  <span className="lp-industry-name">{industry.name}</span>
                  <span className="lp-industry-naics">
                    {naicsText(industry)}
                  </span>
                  <span className="lp-industry-examples">
                    {industry.examples}
                  </span>
                </button>
              </li>
            ))}
          </ul>
          {!isFiltered && visible.length > INITIAL_VISIBLE && (
            <div className="lp-explorer-more">
              <button
                type="button"
                className="lp-btn lp-btn--outline"
                onClick={() => setExpanded((prev) => !prev)}
              >
                {expanded
                  ? "Show fewer industries"
                  : `Show all ${visible.length} industries (${hiddenCount} more)`}
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
