# Swiss home financing explorer

[![Tests](https://github.com/gkatharopo/swiss-mortgage-explorer/actions/workflows/tests.yml/badge.svg)](https://github.com/gkatharopo/swiss-mortgage-explorer/actions/workflows/tests.yml)

An interactive Dash app for comparing, in a Swiss context:

- **Buying vs renting**, as the difference in net wealth over time
- **SARON vs fixed-rate mortgages**, each entered as a rate schedule (one value per 5-year period) rather than a single flat number
- **Direct vs indirect amortisation**, where indirect goes through Pillar 3a
- **First vs second mortgage pricing**, with a configurable premium on the second mortgage
- **Voluntary extra amortisation** of the (normally interest-only) first mortgage, also as a per-5-year schedule
- **The cost of actually selling**: sale fees and cantonal capital gains tax, priced into a "net of sale" wealth figure alongside the mark-to-market one

**Live demo:** _add your Render URL here_

## What it models

- Bank affordability rules of thumb: at least 20% equity; interest at a notional 5%, plus 1% maintenance and amortisation, must stay within one third of gross income.
- The second mortgage (above 2/3 loan-to-value) is amortised over 15 years, either directly or indirectly through Pillar 3a; the first mortgage is interest-only unless voluntary extra amortisation is set.
- Nebenkosten (`nebenkosten_pct`): heating, building insurance, refuse, common-area electricity — a running cost distinct from the maintenance/reserve fund, and not tax-deductible.
- Cantonal annual property tax (`property_tax_pct`), where a canton levies one, as a flat % of property value.
- Tax treatment around the abolition of the imputed rental value (Eigenmietwert), which takes effect on 1 January 2029:
  - **Until end-2028:** the imputed rental value is taxed, and mortgage interest and maintenance are deductible.
  - **From 2029:** neither is deductible, apart from the first-time-buyer interest deduction (up to CHF 10k married / CHF 5k single, reduced by 10% a year over 10 years).
- The renter invests the down payment and purchase costs, plus each year's difference between the owner's total costs and rent.
- A "net of sale" wealth figure: sale fees plus capital gains tax on the gain over the purchase price, as if the property were sold that year — shown alongside the mark-to-market figure used for the main chart. The capital gains rate itself is adjusted by `holding_period_multiplier()` in `model.py`: a surcharge for a quick flip (<2 years), tapering to a discount the longer the property's held — illustrative of typical cantonal practice (e.g. Zürich), not a specific canton's real table.
- The first-time-buyer interest deduction's 10-year phase-out is counted from the purchase year (`start_year`), not from 2029 — confirmed against post-referendum guidance: a purchase made before 2029 has already burned down part of its 10-year window by the time the deduction regime takes effect.

## Simplifications

A single marginal tax rate. No wealth tax or Pillar 3a withdrawal tax. The renter's own Pillar 3a is not modelled. Default rates are placeholders, not market quotes.
**This is a learning project, not financial advice.**

## Architecture

```
model.py: Params (frozen dataclass)  ->  simulate()  ->  pandas DataFrame
                   ^                      pure model logic,         |
                   |                      no Dash imports           v
             Dash callback  <-------------------------------  figures + table
```

`model.py` holds `Params`, `simulate()` and `affordability()` — no Dash imports, so it's unit-tested directly (see `tests/`) without a browser, and `app.py`, every page module, and the tests all import straight from it. `app.py` is just the Dash app shell: `Dash(..., use_pages=True)`, the nav bar, `dash.page_container`. `pages/home.py` (the dashboard, at `/`) and `pages/docs.py` (at `/docs`) are auto-imported from the `pages/` folder by `use_pages=True`; page modules use the standalone `@callback` decorator rather than `@app.callback`, since a page was never meant to reach back into the `app` object — it registers against Dash's page-agnostic callback registry instead.

### Design note: pattern-matching callbacks

The 3 rate/amortisation schedules (10 five-year buckets each = 30 inputs) use Dash's pattern-matching ids — `{"type": "bucket", "sid": ..., "i": ...}` — rather than 30 individually-named ones. The main callback declares a single `Input({"type": "bucket", "sid": ALL, "i": ALL}, "value")` (+ a matching `State(..., "id")` to know which value belongs to which bucket) instead of 30 positional `Input`s, and the two clientside callbacks that add thousands separators to the CHF-denominated inputs use the same mechanism to cover all 14 currency fields in 2 callbacks instead of 14. This is the standard Dash idiom for "N near-identical inputs" — worth knowing cold for anyone building a Dash app with a variable or large number of like-shaped inputs.

### Design note: symmetric investing

Each year, whichever side — owner or renter — spent less on housing that year is credited with investing the difference, at its own independent return rate (`invest_return` for the renter, `owner_invest_return` for the owner). An earlier version of this model only tracked the renter's pot, so a year where owning was cheaper than renting silently vanished instead of crediting the owner — worth flagging as the kind of subtle asymmetry that's easy to miss in a naive buy-vs-rent calculator.

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python app.py            # http://127.0.0.1:8050
pytest                   # run the tests
ruff check .             # lint — same check CI runs on every push
```

## CI

`.github/workflows/tests.yml` runs `ruff check .` and `pytest` on every push and pull request. `pyproject.toml` pins the ruff rule set deliberately (pyflakes + pycodestyle errors) rather than accepting its full default — which also flags stylistic choices like `dict(...)` for Plotly's kwargs-style figure properties as errors.

## Deploy

`render.yaml` deploys the app to [Render](https://render.com) as a web service. In production, gunicorn serves the Flask server that sits underneath Dash (`app:server`), not Dash's development server.
