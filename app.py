"""
Swiss home financing explorer — Dash practice app
Buy vs rent · SARON vs fixed · direct vs indirect amortisation

Architecture (worth saying out loud in the interview):
  1. Params        – a frozen dataclass holding every assumption
  2. simulate()     – pure model logic, no Dash imports, easy to unit-test
  3. app.py         – model + the Dash app shell (nav bar, page_container)
  4. pages/home.py  – the dashboard: layout, callback (registered at path "/")
  5. pages/docs.py  – a static documentation page (registered at path "/docs")

This file stays import-light on purpose: tests do `from app import Params,
affordability, simulate`, and every page module does `from app import ...`
for the model/constants it needs, so anything a page needs must be defined
here *before* `Dash(__name__, use_pages=True, ...)` runs — that call scans
and imports the pages/ folder immediately, before this module has finished
executing. Page callbacks use the standalone `@callback` decorator (not
`@app.callback`) for the same reason: `app` itself doesn't exist yet at
that point, so pages can't import it.

Full write-up of the model's assumptions and simplifications is on the
"Documentation" page in the app (pages/docs.py), not duplicated here.
"""
import os
from dataclasses import dataclass

import dash
import pandas as pd
from dash import Dash, dcc, html


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


def simulate(p: Params) -> pd.DataFrame:
    total_debt = p.price * (1 - p.equity_pct)
    second_debt = max(total_debt - p.price * 2 / 3, 0)   # 2nd mortgage: repay within 15 years
    first_debt = total_debt - second_debt
    second_owed = second_debt                             # mandatory-schedule bookkeeping balance
    annual_amort = second_debt / 15

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
            contrib3a = min(pay, p.pillar3a_cap)
            second_debt -= pay - contrib3a                # anything above the cap goes direct
        pillar3a = pillar3a * (1 + p.pillar3a_return) + contrib3a

        extra = min(_bucket_value(p.extra_amort_schedule, t) * 12, first_debt)
        first_debt -= extra

        if year < 2029:
            taxable = rent * p.emw_pct_of_rent - interest - maintenance - contrib3a
        else:
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
        capital_gains_tax = max(house - p.price, 0) * p.capital_gains_tax_pct
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

# Shared constants pages import — kept here (not in a page module) so they're
# defined before Dash's page-folder scan runs, see the docstring above.
PLOT_TEMPLATE = "plotly_dark"
CHART_BG = "#161a20"          # matches --card in assets/style.css
CHART_FONT = "#c7ccd4"        # matches --text in assets/style.css


# ---------------------------------------------------------------- 3. app shell
app = Dash(__name__, use_pages=True, pages_folder="pages",
           title="Swiss home financing explorer")
server = app.server  # WSGI entry point for gunicorn in production

app.layout = html.Div(className="app-shell", children=[
    html.Div(className="app-header", children=[
        html.H2("Swiss home financing explorer"),
        html.P("Buy vs rent · SARON vs fixed · direct vs indirect amortisation"),
        html.Nav(className="top-nav", children=[
            dcc.Link(page["name"], href=page["relative_path"], className="nav-link")
            for page in dash.page_registry.values()
        ]),
    ]),
    dash.page_container,
])


if __name__ == "__main__":
    # Local development only; in production gunicorn serves `server`
    app.run(debug=os.getenv("DASH_DEBUG", "1") == "1")
