"""
Home page — the interactive dashboard.

Uses the standalone `@callback` decorator rather than `@app.callback`: this
module is imported by Dash's page scan *while app.py is still executing*
(before the `app` variable exists), so it can only import names that are
already defined earlier in app.py — see the note at the top of app.py.
"""
from dataclasses import replace

import dash
import plotly.graph_objects as go
from dash import Input, Output, callback, dash_table, dcc, html
from dash.exceptions import PreventUpdate

from app import CHART_BG, CHART_FONT, DEFAULTS, PLOT_TEMPLATE, SCENARIOS, affordability, simulate

dash.register_page(__name__, path="/", name="Explorer")

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


def field(fid, label, step, is_pct):
    value = getattr(DEFAULTS, fid) * (100 if is_pct else 1)
    return html.Div([
        html.Label(label),
        dcc.Input(id=fid, type="number", value=round(value, 4), step=step,
                  debounce=True, className="field-input"),
    ], className="field")


TABLE_COLS = ["year", "rate", "debt", "interest", "amortisation", "pillar3a",
              "tax_effect", "owner_cash", "rent", "owner_wealth", "renter_wealth"]


def _col_format(c):
    if c == "rate":
        return {"specifier": ".2%"}
    if c == "year":
        return {"specifier": "d"}          # no thousands separator on a year
    return {"specifier": ",.0f"}


layout = html.Div(className="layout-grid", children=[
    html.Div(className="card", children=[
        html.H4("Assumptions"),
        *[field(*f) for f in FIELDS],
        dcc.Checklist(id="flags", value=["first", "married"], className="flags-checklist", options=[
            {"label": " First-time buyer", "value": "first"},
            {"label": " Married", "value": "married"},
        ]),
    ]),
    html.Div(className="main-col", children=[
        html.Div(className="card", children=[
            html.H4("Affordability"),
            html.Div(id="afford"),
        ]),
        html.Div(className="card", children=[
            html.H4("Net wealth: buy vs rent"),
            dcc.Graph(id="wealth"),
        ]),
        html.Div(className="card", children=[
            html.H4("Annual cash flows"),
            dcc.RadioItems(id="scenario", className="scenario-picker", inline=True,
                            options=list(SCENARIOS), value="Fixed · direct"),
            dcc.Graph(id="costs"),
        ]),
        html.Div(className="card", children=[
            html.H4("Year-by-year detail"),
            dash_table.DataTable(
                id="table", page_size=15, style_table={"overflowX": "auto"},
                columns=[{"name": c, "id": c, "type": "numeric", "format": _col_format(c)}
                         for c in TABLE_COLS],
                style_header={"backgroundColor": "#1c2128", "color": "#f5f6f8", "fontWeight": 600,
                              "borderBottom": "2px solid #2a2f38", "textAlign": "right"},
                style_cell={"backgroundColor": "#161a20", "color": "#c7ccd4",
                            "padding": "8px 10px", "fontFamily": "inherit", "fontSize": 13,
                            "border": "none", "borderBottom": "1px solid #20242c", "textAlign": "right"},
                style_data_conditional=[
                    {"if": {"row_index": "odd"}, "backgroundColor": "#1a1f26"},
                ],
            ),
        ]),
    ]),
])


@callback(
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
    afford_ok = ratio <= 1/3
    equity_ok = base.equity_pct >= 0.2
    afford = html.Div([
        html.B("Affordability: "),
        f"{ratio:.0%} of gross income — {'OK' if afford_ok else 'above the 33% limit'}",
        html.Br(),
        html.B("Equity: "),
        f"{base.equity_pct:.0%} — {'OK' if equity_ok else 'below the 20% minimum'}",
    ], className=f"afford-box {'afford-ok' if afford_ok and equity_ok else 'afford-bad'}")

    wealth = go.Figure()
    for name, df in results.items():
        wealth.add_scatter(x=df.year, y=df.buy_minus_rent, name=name, mode="lines")
    wealth.add_hline(y=0, line_dash="dot")
    wealth.update_layout(template=PLOT_TEMPLATE, title="Buy minus rent: difference in net wealth (CHF)",
                         yaxis_tickformat=",.0f", hovermode="x unified", margin=dict(t=48),
                         paper_bgcolor=CHART_BG, plot_bgcolor=CHART_BG, font_color=CHART_FONT)

    df = results[scenario]
    costs = go.Figure()
    for col in ["interest", "maintenance", "amortisation", "tax_effect"]:
        costs.add_bar(x=df.year, y=df[col], name=col)
    costs.add_scatter(x=df.year, y=df.rent, name="rent", mode="lines+markers")
    costs.update_layout(template=PLOT_TEMPLATE, barmode="relative",
                        title=f"Annual owner cash flows vs rent — {scenario}",
                        yaxis_tickformat=",.0f", margin=dict(t=48),
                        paper_bgcolor=CHART_BG, plot_bgcolor=CHART_BG, font_color=CHART_FONT)

    return afford, wealth, costs, df[TABLE_COLS].to_dict("records")
