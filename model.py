"""
Swiss home financing explorer — pure model logic.

No Dash imports here on purpose: `simulate()` is unit-tested directly (see
tests/test_model.py) without spinning up a browser, and both app.py (the Dash
shell) and every page module import straight from this file.
"""
from dataclasses import dataclass

import pandas as pd

# ---------------------------------------------------------------- 1. assumptions
BUCKET_YEARS = 5     # rate/amortisation schedules are entered per 5-year period
N_BUCKETS = 10        # ...covering 50 years, same grid rentbuy.top uses


@dataclass(frozen=True)
class Params:
    price: float = 1_200_000
    equity_pct: float = 0.20
    purchase_cost_pct: float = 0.01
    gross_income: float = 220_000
    monthly_rent: float = 3_500          # rent for an equivalent flat
    rent_growth: float = 0.01
    house_growth: float = 0.015
    invest_return: float = 0.04          # return on the renter's invested equity + cost savings
    owner_invest_return: float = 0.04    # return on the owner's invested cost savings (independent rate)
    # one rate per 5-year bucket (years 0-4, 5-9, ..., 45-49); a flat rate is
    # just a schedule where every bucket holds the same value
    fixed_rate_schedule: tuple = (0.015,) * N_BUCKETS   # placeholders — check current offers
    saron_schedule: tuple = (0.0,) * N_BUCKETS          # SARON index, before margin
    saron_margin: float = 0.008
    second_mortgage_premium: float = 0.01   # 2nd mortgage typically prices 0.5-1% above the 1st
    extra_amort_schedule: tuple = (0.0,) * N_BUCKETS    # voluntary 1st-mortgage overpay, CHF/month
    maintenance_pct: float = 0.01
    nebenkosten_pct: float = 0.005       # heating, building insurance, refuse, common-area electricity...
                                          # ...distinct from maintenance_pct, which is the repair/reserve fund
    property_tax_pct: float = 0.0        # cantonal Liegenschaftssteuer; only some cantons levy it
    emw_pct_of_rent: float = 0.65        # imputed rental value as share of market rent
    marginal_tax: float = 0.30
    sale_fee_pct: float = 0.04           # broker/notary costs, charged against a hypothetical sale
    capital_gains_tax_pct: float = 0.25  # cantonal Grundstückgewinnsteuer on the gain, if sold
    horizon: int = 15
    pillar3a_cap: float = 7_258          # per person; check the current limit
    pillar3a_return: float = 0.02
    first_buyer: bool = True
    married: bool = True
    start_year: int = 2027
    rate_type: str = "fixed"             # "fixed" | "saron"
    amort: str = "direct"                # "direct" | "indirect"


# ---------------------------------------------------------------- 2. model
def affordability(p: Params) -> float:
    """Bank rule of thumb: 5% notional rate + 1% maintenance + amortisation <= 1/3 income."""
    debt = p.price * (1 - p.equity_pct)
    second = max(debt - p.price * 2 / 3, 0)
    cost = 0.05 * debt + 0.01 * p.price + second / 15
    return cost / p.gross_income


