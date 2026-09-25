"""
Home page — the interactive dashboard.

Uses the standalone `@callback` decorator rather than `@app.callback` — the normal
Dash multi-page pattern, since `use_pages=True` imports this module itself, so it
was never meant to import the `app` object back; see the note in app.py.
"""
import json
from dataclasses import replace

import dash
import plotly.graph_objects as go
from dash import ALL, Input, Output, State, callback, dash_table, dcc, html

from model import BUCKET_YEARS, DEFAULTS, N_BUCKETS, SCENARIOS, affordability, simulate

dash.register_page(__name__, path="/", name="Explorer")

# Chart theme — only this page renders figures, so these constants live here rather
# than in a shared module. Categorical colors are the dataviz skill's validated
# 8-hue dark-mode set, in fixed order, re-validated against this app's own card
# surface (#161a20) with scripts/validate_palette.js — never cycle these.
PLOT_TEMPLATE = "plotly_dark"
CHART_BG = "#161a20"          # matches --card in assets/style.css
CHART_FONT = "#c7ccd4"        # matches --text in assets/style.css
CHART_MUTED = "#8b93a1"       # matches --muted in assets/style.css; gridlines/reference lines
SCENARIO_COLORS = {
    "Fixed · direct": "#3987e5",
    "Fixed · indirect": "#d95926",
    "SARON · direct": "#199e70",
    "SARON · indirect": "#c98500",
}
COST_COLORS = {
    "interest": "#3987e5",
    "maintenance": "#d95926",
    "nebenkosten": "#199e70",
    "property_tax": "#c98500",
    "amortisation": "#d55181",
    "extra_amortisation": "#008300",
    "tax_effect": "#9085e9",
}
RENT_LINE_COLOR = "#f5f6f8"   # matches --heading; a neutral benchmark, not a cost category

# (field id, label, step, entered as percent?, help text)
FIELDS = [
    ("price", "Purchase price (CHF)", 10_000, False,
     "The property's purchase price, before any purchase costs."),
    ("purchase_cost_pct", "Purchase costs (%)", 0.1, True,
     "One-off notary, land registry and transfer costs, as a % of price — paid from equity, not financed."),
    ("equity_pct", "Equity (%)", 1, True,
     "Down payment as a % of price. Swiss banks require at least 20%, of which at least 10 percentage "
     "points must come from sources other than the pension fund (Pillar 2)."),
    ("house_growth", "Property growth (%/yr)", 0.1, True,
     "Assumed annual growth in the property's value."),
    ("gross_income", "Gross household income (CHF)", 5_000, False,
     "Gross household income, used for the affordability check below."),
    ("horizon", "Horizon (years)", 1, False,
     "How many years to simulate."),
    ("start_year", "Start year", 1, False,
     "Calendar year the mortgage starts — determines which Eigenmietwert tax rules apply (pre/post-2029)."),
    ("monthly_rent", "Equivalent rent (CHF/month)", 100, False,
     "Rent for an equivalent flat, assumed to already include Nebenkosten (an all-in / Bruttomiete figure)."),
    ("rent_growth", "Rent growth (%/yr)", 0.1, True,
     "Assumed annual growth in rent."),
    ("invest_return", "Renter's return (%/yr)", 0.1, True,
     "Annual return on the renter's invested capital: the buyer's equity + purchase costs, plus any "
     "year the renter is credited with investing the cost saving. Independent from the owner's rate below."),
    ("owner_invest_return", "Owner's investment return (%/yr)", 0.1, True,
     "Annual return on the owner's own invested capital: any year owning is cheaper than renting, the "
     "owner is credited with investing the saving at this rate instead of the renter's."),
    ("maintenance_pct", "Maintenance / reserve fund (%/yr)", 0.1, True,
     "Repairs and reserve-fund contributions, usually between 0.5% and 1% of property value per year."),
    ("nebenkosten_pct", "Nebenkosten: heating, insurance, refuse (%/yr)", 0.05, True,
     "Heating, building insurance, refuse collection, common-area electricity — running costs distinct "
     "from the maintenance/reserve fund above."),
    ("property_tax_pct", "Cantonal property tax (%/yr)", 0.05, True,
     "Liegenschaftssteuer, an annual property-value tax — only levied in some cantons (0 in most)."),
    ("emw_pct_of_rent", "Imputed rent (% of rent)", 5, True,
     "Imputed rental value (Eigenmietwert) as a % of the equivalent market rent — taxed as income until "
     "the 2029 reform abolishes it."),
    ("marginal_tax", "Marginal tax rate (%)", 1, True,
     "Combined federal/cantonal/communal marginal income tax rate, applied to each year's taxable-income effect."),
    ("sale_fee_pct", "Sale fee if sold (%)", 0.5, True,
     "Broker, notary and marketing costs if the property were sold, as a % of the sale price."),
    ("capital_gains_tax_pct", "Capital gains tax if sold (%)", 1, True,
     "Grundstückgewinnsteuer: cantonal tax on the gain over the purchase price, if the property were sold. "
     "Adjusted for how long the property's been held — see the Documentation page."),
    ("second_mortgage_premium", "2nd mortgage premium (+%)", 0.05, True,
     "How much higher the second mortgage's rate is than the first's — banks typically price it 0.5-1% higher."),
    ("saron_margin", "SARON bank margin (%)", 0.05, True,
     "The bank's margin added on top of the SARON reference rate, for the SARON scenarios."),
    ("pillar3a_cap", "Pillar 3a annual cap (CHF)", 100, False,
     "Maximum annual Pillar 3a contribution eligible for indirect amortisation, per person — enter the "
     "current official limit. Automatically doubled when 'Married' is checked, for two accounts."),
    ("pillar3a_return", "Pillar 3a return (%/yr)", 0.1, True,
     "Assumed annual return within the Pillar 3a account."),
]
FIELD_BY_ID = {f[0]: f for f in FIELDS}
INT_FIELDS = {"horizon", "start_year"}

