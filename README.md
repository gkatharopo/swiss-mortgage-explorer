# Swiss home financing explorer

An interactive Dash app for comparing, in a Swiss context:

- **Buying vs renting**, as the difference in net wealth over time
- **SARON vs fixed-rate mortgages**, including a configurable rate shock
- **Direct vs indirect amortisation**, where indirect goes through Pillar 3a

**Live demo:** _add your Render URL here_

## What it models

- Bank affordability rules of thumb: at least 20% equity; interest at a notional 5%, plus 1% maintenance and amortisation, must stay within one third of gross income.
- The second mortgage (above 2/3 loan-to-value) is amortised over 15 years, either directly or indirectly through Pillar 3a.
- Tax treatment around the abolition of the imputed rental value (Eigenmietwert), which takes effect on 1 January 2029:
  - **Until end-2028:** the imputed rental value is taxed, and mortgage interest and maintenance are deductible.
  - **From 2029:** neither is deductible, apart from the first-time-buyer interest deduction (up to CHF 10k married / CHF 5k single, reduced by 10% a year over 10 years).
- The renter invests the down payment and purchase costs, plus each year's difference between the owner's total costs and rent.

## Simplifications

A single marginal tax rate. No wealth tax, capital gains tax, selling costs or Pillar 3a withdrawal tax. The renter's own Pillar 3a is not modelled. Default rates are placeholders, not market quotes.
**This is a learning project, not financial advice.**

## Architecture

```
Params (frozen dataclass)  ->  simulate()  ->  pandas DataFrame
         ^                      pure model logic,         |
         |                      no Dash imports           v
   Dash callback  <-------------------------------  figures + table
```

Keeping the model separate from the UI means it can be unit-tested without a browser (see `tests/`).

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python app.py            # http://127.0.0.1:8050
pytest                   # run the tests
```

## Deploy

`render.yaml` deploys the app to [Render](https://render.com) as a web service. In production, gunicorn serves the Flask server that sits underneath Dash (`app:server`), not Dash's development server.
