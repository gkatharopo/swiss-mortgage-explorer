# Swiss home financing explorer

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
- A "net of sale" wealth figure: sale fees plus capital gains tax on the gain over the purchase price, as if the property were sold that year — shown alongside the mark-to-market figure used for the main chart.

## Simplifications

A single marginal tax rate. No wealth tax or Pillar 3a withdrawal tax. The renter's own Pillar 3a is not modelled. Default rates are placeholders, not market quotes.
**This is a learning project, not financial advice.**

## Architecture

```
Params (frozen dataclass)  ->  simulate()  ->  pandas DataFrame
         ^                      pure model logic,         |
         |                      no Dash imports           v
   Dash callback  <-------------------------------  figures + table
```

Keeping the model separate from the UI means it can be unit-tested without a browser (see `tests/`).

`app.py` builds the model, the `Params` dataclass and `simulate()`, then the `Dash(..., use_pages=True)` app shell. `pages/home.py` (the dashboard, at `/`) and `pages/docs.py` (this page's source, at `/docs`) are auto-imported from the `pages/` folder — but that import happens *while `app.py` is still executing*, before the `app` object exists, so page modules use the standalone `@callback` decorator rather than `@app.callback`, and can only import names defined above the `Dash(...)` call in `app.py`.

### Design note: symmetric investing

Each year, whichever side — owner or renter — spent less on housing that year is credited with investing the difference, at its own independent return rate (`invest_return` for the renter, `owner_invest_return` for the owner). An earlier version of this model only tracked the renter's pot, so a year where owning was cheaper than renting silently vanished instead of crediting the owner — worth flagging as the kind of subtle asymmetry that's easy to miss in a naive buy-vs-rent calculator.

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python app.py            # http://127.0.0.1:8050
pytest                   # run the tests
```

## Deploy

`render.yaml` deploys the app to [Render](https://render.com) as a web service. In production, gunicorn serves the Flask server that sits underneath Dash (`app:server`), not Dash's development server.
