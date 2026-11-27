import React from "react";

interface AmarkalLogoProps {
  variant?: "light" | "dark";
  height?: number;
  showWordmark?: boolean;
  className?: string;
}

/**
 * Vector reproduction of the AMARKAL Platform emblem and geometric wordmark:
 * open-apex architectural chevron (Λ) crowned by a metallic gold dot (#B8934A),
 * paired with wide crossbar-less geometric ΛMARKΛL lettering.
 */
export function AmarkalLogo({
  variant = "light",
  height = 22,
  showWordmark = true,
  className,
}: AmarkalLogoProps) {
  const strokeInk = variant === "dark" ? "#F5F6F8" : "#222327";
  const gold = variant === "dark" ? "#C9A45C" : "#B8934A";

  if (!showWordmark) {
    return (
      <span
        className={className}
        style={{ display: "inline-flex", alignItems: "center" }}
      >
        <svg
          viewBox="0 0 40 36"
          height={height}
          width={(height * 40) / 36}
          fill="none"
          aria-hidden="true"
          focusable="false"
        >
          <circle cx="20" cy="4.2" r="2.7" fill={gold} />
          <path d="M18.3 9.2 L4.5 34 H8.6 L19.6 13.4 Z" fill={strokeInk} />
          <path d="M21.7 9.2 L35.5 34 H31.4 L20.4 13.4 Z" fill={strokeInk} />
        </svg>
        <span className="sr-only">AMARKAL Platform</span>
      </span>
    );
  }

  const width = Math.round((height * 238) / 36);

  return (
    <span
      className={className}
      style={{ display: "inline-flex", alignItems: "center" }}
    >
      <svg
        viewBox="0 0 238 36"
        height={height}
        width={width}
        fill="none"
        aria-hidden="true"
        focusable="false"
      >
        {/* Architectural chevron emblem with golden apex dot */}
        <circle cx="19" cy="4.2" r="2.65" fill={gold} />
        <path d="M17.4 9.2 L3.8 34 H7.7 L18.6 13.4 Z" fill={strokeInk} />
        <path d="M20.6 9.2 L34.2 34 H30.3 L19.4 13.4 Z" fill={strokeInk} />

        {/* Geometric wide ΛMARKΛL wordmark */}
        <g
          stroke={strokeInk}
          strokeWidth="2.35"
          strokeLinecap="square"
          strokeLinejoin="miter"
        >
          {/* Λ */}
          <path d="M51 30 L60.5 9.5 L70 30" />
          {/* M */}
          <path d="M78 30 V9.5 L88 23 L98 9.5 V30" />
          {/* Λ */}
          <path d="M106 30 L115.5 9.5 L125 30" />
          {/* R */}
          <path d="M134 30 V9.5 H144.5 C148.5 9.5 151 11.9 151 15.2 C151 18.5 148.5 20.8 144.5 20.8 H134" />
          <path d="M142.8 20.8 L151.5 30" />
          {/* K */}
          <path d="M161 30 V9.5" />
          <path d="M177.5 9.5 L162.5 20.4 L178.2 30" />
          {/* Λ */}
          <path d="M186 30 L195.5 9.5 L205 30" />
          {/* L */}
          <path d="M214.5 9.5 V30 H230" />
        </g>
      </svg>
      <span className="sr-only">AMARKAL Platform</span>
    </span>
  );
}
