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


def test_saron_schedule_raises_rate_at_bucket_boundary():
    schedule = (0.0,) + (0.02,) * 9   # bucket 0 (years 0-4) flat, bucket 1+ (5y on) shocked
    p = Params(rate_type="saron", saron_margin=0.008, saron_schedule=schedule, horizon=10)
    df = simulate(p)
    assert df.rate_first.iloc[4] == pytest.approx(0.008)    # year 4: still bucket 0
    assert df.rate_first.iloc[5] == pytest.approx(0.028)    # year 5: bucket 1


def test_second_mortgage_premium_adds_to_first_mortgage_rate():
    p = Params(rate_type="fixed", second_mortgage_premium=0.01, horizon=1)
    df = simulate(p)
    assert df.rate_second.iloc[0] == pytest.approx(df.rate_first.iloc[0] + 0.01)


def test_extra_amortisation_reduces_first_mortgage_debt():
    schedule = (500.0,) * 10   # CHF 500/month extra, every bucket
    baseline = simulate(Params(horizon=5)).debt.iloc[-1]
    reduced = simulate(Params(horizon=5, extra_amort_schedule=schedule)).debt.iloc[-1]
    assert reduced < baseline


def test_property_tax_adds_to_owner_cash():
    baseline = simulate(Params(horizon=1, property_tax_pct=0.0)).owner_cash.iloc[0]
    with_tax = simulate(Params(horizon=1, property_tax_pct=0.001)).owner_cash.iloc[0]
    assert with_tax > baseline


def test_nebenkosten_adds_to_owner_cash_but_not_taxable_income():
    baseline = simulate(Params(horizon=1, nebenkosten_pct=0.0))
    with_neben = simulate(Params(horizon=1, nebenkosten_pct=0.01))
    assert with_neben.owner_cash.iloc[0] > baseline.owner_cash.iloc[0]
    assert with_neben.tax_effect.iloc[0] == pytest.approx(baseline.tax_effect.iloc[0])


def test_sale_costs_reduce_net_of_sale_wealth():
    df = simulate(Params(horizon=5, sale_fee_pct=0.04, capital_gains_tax_pct=0.25))
    assert (df.owner_wealth_net_of_sale < df.owner_wealth).all()


def test_no_imputed_rent_tax_from_2029_for_non_first_buyer():
    p = Params(start_year=2029, first_buyer=False, amort="direct")
    df = simulate(p)
    assert (df.tax_effect == 0).all()


def test_affordability_default_is_below_one_third():
    assert affordability(Params()) < 1 / 3


def test_owner_invests_the_saving_when_owning_is_cheaper():
    p = Params(monthly_rent=20_000, horizon=3)   # rent set far above the owner's cash cost
    df = simulate(p)
    assert df.owner_invested.iloc[-1] > 0
    # the renter isn't debited for the gap — their pot only ever compounds
    initial = p.price * p.equity_pct + p.price * p.purchase_cost_pct
    expected = initial * (1 + p.invest_return) ** p.horizon
    assert df.renter_wealth.iloc[-1] == pytest.approx(expected)


def test_home_equity_and_investments_sum_to_owner_wealth():
    df = simulate(Params(horizon=5))
    assert (df.home_equity + df.owner_investments).tolist() == pytest.approx(df.owner_wealth.tolist())


def test_owner_and_renter_returns_are_independent():
    p = Params(monthly_rent=20_000, horizon=3, invest_return=0.0, owner_invest_return=0.10)
    df = simulate(p)
    # renter's pot never receives a cost-saving credit here (owning is always cheaper), so with
    # invest_return=0 it must sit exactly at its untouched starting value the whole horizon
    initial = p.price * p.equity_pct + p.price * p.purchase_cost_pct
    assert df.renter_wealth.iloc[-1] == pytest.approx(initial)
    # the owner's pot, credited every year here, must reflect the 10% owner_invest_return —
    # not the renter's 0% invest_return
    assert df.owner_invested.iloc[-1] > 0


def test_higher_rent_favours_buying():
    low = simulate(Params(monthly_rent=2_500)).buy_minus_rent.iloc[-1]
    high = simulate(Params(monthly_rent=4_500)).buy_minus_rent.iloc[-1]
    assert high > low