# How the FIELDS above are grouped into sidebar cards.
CATEGORIES = [
    ("Property & purchase", ["price", "purchase_cost_pct", "equity_pct", "house_growth"]),
    ("Household & timing", ["gross_income", "horizon", "start_year"]),
    ("Rent & comparison", ["monthly_rent", "rent_growth", "invest_return", "owner_invest_return"]),
    ("Second mortgage & Pillar 3a", ["second_mortgage_premium", "saron_margin",
                                      "pillar3a_cap", "pillar3a_return"]),
    ("Costs & taxes", ["maintenance_pct", "nebenkosten_pct", "property_tax_pct", "emw_pct_of_rent",
                        "marginal_tax", "sale_fee_pct", "capital_gains_tax_pct"]),
]

# (schedule id, card title, step, entered as percent?, help text) — one input per 5-year bucket
SCHEDULES = [
    ("fixed_rate_schedule", "Fixed-rate schedule (%/yr)", 0.05, True,
     "Fixed mortgage rate for each 5-year period of the horizon, used by the 'Fixed' scenarios. "
     "Set every bucket to the same value for a flat rate, or vary them to model a future rate change."),
    ("saron_schedule", "SARON schedule (%/yr, before margin)", 0.05, True,
     "SARON reference rate for each 5-year period, before the bank's margin, used by the 'SARON' "
     "scenarios. Vary the buckets to model a rate shock at a specific point in the horizon."),
    ("extra_amort_schedule", "Extra 1st-mortgage amortisation (CHF/month)", 50, False,
     "Optional voluntary overpayment on the first mortgage, per 5-year period — the first mortgage is "
     "otherwise interest-only and never amortised, unlike the second mortgage's mandatory schedule."),
]


def _is_currency(fid, is_pct):
    """CHF amounts get thousands separators; percentages and plain counts (years) don't."""
    return not is_pct and fid not in INT_FIELDS


def _field_dom_id(fid, is_pct):
    # Currency scalar fields get a pattern-matchable dict id so one clientside callback
    # (below) can reformat all of them, instead of one callback per field.
    return {"type": "currency-field", "id": fid} if _is_currency(fid, is_pct) else fid


def _to_float(v):
    """Currency fields arrive as comma-formatted strings (e.g. "1,400,000"); everything
    else arrives as a plain number already, straight from a type="number" input. Falls
    back to None (which the caller treats as "use the default") on unparseable text,
    since a currency field being type="text" means a user can type anything into it."""
    if isinstance(v, str):
        v = v.replace(",", "").strip()
        if not v:
            return None
        try:
            return float(v)
        except ValueError:
            return None
    return v


