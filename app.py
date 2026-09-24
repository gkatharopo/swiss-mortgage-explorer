"""
Swiss home financing explorer — Dash practice app
Buy vs rent · SARON vs fixed · direct vs indirect amortisation

Architecture (worth saying out loud in the interview):
  1. Params      – a frozen dataclass holding every assumption
  2. simulate()  – pure model logic, no Dash imports, easy to unit-test
  3. layout      – components with ids
  4. callback    – reads inputs -> builds Params -> calls the model -> returns figures

Deliberate simplifications:
- One marginal tax rate applied to changes in taxable income.
- Tax regime: imputed rental value (Eigenmietwert) taxed, interest + maintenance
  deductible until end-2028. From 2029: no EMW, no maintenance or interest deduction,
  except the first-buyer interest deduction (CHF 10k married / 5k single, falling
  10%/yr over 10 years; assumed counted from the purchase year — check).
- No capital gains tax, wealth tax, selling costs, or 3a withdrawal tax.
- Renter invests the down payment + purchase costs, then each year the difference
  between the owner's total cash outflow and rent (negative = withdrawal).
- 3a is only modelled for the owner's indirect amortisation. In reality a renter can
  also pay into 3a, so the fair 3a comparison is indirect vs direct, not buy vs rent.
"""
import os
from dataclasses import dataclass, replace

import pandas as pd
import plotly.graph_objects as go
from dash import Dash, Input, Output, dash_table, dcc, html
from dash.exceptions import PreventUpdate


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

# ---------------------------------------------------------------- 3. layout
# (field id, label, step, entered as percent?)
FIELDS = [
    ("price", "Purchase price (CHF)", 10_000, False),
    ("equity_pct", "Equity (%)", 1, True),
    ("purchase_cost_pct", "Purchase costs (%)", 0.1, True),
    ("gross_income", "Gross household income (CHF)", 5_000, False),
    ("monthly_rent", "Equivalent rent (CHF/month)", 100, False),
    ("rent_growth", "Rent growth (%/yr)", 0.1, True),
    ("house_growth", "Property growth (%/yr)", 0.1, True),
    ("invest_return", "Renter's return (%/yr)", 0.1, True),
    ("fixed_rate", "Fixed rate (%)", 0.05, True),
    ("saron", "SARON (%)", 0.05, True),
    ("saron_margin", "SARON margin (%)", 0.05, True),
    ("saron_shock", "SARON shock (+%)", 0.25, True),
    ("shock_year", "Shock from year", 1, False),
    ("maintenance_pct", "Maintenance (%/yr)", 0.1, True),
    ("emw_pct_of_rent", "Imputed rent (% of rent)", 5, True),
    ("marginal_tax", "Marginal tax rate (%)", 1, True),
    ("horizon", "Horizon (years)", 1, False),
]
INT_FIELDS = {"shock_year", "horizon"}
DEFAULTS = Params()


def field(fid, label, step, is_pct):
    value = getattr(DEFAULTS, fid) * (100 if is_pct else 1)
    return html.Div([
        html.Label(label, style={"fontSize": 13}),
        dcc.Input(id=fid, type="number", value=round(value, 4), step=step,
                  debounce=True, style={"width": "100%"}),
    ], style={"marginBottom": 8})


TABLE_COLS = ["year", "rate", "debt", "interest", "amortisation", "pillar3a",
              "tax_effect", "owner_cash", "rent", "owner_wealth", "renter_wealth"]

app = Dash(__name__, title="Swiss home financing explorer")
server = app.server  # WSGI entry point for gunicorn in production
app.layout = html.Div(style={"fontFamily": "sans-serif", "maxWidth": 1250, "margin": "auto"}, children=[
    html.H2("Swiss home financing explorer"),
    html.Div(style={"display": "grid", "gridTemplateColumns": "300px 1fr", "gap": 24}, children=[
        html.Div([
            *[field(*f) for f in FIELDS],
            dcc.Checklist(id="flags", value=["first", "married"], options=[
                {"label": " First-time buyer", "value": "first"},
                {"label": " Married", "value": "married"},
            ]),
        ]),
        html.Div([
            html.Div(id="afford", style={"padding": 12, "borderRadius": 8, "background": "#f3f3f3"}),
            dcc.Graph(id="wealth"),
            dcc.RadioItems(id="scenario", options=list(SCENARIOS), value="Fixed · direct", inline=True),
            dcc.Graph(id="costs"),
            dash_table.DataTable(
                id="table", page_size=15, style_table={"overflowX": "auto"},
                columns=[{"name": c, "id": c, "type": "numeric",
                          "format": {"specifier": ".2%" if c == "rate" else ",.0f"}}
                         for c in TABLE_COLS],
            ),
        ]),
    ]),
])


# ---------------------------------------------------------------- 4. callback
@app.callback(
    Output("afford", "children"),
    Output("wealth", "figure"),
    Output("costs", "figure"),
    Output("table", "data"),
    [Input(f[0], "value") for f in FIELDS] + [Input("flags", "value"), Input("scenario", "value")],
)
def update(*args):
    *values, flags, scenario = args
    if any(v is None for v in values):      # a box is empty while the user is typing
        raise PreventUpdate

    kwargs = {}
    for (fid, _, _, is_pct), v in zip(FIELDS, values):
        v = v / 100 if is_pct else v
        kwargs[fid] = int(v) if fid in INT_FIELDS else v
    base = replace(DEFAULTS, **kwargs, first_buyer="first" in flags, married="married" in flags)

    results = {name: simulate(replace(base, **s)) for name, s in SCENARIOS.items()}

    ratio = affordability(base)
    afford = [
        html.B("Affordability: "),
        f"{ratio:.0%} of gross income — {'OK' if ratio <= 1/3 else 'above the 33% limit'}",
        html.Br(),
        html.B("Equity: "),
        f"{base.equity_pct:.0%} — {'OK' if base.equity_pct >= 0.2 else 'below the 20% minimum'}",
    ]

    wealth = go.Figure()
    for name, df in results.items():
        wealth.add_scatter(x=df.year, y=df.buy_minus_rent, name=name, mode="lines")
    wealth.add_hline(y=0, line_dash="dot")
    wealth.update_layout(title="Buy minus rent: difference in net wealth (CHF)",
                         yaxis_tickformat=",.0f", hovermode="x unified")

    df = results[scenario]
    costs = go.Figure()
    for col in ["interest", "maintenance", "amortisation", "tax_effect"]:
        costs.add_bar(x=df.year, y=df[col], name=col)
    costs.add_scatter(x=df.year, y=df.rent, name="rent", mode="lines+markers")
    costs.update_layout(barmode="relative", title=f"Annual owner cash flows vs rent — {scenario}",
                        yaxis_tickformat=",.0f")

    return afford, wealth, costs, df[TABLE_COLS].to_dict("records")


if __name__ == "__main__":
    # Local development only; in production gunicorn serves `server`
    app.run(debug=os.getenv("DASH_DEBUG", "1") == "1")
