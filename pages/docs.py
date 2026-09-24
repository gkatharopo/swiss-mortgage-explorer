"""Documentation page — static content, no callback."""
import dash
from dash import dcc, html

dash.register_page(__name__, path="/docs", name="Documentation")

CONTENT = """
## Architecture

1. **`Params`** — a frozen dataclass holding every assumption (price, rates, tax,
   horizon, ...). Frozen so a scenario is always built with `dataclasses.replace`,
   never mutated in place.
2. **`simulate()`** — pure model logic. No Dash imports, so it's unit-tested
   directly (see `tests/test_model.py`) without spinning up a browser.
3. **`app.py`** — the model plus the Dash app shell: creates the `Dash` instance
   with `use_pages=True`, builds the nav bar, and renders `dash.page_container`.
4. **`pages/home.py`** — the interactive dashboard, registered at `/`.
5. **`pages/docs.py`** — this page, registered at `/docs`.

Page modules use the standalone `@callback` decorator rather than `@app.callback`,
because Dash imports every file in `pages/` *while `app.py` is still executing*
(before the `app` object exists) — so a page can't import `app` itself, only
names already defined above the `Dash(...)` call in `app.py`.

## What the model does

- Simulates a `horizon`-year mortgage: interest, maintenance, amortisation
  (direct or indirect via Pillar 3a), and the Swiss tax effect, year by year.
- Runs the same assumptions across four scenarios — fixed vs SARON rate,
  direct vs indirect amortisation — so they can be compared side by side.
- Compares the buyer's resulting net wealth against a renter's counterfactual:
  someone who never buys, invests what the buyer would have put down as
  equity, and keeps investing the difference whenever owning costs more than
  renting in a given year.

## Opportunity cost of the equity

A common gap in naive buy-vs-rent calculators: the equity tied up as a down
payment could have earned a return elsewhere, and if that's left out, buying
looks artificially cheap. This model prices it in explicitly:

```python
renter = equity + p.price * p.purchase_cost_pct   # renter's pot starts where
                                                     # the buyer's equity would go
...
owner_cash = interest + maintenance + pay + tax     # buyer's total cash cost this year
renter = renter * (1 + p.invest_return) + (owner_cash - rent)
```

Every year, the renter's portfolio compounds at `invest_return`, **and** if
owning costs more than renting that year, the renter is credited with
investing the difference too. So `renter_wealth` is the wealth of someone who
put the same capital to work in the market instead of a house — the
opportunity cost is the gap between `owner_wealth` and `renter_wealth`, which
is exactly what the "Net wealth: buy vs rent" chart plots.

## Deliberate simplifications

- One marginal tax rate applied to changes in taxable income.
- Tax regime: imputed rental value (*Eigenmietwert*) taxed, interest and
  maintenance deductible until end-2028. From 2029: no EMW, no maintenance or
  interest deduction, except the first-buyer interest deduction (CHF 10k
  married / 5k single, falling 10%/yr over 10 years; assumed counted from the
  purchase year — check against the final rules once passed).
- No capital gains tax, wealth tax, selling costs, or Pillar 3a withdrawal tax.
- Pillar 3a is only modelled for the owner's indirect amortisation. In
  reality a renter can also pay into 3a, so the fair 3a comparison is
  indirect vs direct amortisation, not buy vs rent.
- Affordability uses the standard Swiss bank rule of thumb: a 5% notional
  interest rate plus 1% maintenance plus amortisation, capped at a third of
  gross income — deliberately conservative and rate-independent, as banks
  use it to stress-test against rate rises.

## Deployment

`server = app.server` in `app.py` is the WSGI entry point gunicorn serves in
production (`render.yaml` runs `gunicorn app:server`). Locally,
`app.run(debug=...)` uses Dash's own dev server, controlled by the
`DASH_DEBUG` environment variable (defaults to on).

---

*This is a learning project built to practise Dash, not financial advice.
Every placeholder rate (SARON, fixed rate, Pillar 3a cap, ...) should be
checked against current figures before drawing any real conclusion from it.*
"""

layout = html.Div(className="card docs-card", children=[
    dcc.Markdown(CONTENT, className="docs-markdown"),
])
