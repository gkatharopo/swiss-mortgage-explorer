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
@dataclass(frozen=True)
class Params:
    price: float = 1_200_000
    equity_pct: float = 0.20
    purchase_cost_pct: float = 0.01
    gross_income: float = 220_000
    monthly_rent: float = 3_500          # rent for an equivalent flat
    rent_growth: float = 0.01
    house_growth: float = 0.015
    invest_return: float = 0.04
    fixed_rate: float = 0.015            # placeholder — check current offers
    saron: float = 0.0                   # placeholder — check current SARON
    saron_margin: float = 0.008
    saron_shock: float = 0.0             # added to SARON from shock_year onwards
    shock_year: int = 3
    maintenance_pct: float = 0.01
    emw_pct_of_rent: float = 0.65        # imputed rental value as share of market rent
    marginal_tax: float = 0.30
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


def simulate(p: Params) -> pd.DataFrame:
    equity = p.price * p.equity_pct
    debt = p.price - equity
    second_left = max(debt - p.price * 2 / 3, 0)   # 2nd mortgage: repay within 15 years
    annual_amort = second_left / 15

    house, pillar3a = p.price, 0.0
    renter = equity + p.price * p.purchase_cost_pct
    rent = p.monthly_rent * 12
    rows = []

    for t in range(p.horizon):
        year = p.start_year + t

        if p.rate_type == "fixed":
            rate = p.fixed_rate
        else:
            shock = p.saron_shock if t >= p.shock_year else 0
            rate = max(p.saron + shock, 0) + p.saron_margin   # SARON floored at 0

        interest = debt * rate
        maintenance = house * p.maintenance_pct

        pay = min(annual_amort, second_left)
        second_left -= pay
        if p.amort == "direct":
            contrib3a = 0.0
            debt -= pay
        else:
            contrib3a = min(pay, p.pillar3a_cap)
            debt -= pay - contrib3a                        # anything above the cap goes direct
        pillar3a = pillar3a * (1 + p.pillar3a_return) + contrib3a

        if year < 2029:
            taxable = rent * p.emw_pct_of_rent - interest - maintenance - contrib3a
        else:
            base = 10_000 if p.married else 5_000
            cap = base * max(0.0, 1 - 0.1 * t) if p.first_buyer else 0.0
            taxable = -min(interest, cap) - contrib3a
        tax = p.marginal_tax * taxable                     # + means the owner pays more tax

        owner_cash = interest + maintenance + pay + tax
        renter = renter * (1 + p.invest_return) + (owner_cash - rent)
        house *= 1 + p.house_growth

        rows.append(dict(
            year=year, rate=rate, debt=debt, interest=interest, maintenance=maintenance,
            amortisation=pay, pillar3a=pillar3a, tax_effect=tax, owner_cash=owner_cash,
            rent=rent, owner_wealth=house - debt + pillar3a, renter_wealth=renter,
        ))
        rent *= 1 + p.rent_growth

    df = pd.DataFrame(rows)
    df["buy_minus_rent"] = df.owner_wealth - df.renter_wealth
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