def _currency_input(elem_id, step, value):
    # HTML's native type="number" strips commas outright, so a comma-formatted CHF amount
    # needs a plain text input instead, reformatted by a clientside callback (below) on blur.
    return dcc.Input(id=elem_id, type="text", inputMode="numeric", value=f"{value:,.0f}", step=step,
                      debounce=True, className="field-input")


def _numeric_input(elem_id, step, value):
    return dcc.Input(id=elem_id, type="number", value=round(value, 4), step=step,
                      debounce=True, className="field-input")


def _input_for(elem_id, is_currency, step, value):
    return _currency_input(elem_id, step, value) if is_currency else _numeric_input(elem_id, step, value)


def field(fid, label, step, is_pct, help_text):
    value = getattr(DEFAULTS, fid) * (100 if is_pct else 1)
    input_el = _input_for(_field_dom_id(fid, is_pct), _is_currency(fid, is_pct), step, value)
    return html.Div([
        html.Label(label),
        html.P(help_text, className="field-help"),
        input_el,
    ], className="field")


def category_card(title, ids):
    return html.Div(className="card", children=[
        html.H4(title),
        *[field(*FIELD_BY_ID[fid]) for fid in ids],
    ])


def schedule_card(sid, title, step, is_pct, help_text):
    values = getattr(DEFAULTS, sid)
    is_curr = _is_currency(sid, is_pct)
    buckets = []
    for i in range(N_BUCKETS):
        lo = i * BUCKET_YEARS
        v = values[i] * (100 if is_pct else 1)
        # Pattern-matching id: {"type": "bucket", "sid": ..., "i": ...} for every bucket,
        # currency or not — lets both the main callback and the reformat callback below
        # address "all 30 buckets" as one Input each, instead of 30 separate ones.
        input_el = _input_for({"type": "bucket", "sid": sid, "i": i}, is_curr, step, v)
        buckets.append(html.Div([
            html.Label(f"{lo}–{lo + BUCKET_YEARS}y"),
            input_el,
        ], className="bucket-field"))
    # Collapsed by default: these three schedule cards are the least commonly touched
    # (most sessions leave a flat rate / no extra amortisation), and 10 bucket inputs
    # each make the sidebar much longer than the more-common cards around them.
    return html.Details(className="card collapsible-card", children=[
        html.Summary(title),
        html.P(help_text, className="field-help"),
        html.Div(buckets, className="bucket-grid"),
    ])


TABLE_COLS = ["year", "rate_first", "rate_second", "debt", "interest", "maintenance",
              "nebenkosten", "property_tax", "amortisation", "extra_amortisation",
              "tax_effect", "owner_cash", "rent", "home_equity", "owner_investments",
              "owner_wealth", "owner_wealth_net_of_sale", "renter_wealth"]

COLUMN_LABELS = {
    "year": "Year",
    "rate_first": "IR 1st mortgage (%)",
    "rate_second": "IR 2nd mortgage (%)",
    "debt": "Total debt",
    "interest": "Annual amount due to interest",
    "maintenance": "Annual maintenance costs",
    "nebenkosten": "House annual running costs",
    "property_tax": "Property tax cost",
    "amortisation": "Amortization - obligatory",
    "extra_amortisation": "Amortization - voluntary",
    "tax_effect": "Net tax effect (+ = pay more)",
    "owner_cash": "Annual cost of owning",
    "rent": "Annual renting cost",
    "home_equity": "Home equity",
    "owner_investments": "Home owner investments",
    "owner_wealth": "Home owner wealth",
    "owner_wealth_net_of_sale": "Home owner wealth net of sale",
    "renter_wealth": "Renter wealth",
}


def _col_format(c):
    if c in ("rate_first", "rate_second"):
        return {"specifier": ".2%"}
    if c == "year":
        return {"specifier": "d"}          # no thousands separator on a year
    return {"specifier": ",.0f"}


