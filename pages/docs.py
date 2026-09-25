"""Documentation page — static content, no callback."""
import dash
from dash import dcc, html

dash.register_page(__name__, path="/docs", name="Documentation")

CONTENT = """
## About this tool

A calculator for comparing buying a home in Switzerland against renting an
equivalent one, over a number of years. Enter your own assumptions on the
left — price, income, rates, growth — and the results on the right update
as soon as you finish editing a field.

It's a personal, illustrative model, not financial or tax advice. Every
default number (rates, tax thresholds, Pillar 3a limits, ...) is a
placeholder — check it against current figures before relying on any result.

## Using the calculator

**Left column — your assumptions**, grouped into cards:

- **Property & purchase** — price, one-off purchase costs, your equity (down
  payment), and how fast you expect the property to appreciate.
- **Household & timing** — income, how many years to look ahead, and the
  year you'd start.
- **Rent & comparison** — the rent for an equivalent home, how fast rent
  grows, and the investment return assumed for whichever side — you or a
  hypothetical renter — ends up with spare cash to invest in a given year.
- **Fixed-rate schedule** and **SARON schedule** — the mortgage rate,
  entered in 5-year blocks rather than one flat number, so a future rate
  change can be modelled directly. Both scenarios are always calculated
  side by side; these set the assumptions each one runs on.
- **Second mortgage & Pillar 3a** — how much more the second mortgage costs
  than the first, the SARON bank margin, and your Pillar 3a settings.
- **Extra 1st-mortgage amortisation** — optional voluntary overpayments on
  the first mortgage, which is normally interest-only.
- **Costs & taxes** — maintenance, Nebenkosten, property tax, the imputed
  rent used for tax, your marginal tax rate, and the costs of eventually
  selling.
- **Flags** — whether you qualify as a first-time buyer and/or are married,
  which affects the post-2029 interest-deduction rules.

**Right column — the results:**

- **Affordability** — a quick pass/fail against the two standard Swiss bank
  rules: your notional mortgage cost must stay under a third of gross
  income, and your equity must be at least 20%. Also shows what you'd walk
  away with, after sale costs, if you sold in the final year.
- **Net wealth: buy vs rent** — the main chart. It plots, for all four
  scenarios at once (fixed/SARON × direct/indirect amortisation), how much
  further ahead — or behind — buying leaves you compared with renting, year
  by year. Above the dotted zero line, buying is ahead; below it, renting
  is ahead.
- **Annual cash flows** — pick one of the four scenarios above the chart to
  see its year-by-year cost breakdown (interest, maintenance, Nebenkosten,
  property tax, amortisation, tax effect) stacked against what renting
  would have cost that year.
- **Year-by-year detail** — the full table behind the charts, including how
  your wealth splits between equity tied up in the home and money held as
  investments.

## Swiss terms used here

- **Eigenmietwert (imputed rental value)** — Switzerland taxes homeowners on
  a notional rental income for living in their own home, but lets them
  deduct mortgage interest and maintenance in return. This is abolished
  from 1 January 2029; the calculator switches its tax treatment
  automatically at that calendar year, wherever it falls inside your
  horizon — not at your chosen start year. A first-time buyer's transitional
  interest deduction after 2029 is time-limited from *their purchase year*,
  even if that's before 2029: buying in, say, 2027 already uses up part of
  that 10-year window before the deduction itself starts applying.
- **SARON** — the reference rate Swiss variable/short-fixed mortgages are
  priced from; the bank adds its own margin on top.
- **First vs second mortgage** — Swiss mortgages are split in two: the
  first covers up to two-thirds of the property's value and is typically
  never paid down; the second (anything above that) must be repaid to zero
  within 15 years, and usually carries a slightly higher rate.
- **Direct vs indirect amortisation** — "direct" pays down the second
  mortgage in cash each year. "Indirect" instead pays the same amount into
  a Pillar 3a account, keeping the mortgage (and its deductible interest)
  higher for longer. The second mortgage still has to be repaid by the end
  of the mandatory schedule either way: this calculator settles it with a
  lump-sum Pillar 3a withdrawal once the 15 years are up, rather than
  leaving it on the books indefinitely. Any 3a withdrawal tax on that
  lump sum isn't modelled.
- **Nebenkosten** — the running costs of a home besides mortgage and
  maintenance: heating, building insurance, refuse collection, and similar.
- **Grundstückgewinnsteuer** — the cantonal tax on the gain if you sell,
  applied here to what the property has appreciated over your original
  purchase price. Real schedules also depend on how long you've owned the
  property — typically a surcharge for a quick flip, tapering to a discount
  the longer you hold. This calculator applies a rough version of that
  shape rather than one specific canton's exact table.

## What this tool doesn't account for

- A single flat marginal tax rate, rather than Switzerland's actual
  progressive brackets.
- No wealth tax, and no tax on withdrawing Pillar 3a at retirement.
- The renter's own Pillar 3a isn't modelled — only the owner's.
- Cantonal rules vary considerably (property tax, capital gains tax rate,
  how imputed rent is calculated); the defaults are generic placeholders,
  not your canton's actual rules.

---

*This is a personal learning project, not financial advice. Check every
default number — rates, tax thresholds, Pillar 3a limits — against current
figures before drawing any real conclusion from it.*
"""

layout = html.Div(className="card docs-card", children=[
    dcc.Markdown(CONTENT, className="docs-markdown"),
])
