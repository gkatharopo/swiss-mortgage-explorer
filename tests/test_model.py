from dataclasses import replace

import pytest

from app import Params, affordability, simulate


def test_second_mortgage_repaid_within_15_years():
    p = Params(horizon=15, amort="direct")
    df = simulate(p)
    first_mortgage = p.price * 2 / 3
    assert df.debt.iloc[-1] == pytest.approx(first_mortgage)


def test_indirect_amortisation_keeps_debt_flat_below_3a_cap():
    p = Params(amort="indirect", pillar3a_cap=1e9)
    df = simulate(p)
    assert df.debt.tolist() == pytest.approx([p.price * (1 - p.equity_pct)] * len(df))
    assert df.pillar3a.iloc[-1] > 0


def test_saron_shock_raises_rate_from_shock_year():
    p = Params(rate_type="saron", saron=0.0, saron_margin=0.008, saron_shock=0.02, shock_year=3)
    df = simulate(p)
    assert df.rate.iloc[2] == pytest.approx(0.008)
    assert df.rate.iloc[3] == pytest.approx(0.028)


def test_no_imputed_rent_tax_from_2029_for_non_first_buyer():
    p = Params(start_year=2029, first_buyer=False, amort="direct")
    df = simulate(p)
    assert (df.tax_effect == 0).all()


def test_affordability_default_is_below_one_third():
    assert affordability(Params()) < 1 / 3


def test_higher_rent_favours_buying():
    low = simulate(Params(monthly_rent=2_500)).buy_minus_rent.iloc[-1]
    high = simulate(Params(monthly_rent=4_500)).buy_minus_rent.iloc[-1]
    assert high > low
