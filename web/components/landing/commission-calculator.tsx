"use client";

import { useId, useState } from "react";

const usd = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

/**
 * A what-if for the 0% commission promise. It only multiplies the two numbers the visitor
 * enters; it is an illustration, not a price quote, and says so.
 */
export function CommissionCalculator() {
  const revenueId = useId();
  const rateId = useId();
  const noteId = useId();
  const [revenue, setRevenue] = useState(25000);
  const [rate, setRate] = useState(15);

  const monthly = Math.round((revenue * rate) / 100);
  const yearly = monthly * 12;

  return (
    <div className="lp-calc">
      <h3 className="lp-calc-title">What a commission would cost you</h3>
      <div className="lp-calc-fields">
        <div className="lp-calc-field">
          <div className="lp-calc-row">
            <label htmlFor={revenueId}>
              Monthly revenue from orders &amp; services
            </label>
            <output className="lp-calc-value" htmlFor={revenueId}>
              {usd.format(revenue)}
            </output>
          </div>
          <input
            id={revenueId}
            type="range"
            min={2000}
            max={200000}
            step={1000}
            value={revenue}
            aria-valuetext={usd.format(revenue)}
            aria-describedby={noteId}
            onChange={(event) => setRevenue(Number(event.target.value))}
          />
        </div>
        <div className="lp-calc-field">
          <div className="lp-calc-row">
            <label htmlFor={rateId}>Commission a platform takes today</label>
            <output className="lp-calc-value" htmlFor={rateId}>
              {rate}%
            </output>
          </div>
          <input
            id={rateId}
            type="range"
            min={5}
            max={40}
            step={1}
            value={rate}
            aria-valuetext={`${rate} percent`}
            aria-describedby={noteId}
            onChange={(event) => setRate(Number(event.target.value))}
          />
        </div>
      </div>
      <dl className="lp-calc-results">
        <div className="lp-calc-result">
          <dt>Commission per year</dt>
          <dd>{usd.format(yearly)}</dd>
          <dd className="lp-calc-sub">{usd.format(monthly)} every month</dd>
        </div>
        <div className="lp-calc-result lp-calc-result--zero">
          <dt>With AMARKAL Platform</dt>
          <dd>{usd.format(0)}</dd>
          <dd className="lp-calc-sub">0% commission, always</dd>
        </div>
      </dl>
      <p className="lp-calc-note" id={noteId}>
        Illustration only: it multiplies the two numbers you choose. It is not a
        price quote and does not include payment-processing fees or any other
        costs.
      </p>
    </div>
  );
}
