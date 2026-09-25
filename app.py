"""
Swiss home financing explorer — Dash app shell
Buy vs rent · SARON vs fixed · direct vs indirect amortisation

Architecture (worth saying out loud in the interview):
  1. model.py       – Params, simulate(), affordability(): pure logic, no Dash imports
  2. app.py          – this file: creates the Dash app, nav bar, page_container
  3. pages/home.py   – the dashboard: layout, callback (registered at path "/")
  4. pages/docs.py   – a static documentation page (registered at path "/docs")

Page modules use the standalone `@callback` decorator rather than `@app.callback` —
the normal pattern for a Dash multi-page app, since `use_pages=True` imports every
file under pages/ itself, so a page module was never meant to reach back into the
`app` object; it registers callbacks against Dash's page-agnostic callback registry
instead, which gets wired up once every page has been collected.
"""
import os

import dash
from dash import Dash, dcc, html

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
