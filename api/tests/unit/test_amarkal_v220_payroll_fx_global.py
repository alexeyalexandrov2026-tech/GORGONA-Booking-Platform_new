"""Unit tests for AMARKAL v2.20.0: US Payroll Compliance (FLSA/CA/Union),
Multi-Currency FX Ledger Gain/Loss & International Tax / VAT Reverse Charge.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from gorgona_booking.business.global_payroll_fx import (
    InternationalTaxProfileView,
    PayrollProfileView,
    calculate_international_tax,
    calculate_us_paystub,
    compute_fx_gain_loss_cents,
    convert_minor_to_usd_cents,
    split_us_overtime_hours,
)


def _profile(**overrides: object) -> PayrollProfileView:
    base: dict[str, object] = {
        "id": uuid4(),
        "employee_code": "EMP-101",
        "full_name": "Jordan Vance",
        "email": "jordan@acme.us",
        "work_state": "CA",
        "pay_type": "hourly",
        "base_rate_cents": 4000,  # $40.00/hr
        "overtime_rule": "california_daily_8_12",
        "union_local_code": "IBT Local 705",
        "union_dues_cents": 4500,
        "union_ot_multiplier_bps": 15000,
        "union_doubletime_bps": 20000,
        "health_insurance_pretax_cents": 15000,
        "retirement_401k_bps": 500,  # 5%
        "filing_status": "single",
        "state_tax_override_bps": None,
        "external_payroll_provider": "gusto",
        "is_active": True,
        "created_at": datetime.now(UTC),
    }
    base.update(overrides)
    return PayrollProfileView(**base)  # type: ignore[arg-type]


def test_california_daily_8_12_and_flsa_overtime_splits() -> None:
    # CA worker works 14h on Mon, 10h Tue, 8h Wed, 8h Thu, 8h Fri
    # Day 1 (14h): 8h reg + 4h OT + 2h DT
    # Day 2 (10h): 8h reg + 2h OT
    # Days 3-5: 24h reg -> Total reg=40h, OT=6h, DT=2h
    reg, ot, dt, note = split_us_overtime_hours(
        overtime_rule="california_daily_8_12",
        daily_hours_milli=[14_000, 10_000, 8_000, 8_000, 8_000],
    )
    assert reg == 40_000
    assert ot == 6_000
    assert dt == 2_000
    assert "California Labor Code" in note

    # Federal FLSA on same 48h total -> 40h reg, 8h OT, 0h DT
    reg2, ot2, dt2, _ = split_us_overtime_hours(
        overtime_rule="flsa_weekly_40",
        daily_hours_milli=[14_000, 10_000, 8_000, 8_000, 8_000],
    )
    assert reg2 == 40_000
    assert ot2 == 8_000
    assert dt2 == 0


def test_us_paystub_exact_gross_taxes_union_dues_and_net() -> None:
    prof = _profile()
    # 40h @ $40 = $1600; 6h OT @ $60 = $360; 2h DT @ $80 = $160 -> gross = $2,120.00 (212_000)
    calc = calculate_us_paystub(
        profile=prof,
        regular_hours_milli=40_000,
        overtime_hours_milli=6_000,
        doubletime_hours_milli=2_000,
        bonus_cents=0,
    )
    assert calc.regular_pay_cents == 160_000
    assert calc.overtime_pay_cents == 36_000
    assert calc.doubletime_pay_cents == 16_000
    assert calc.gross_pay_cents == 212_000
    assert calc.pretax_health_cents == 15_000
    assert calc.pretax_401k_cents == 10_600  # 5% of 212_000
    assert calc.union_dues_cents == 4_500
    assert calc.state_income_tax_cents > 0  # CA 8%
    assert calc.employer_fica_cents == calc.social_security_cents + calc.medicare_cents
    assert calc.net_pay_cents < calc.gross_pay_cents

    # Texas worker has 0% state income tax
    tx_prof = _profile(work_state="TX", union_local_code="", union_dues_cents=0)
    tx_calc = calculate_us_paystub(
        profile=tx_prof,
        regular_hours_milli=40_000,
        overtime_hours_milli=0,
        doubletime_hours_milli=0,
    )
    assert tx_calc.state_income_tax_cents == 0
    assert tx_calc.union_dues_cents == 0


def test_multicurrency_fx_gain_loss_and_eu_vat_reverse_charge() -> None:
    # EUR 10,000.00 (1_000_000 minor) booked at 1.080000 USD -> $10,800.00
    booked = convert_minor_to_usd_cents(amount_minor=1_000_000, rate_micros=1_080_000)
    assert booked == 1_080_000

    # EUR strengthens to 1.105000 USD -> $11,050.00
    reval = convert_minor_to_usd_cents(amount_minor=1_000_000, rate_micros=1_105_000)
    assert reval == 1_105_000

    # Receivable gains +$250.00; Payable loses -$250.00
    assert (
        compute_fx_gain_loss_cents(
            entry_kind="receivable", booked_usd_cents=booked, current_usd_cents=reval
        )
        == 25_000
    )
    assert (
        compute_fx_gain_loss_cents(
            entry_kind="payable", booked_usd_cents=booked, current_usd_cents=reval
        )
        == -25_000
    )

    eu_de = InternationalTaxProfileView(
        id=uuid4(),
        country_code="DE",
        region_label="European Union — Germany",
        tax_regime="eu_vat",
        tax_name="EU VAT (USt)",
        standard_rate_bps=1900,
        reduced_rate_bps=700,
        reverse_charge_b2b=True,
        tax_registration_id="DE123456789",
        default_currency="EUR",
        reporting_standard="IFRS_EU",
        is_default=False,
        is_active=True,
    )
    domestic = calculate_international_tax(
        profile=eu_de, subtotal_minor=100_000, is_b2b_cross_border=False
    )
    assert domestic.tax_minor == 19_000
    assert domestic.total_minor == 119_000
    assert domestic.reverse_charge_applied is False

    b2b_rc = calculate_international_tax(
        profile=eu_de, subtotal_minor=100_000, is_b2b_cross_border=True
    )
    assert b2b_rc.tax_minor == 0
    assert b2b_rc.total_minor == 100_000
    assert b2b_rc.reverse_charge_applied is True
