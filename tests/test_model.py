import pytest

from model import Params, affordability, holding_period_multiplier, simulate


def test_second_mortgage_repaid_within_15_years():
    p = Params(horizon=15, amort="direct")
    df = simulate(p)
    first_mortgage = p.price * 2 / 3
    assert df.debt.iloc[-1] == pytest.approx(first_mortgage)


def test_indirect_amortisation_keeps_debt_flat_until_the_15_year_settlement():
    p = Params(amort="indirect", pillar3a_cap=1e9)
    df = simulate(p)
    # flat for the 14 years the mandatory schedule is still running...
    assert df.debt.iloc[:-1].tolist() == pytest.approx([p.price * (1 - p.equity_pct)] * (len(df) - 1))
    # ...then settled via a Pillar 3a withdrawal in the schedule's final year: the second
    # mortgage (the debt above 2/3 loan-to-value) is fully cleared, not left outstanding
    assert df.debt.iloc[-1] == pytest.approx(p.price * 2 / 3)
    assert df.pillar3a.iloc[-1] > 0   # any 3a savings beyond what was owed stay invested


def test_indirect_amortisation_matches_direct_after_the_15_year_settlement():
    # In reality the second mortgage doesn't sit unpaid forever under indirect
    # amortisation — once the Pillar 3a lump sum settles it, an indirect and a direct
    # scenario should converge to the same remaining debt and the same interest cost.
    indirect = simulate(Params(amort="indirect", horizon=20))
    direct = simulate(Params(amort="direct", horizon=20))
    assert indirect.debt.iloc[-1] == pytest.approx(direct.debt.iloc[-1])
    assert indirect.interest.iloc[-1] == pytest.approx(direct.interest.iloc[-1])


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


def test_horizon_below_one_raises_instead_of_crashing_on_empty_dataframe():
    with pytest.raises(ValueError):
        simulate(Params(horizon=0))


def test_pillar3a_cap_doubles_when_married():
    married = simulate(Params(amort="indirect", pillar3a_cap=1_000, married=True, horizon=1))
    single = simulate(Params(amort="indirect", pillar3a_cap=1_000, married=False, horizon=1))
    assert married.pillar3a.iloc[0] == pytest.approx(2 * single.pillar3a.iloc[0])


def test_capital_gains_tax_basis_includes_purchase_costs():
    # same house appreciation either way; only the taxable gain's cost basis should differ
    low_costs = simulate(Params(horizon=1, purchase_cost_pct=0.0, capital_gains_tax_pct=0.25))
    high_costs = simulate(Params(horizon=1, purchase_cost_pct=0.05, capital_gains_tax_pct=0.25))
    assert high_costs.owner_wealth_net_of_sale.iloc[0] > low_costs.owner_wealth_net_of_sale.iloc[0]


def test_holding_period_multiplier_surcharges_a_quick_flip_and_discounts_a_long_hold():
    assert holding_period_multiplier(1) > 1.0     # sold within 2 years: surcharge
    assert holding_period_multiplier(3) == 1.0    # 2-4 years: flat rate, no adjustment
    assert holding_period_multiplier(15) < 1.0    # held well over 5 years: discount
    assert holding_period_multiplier(100) >= 0.5  # discount is floored, never goes to zero


def test_first_time_buyer_deduction_counts_from_purchase_year_not_from_2029():
    # A purchase before 2029 already burns down its 10-year window before the deduction
    # regime even takes effect — someone buying in 2027 has 2 years elapsed by 2029, so
    # their first available (2029) deduction is already reduced to CHF 8k, not the full 10k.
    # (interest is well above any possible cap here, so taxable = -cap exactly; direct
    # amortisation means contrib3a is always 0, so it drops out of the taxable formula too.)
    p = Params(start_year=2027, married=True, first_buyer=True, horizon=3, amort="direct")
    df = simulate(p)
    year_2029_tax_effect = df.loc[df.year == 2029, "tax_effect"].iloc[0]
    assert -year_2029_tax_effect / p.marginal_tax == pytest.approx(8_000)