def _bucket_value(schedule, t):
    """schedule[t // BUCKET_YEARS], clamped to the last bucket past year 50."""
    return schedule[min(t // BUCKET_YEARS, len(schedule) - 1)]


def holding_period_multiplier(years_held: int) -> float:
    """Illustrative Zürich-style adjustment to the flat capital_gains_tax_pct: a surcharge
    for a quick flip, tapering to a discount the longer the property is held. Real
    Grundstückgewinnsteuer schedules are set per canton and vary a lot — this is a rough,
    clearly-approximate shape, not a specific canton's actual table. Check the applicable
    canton before trusting the "net of sale" figures for a real decision."""
    if years_held < 2:
        return 1.5
    if years_held < 5:
        return 1.0
    return max(1.0 - 0.05 * ((years_held - 5) // 2 + 1), 0.5)


def simulate(p: Params) -> pd.DataFrame:
    if p.horizon < 1:
        raise ValueError(f"horizon must be at least 1, got {p.horizon}")

    total_debt = p.price * (1 - p.equity_pct)
    second_debt = max(total_debt - p.price * 2 / 3, 0)   # 2nd mortgage: repay within 15 years
    first_debt = total_debt - second_debt
    second_owed = second_debt                             # mandatory-schedule bookkeeping balance
    annual_amort = second_debt / 15
    pillar3a_cap = p.pillar3a_cap * (2 if p.married else 1)   # two pension-linked accounts if married

    house, pillar3a = p.price, 0.0
    renter_pot = p.price * p.equity_pct + p.price * p.purchase_cost_pct
    owner_pot = 0.0                                        # invested whenever owning is cheaper
    rent = p.monthly_rent * 12
    rows = []

    for t in range(p.horizon):
        year = p.start_year + t

        if p.rate_type == "fixed":
            rate_first = _bucket_value(p.fixed_rate_schedule, t)
        else:
            rate_first = max(_bucket_value(p.saron_schedule, t), 0) + p.saron_margin   # floored at 0
        rate_second = rate_first + p.second_mortgage_premium

        interest = first_debt * rate_first + second_debt * rate_second
        maintenance = house * p.maintenance_pct
        nebenkosten = house * p.nebenkosten_pct
        property_tax = house * p.property_tax_pct

        pay = min(annual_amort, second_owed)
        second_owed -= pay
        if p.amort == "direct":
            contrib3a = 0.0
            second_debt -= pay
        else:
            contrib3a = min(pay, pillar3a_cap)
            second_debt -= pay - contrib3a                # anything above the cap goes direct
        pillar3a = pillar3a * (1 + p.pillar3a_return) + contrib3a

        if p.amort == "indirect" and second_owed <= 1e-6:
            # The mandatory 15-year schedule has just run its course. In reality the
            # second mortgage doesn't just sit there unpaid from this point on — it's
            # settled by withdrawing the Pillar 3a account (up to what's still owed) and
            # clearing the balance in one lump sum. Idempotent: a no-op once either side
            # of the min() hits zero, so it's safe to leave this check unconditional for
            # every year after the schedule completes, not just the one year it does.
            settle = min(pillar3a, second_debt)
            second_debt -= settle
            pillar3a -= settle

        extra = min(_bucket_value(p.extra_amort_schedule, t) * 12, first_debt)
        first_debt -= extra

        if year < 2029:
            taxable = rent * p.emw_pct_of_rent - interest - maintenance - contrib3a
        else:
            # The first-buyer deduction's 10-year countdown runs from the purchase year
            # (start_year), not from 2029, even for purchases made before the reform takes
            # effect — e.g. someone buying in 2024 is still eligible through 2034, but the
            # deduction is already partway reduced by the time 2029 arrives. `t` here is
            # already years-since-purchase (year = start_year + t), so this falls out
            # naturally. Verified against the post-referendum guidance (Sept 2025 vote,
            # in force 1 Jan 2029); confirm against the final ordinance text before relying
            # on this for a real purchase.
            base = 10_000 if p.married else 5_000
            cap = base * max(0.0, 1 - 0.1 * t) if p.first_buyer else 0.0
            taxable = -min(interest, cap) - contrib3a
        tax = p.marginal_tax * taxable                     # + means the owner pays more tax

        owner_cash = interest + maintenance + nebenkosten + property_tax + pay + extra + tax
        diff = owner_cash - rent                            # + means owning cost more this year
        renter_pot *= 1 + p.invest_return
        owner_pot *= 1 + p.owner_invest_return
        if diff > 0:
            renter_pot += diff       # renter is cheaper this year — invests the saving
        else:
            owner_pot += -diff       # owning is cheaper this year — owner invests the saving
        house *= 1 + p.house_growth

        debt = first_debt + second_debt
        sale_fee = house * p.sale_fee_pct
        # Grundstückgewinnsteuer practice taxes the gain over cost basis, not just the raw
        # purchase price — acquisition costs (notary, transfer) count against the gain too —
        # and the rate itself depends on how long the property has been held.
        cost_basis = p.price * (1 + p.purchase_cost_pct)
        gain = max(house - cost_basis, 0)
        capital_gains_tax = gain * p.capital_gains_tax_pct * holding_period_multiplier(t + 1)
        home_equity = house - debt                          # wealth tied up in the property itself
        owner_investments = pillar3a + owner_pot             # wealth held as investments, not property
        owner_wealth = home_equity + owner_investments
        owner_wealth_net_of_sale = owner_wealth - sale_fee - capital_gains_tax

        rows.append(dict(
            year=year, rate_first=rate_first, rate_second=rate_second, debt=debt,
            interest=interest, maintenance=maintenance, nebenkosten=nebenkosten,
            property_tax=property_tax,
            amortisation=pay, extra_amortisation=extra, pillar3a=pillar3a,
            owner_invested=owner_pot, home_equity=home_equity,
            owner_investments=owner_investments, tax_effect=tax,
            owner_cash=owner_cash, rent=rent, owner_wealth=owner_wealth,
            owner_wealth_net_of_sale=owner_wealth_net_of_sale, renter_wealth=renter_pot,
        ))
        rent *= 1 + p.rent_growth

    df = pd.DataFrame(rows)
    df["buy_minus_rent"] = df.owner_wealth - df.renter_wealth
    df["buy_minus_rent_net_of_sale"] = df.owner_wealth_net_of_sale - df.renter_wealth
    return df


SCENARIOS = {
    "Fixed · direct": dict(rate_type="fixed", amort="direct"),
    "Fixed · indirect": dict(rate_type="fixed", amort="indirect"),
    "SARON · direct": dict(rate_type="saron", amort="direct"),
    "SARON · indirect": dict(rate_type="saron", amort="indirect"),
}

DEFAULTS = Params()