layout = html.Div(className="layout-grid", children=[
    html.Div(className="sidebar-col", children=[
        category_card(*CATEGORIES[0]),
        category_card(*CATEGORIES[1]),
        category_card(*CATEGORIES[2]),
        schedule_card(*SCHEDULES[0]),
        schedule_card(*SCHEDULES[1]),
        category_card(*CATEGORIES[3]),
        schedule_card(*SCHEDULES[2]),
        category_card(*CATEGORIES[4]),
        html.Div(className="card", children=[
            html.H4("Flags"),
            dcc.Checklist(id="flags", value=["first", "married"], className="flags-checklist", options=[
                {"label": " First-time buyer", "value": "first"},
                {"label": " Married", "value": "married"},
            ]),
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
                columns=[{"name": COLUMN_LABELS[c], "id": c, "type": "numeric", "format": _col_format(c)}
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

# --------------------------------------------------------------- thousands-separator reformat
# Reformat a currency field with commas once the user finishes editing it (blur fires
# n_blur; a component's "value" can't be both this callback's Output and Input at once).
# Two pattern-matching callbacks cover all 14 currency inputs, instead of one per field:
# one over the 4 scalar currency fields, one over the bucket grid (filtered in JS to just
# the currency schedule — fixed/SARON-rate buckets are percentages, not CHF amounts).
_COMMA_FORMAT_FIELDS_JS = """
function(nBlurs, values) {
    return values.map(function(v) {
        if (v === null || v === undefined || v === '') { return window.dash_clientside.no_update; }
        var num = parseFloat(String(v).replace(/,/g, ''));
        if (isNaN(num)) { return window.dash_clientside.no_update; }
        return num.toLocaleString('en-US', {maximumFractionDigits: 0});
    });
}
"""
dash.clientside_callback(
    _COMMA_FORMAT_FIELDS_JS,
    Output({"type": "currency-field", "id": ALL}, "value"),
    Input({"type": "currency-field", "id": ALL}, "n_blur"),
    State({"type": "currency-field", "id": ALL}, "value"),
)

_CURRENCY_SCHEDULE_SID = next(sid for sid, _, _, is_pct, _ in SCHEDULES if _is_currency(sid, is_pct))
_COMMA_FORMAT_BUCKETS_JS = """
function(nBlurs, values, ids) {
    return ids.map(function(id, idx) {
        if (id.sid !== %s) { return window.dash_clientside.no_update; }
        var v = values[idx];
        if (v === null || v === undefined || v === '') { return window.dash_clientside.no_update; }
        var num = parseFloat(String(v).replace(/,/g, ''));
        if (isNaN(num)) { return window.dash_clientside.no_update; }
        return num.toLocaleString('en-US', {maximumFractionDigits: 0});
    });
}
""" % json.dumps(_CURRENCY_SCHEDULE_SID)
dash.clientside_callback(
    _COMMA_FORMAT_BUCKETS_JS,
    Output({"type": "bucket", "sid": ALL, "i": ALL}, "value"),
    Input({"type": "bucket", "sid": ALL, "i": ALL}, "n_blur"),
    State({"type": "bucket", "sid": ALL, "i": ALL}, "value"),
    State({"type": "bucket", "sid": ALL, "i": ALL}, "id"),
)


@callback(
    Output("afford", "children"),
    Output("wealth", "figure"),
    Output("costs", "figure"),
    Output("table", "data"),
    [Input(_field_dom_id(f[0], f[3]), "value") for f in FIELDS]
    + [Input({"type": "bucket", "sid": ALL, "i": ALL}, "value"),
       State({"type": "bucket", "sid": ALL, "i": ALL}, "id")]
    + [Input("flags", "value"), Input("scenario", "value")],
)
def update(*args):
    n_scalar = len(FIELDS)
    scalar_values = args[:n_scalar]
    bucket_values = args[n_scalar]      # one flat list covering all 30 buckets
    bucket_ids = args[n_scalar + 1]     # matching list of {"type":"bucket","sid":...,"i":...}
    flags, scenario = args[n_scalar + 2], args[n_scalar + 3]

    # A field reads as None while its box is briefly empty mid-edit. Falling back to that
    # field's own default (rather than blocking the whole update, as with ~50 inputs on
    # this page one blank box anywhere would otherwise freeze every plot) keeps the rest
    # of the dashboard responsive to whatever the user did just change.
    schedule_raw = {sid: [None] * N_BUCKETS for sid, *_ in SCHEDULES}
    for id_dict, v in zip(bucket_ids, bucket_values):
        schedule_raw[id_dict["sid"]][id_dict["i"]] = _to_float(v)

    schedules = {}
    for sid, _, _, is_pct, _ in SCHEDULES:
        defaults = getattr(DEFAULTS, sid)
        schedules[sid] = tuple(
            (defaults[i] if v is None else (v / 100 if is_pct else v))
            for i, v in enumerate(schedule_raw[sid])
        )

    kwargs = dict(schedules)
    for (fid, _, _, is_pct, _), v in zip(FIELDS, scalar_values):
        v = _to_float(v)
        if v is None:
            kwargs[fid] = getattr(DEFAULTS, fid)
            continue
        v = v / 100 if is_pct else v
        kwargs[fid] = int(v) if fid in INT_FIELDS else v
    kwargs["horizon"] = max(1, kwargs["horizon"])    # a 0-year simulation has no rows to plot
    base = replace(DEFAULTS, **kwargs, first_buyer="first" in flags, married="married" in flags)

    results = {name: simulate(replace(base, **s)) for name, s in SCENARIOS.items()}
    df = results[scenario]
    final = df.iloc[-1]

    ratio = affordability(base)
    afford_ok = ratio <= 1/3
    equity_ok = base.equity_pct >= 0.2
    afford = html.Div([
        html.B("Affordability: "),
        f"{ratio:.0%} of gross income — {'OK' if afford_ok else 'above the 33% limit'}",
        html.Br(),
        html.B("Equity: "),
        f"{base.equity_pct:.0%} — {'OK' if equity_ok else 'below the 20% minimum'}",
        html.Br(),
        html.B("Net proceeds if sold in final year: "),
        f"{final.owner_wealth_net_of_sale:,.0f} CHF ({scenario}, after sale fee + capital gains tax)",
    ], className=f"afford-box {'afford-ok' if afford_ok and equity_ok else 'afford-bad'}")

    wealth = go.Figure()
    for name, res in results.items():
        wealth.add_scatter(x=res.year, y=res.buy_minus_rent, name=name, mode="lines",
                            line=dict(color=SCENARIO_COLORS[name], width=2))
    wealth.add_hline(y=0, line_dash="dot", line_color=CHART_MUTED)

    # Mark where the selected scenario's line actually crosses from renting-ahead to
    # buying-ahead (or back) — the single most useful thing to read off this chart, and
    # otherwise only discoverable by hovering along the line looking for a sign flip.
    sel_years, sel_vals = df.year.tolist(), df.buy_minus_rent.tolist()
    crossover_year = next((sel_years[i] for i in range(1, len(sel_vals))
                            if (sel_vals[i - 1] < 0) != (sel_vals[i] < 0)), None)
    if crossover_year is not None:
        wealth.add_vline(x=crossover_year, line_dash="dash", line_color=SCENARIO_COLORS[scenario],
                          annotation_text=f"{scenario} crosses over — {crossover_year}",
                          annotation_position="top", annotation_font_color=SCENARIO_COLORS[scenario])
    # The imputed-rental-value tax regime changes at a fixed calendar year, not a fixed
    # point in the horizon — worth flagging since it's an invisible cliff in the model.
    if sel_years[0] <= 2029 <= sel_years[-1]:
        wealth.add_vline(x=2029, line_dash="dot", line_color=CHART_MUTED,
                          annotation_text="2029: EMW abolished", annotation_position="bottom",
                          annotation_font_color=CHART_MUTED)

    wealth.update_layout(template=PLOT_TEMPLATE, title="Buy minus rent: difference in net wealth (CHF)",
                         xaxis_title="Year", yaxis_title="Buy minus rent (CHF)",
                         yaxis_tickformat=",.0f", hovermode="x unified", margin=dict(t=48),
                         paper_bgcolor=CHART_BG, plot_bgcolor=CHART_BG, font_color=CHART_FONT)

    costs = go.Figure()
    for col in ["interest", "maintenance", "nebenkosten", "property_tax",
                "amortisation", "extra_amortisation", "tax_effect"]:
        costs.add_bar(x=df.year, y=df[col], name=COLUMN_LABELS[col],
                       marker=dict(color=COST_COLORS[col], line=dict(color=CHART_BG, width=1)))
    costs.add_scatter(x=df.year, y=df.rent, name=COLUMN_LABELS["rent"], mode="lines+markers",
                       line=dict(color=RENT_LINE_COLOR, width=2), marker=dict(size=6))
    costs.update_layout(template=PLOT_TEMPLATE, barmode="relative",
                        title=f"Annual owner cash flows vs rent — {scenario}",
                        xaxis_title="Year", yaxis_title="CHF per year",
                        yaxis_tickformat=",.0f", hovermode="x unified", margin=dict(t=48),
                        paper_bgcolor=CHART_BG, plot_bgcolor=CHART_BG, font_color=CHART_FONT)

    return afford, wealth, costs, df[TABLE_COLS].to_dict("records")
