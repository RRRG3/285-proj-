# Alloc8

> Stock portfolio suggestion engine — build, track, and stress-test a real portfolio in minutes with live prices, backtests, Monte Carlo forecasts, and a what-if workbench you can drag.

[![Tests](https://img.shields.io/badge/tests-55%20passing-4ade80?style=flat-square)]()
[![Coverage](https://img.shields.io/badge/coverage-65%25-58cbff?style=flat-square)]()
[![Python](https://img.shields.io/badge/python-3.10%2B-blue?style=flat-square)]()
[![License](https://img.shields.io/badge/license-MIT-lightgrey?style=flat-square)]()

**Alloc8** is a Flask web app for CMPE 285 (Software Engineering Processes, SJSU). Enter an amount and one or two investing strategies; the engine assigns stocks/ETFs, splits capital, shows live portfolio value, and tracks a five-day value trend.

---

## Table of contents

1. [Setup instructions](#setup-instructions)
2. [10 detailed test cases](#10-detailed-test-cases)
3. [Features](#features)
4. [How allocation works](#how-allocation-works)
5. [Risk profile](#risk-profile)
6. [Architecture](#architecture)
7. [Project layout](#project-layout)
8. [API reference](#api-reference)
9. [Configuration](#configuration)
10. [Testing](#testing)

---

## Setup instructions

### Requirements

- **Python 3.10 or newer** (`python3 --version`)
- **pip**
- Modern browser (Chrome, Firefox, or Safari)
- Internet access for live market quotes (yfinance)

### Run locally

1. Unzip or clone the project and open a terminal in the project folder.

2. Create a virtual environment and install dependencies:

```bash
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

3. Start the application:

```bash
python app.py
```

4. Open **`http://127.0.0.1:8080`** in your browser.

5. Dismiss the onboarding tour if it appears (it stays dismissed after the first visit).

The terminal prints the URL when the server starts (default port **8080**).

### Run with Docker

```bash
docker compose up
```

Then open **`http://127.0.0.1:8080`**.

### Repository

```bash
git clone https://github.com/RRRG3/285-proj-.git
cd 285-proj-
```

---

## 10 detailed test cases

Follow these steps to verify core and extended functionality. Complete [Setup instructions](#setup-instructions) first.

### Test Case 1: Generate Portfolio (Core Spec)

1. Enter `10000` in **Investment Amount (USD)**.
2. Click the strategy card **Growth Investing** (one strategy only).
3. Click **Run Portfolio Model**.
4. **Expected:** Results appear on the right. **Current Portfolio Value** is approximately **$10,000.00**. **Holdings** lists tickers (e.g. TSLA, NVDA, AMZN, META) with **shares**, **weight %**, and **dollar amounts** that sum to approximately $10,000. The **Strategies** meta line shows `Growth Investing`.

### Test Case 2: Minimum Investment Validation ($5,000)

1. Enter `3000` in the investment field.
2. Select **Index Investing**.
3. Click **Run Portfolio Model**.
4. **Expected:** Error message: **Minimum investment amount is $5,000.** No portfolio results panel.

### Test Case 3: Strategy Selection Limit (1–2 Strategies)

1. Enter `5000`.
2. Click **Ethical Investing**, then **Value Investing** (two selected).
3. Try to click a third strategy (e.g. **Quality Investing**).
4. **Expected:** Third selection is blocked; error: **You can select a maximum of 2 investment strategies.**
5. With only two selected, click **Run Portfolio Model**.
6. **Expected:** Holdings combine tickers from both strategies (deduplicated), with at least **3** positions.

### Test Case 4: Risk Profile Adjusts Allocation

**Run A — conservative:**

1. Enter `10000`, select **Quality Investing**.
2. Under **About You**, set Age `65`, Years until you need it `3`, Max drawdown `10`.
3. Click **Run Portfolio Model**.
4. Note **Cash Remainder** on Overview and the risk label pill next to **Live** (e.g. Conservative).

**Run B — aggressive:**

5. Keep `10000` and **Quality Investing**.
6. Under **About You**, set Age `25`, Years until you need it `25`, Max drawdown `50`.
7. Generate again.
8. **Expected:** Run B has a **lower cash remainder** and/or **more concentrated** top weights than Run A. The results header shows a risk label pill (e.g. Conservative vs Aggressive).

### Test Case 5: Five-Day Portfolio Trend (Weekly History)

1. Generate `10000` with **Index Investing**.
2. Stay on the **Overview** tab.
3. Scroll to **5-Day Portfolio Trend**.
4. **Expected:** A line chart with up to **5 date labels** and a **Portfolio Value** series. Hovering a point shows the **date** and **portfolio dollar value** (total portfolio, not per-ticker prices).

### Test Case 6: Stress Test Scenarios

1. Generate `10000` with **Growth Investing**.
2. Open the **Risk & Diversification** tab.
3. Scroll to **Stress Tests**.
4. **Expected:** At least **5** scenario cards, including **GFC 2008**, **COVID-19 Crash 2020**, dot-com, **2022 Inflation**, and **Black Monday**. Each shows **loss %**, **loss in dollars**, and a severity bar.

### Test Case 7: Compare Two Strategies

1. Open the **Compare** tab.
2. Set **Strategy A** to **Growth Investing** and **Strategy B** to **Index Investing**.
3. Ensure the investment field is `10000`, then click **Run side-by-side**.
4. **Expected:** Two columns/cards with ticker chips, 1Y backtest stats, and Monte Carlo median. **Best** badges mark the winner on Sharpe, return, max drawdown, or MC median where applicable.

### Test Case 8: Goal Tracker Probability

1. Generate any portfolio (e.g. `10000`, **Value Investing**).
2. Open the **What-If** tab.
3. In **Goal Tracker**, enter Target value `15000` and Time horizon `5` years.
4. Click **Estimate probability**.
5. **Expected:** A probability headline (e.g. “X% chance of reaching $15,000 in 5 years”) and supporting detail text. The Monte Carlo chart above may reference the goal.

### Test Case 9: Export Portfolio as CSV

1. After generating a portfolio, click **Download CSV** in the results header (next to **Copy share link**).
2. Open the downloaded `.csv` file.
3. **Expected:** Header rows (investment amount, strategies) and columns **Ticker, Name, Strategy, Weight %, Shares, Entry Price, Current Price, Invested, Current Value** matching the on-screen holdings.

### Test Case 10: Saved Portfolios Persist After Refresh

1. Generate `10000` with **Quality Investing**.
2. Wait for results; note tickers and total value.
3. In the left column under **Saved Portfolios**, confirm a new entry appears (strategy name and value).
4. Refresh the browser (`F5` or `Cmd+R`).
5. Click that entry in **Saved Portfolios**.
6. **Expected:** The same allocation reloads (same tickers, weights, and approximately $10,000 total). Charts and metrics repopulate.

---

## Features

### Assignment requirements

| Requirement | Implementation |
|---|---|
| Minimum **$5,000** investment | Validated in UI and API |
| **1–2** of five strategies | Ethical, Growth, Index, Quality, Value — each maps to 4+ tickers |
| Stock/ETF suggestions + dollar split | Conviction-weighted inverse-volatility sizing |
| **Live** portfolio value | yfinance quotes (Stooq fallback) |
| **5-day** portfolio trend | Overview chart + JSON snapshots |

### Dashboard tabs

| Tab | Highlights |
|---|---|
| **Overview** | Holdings, 5-day trend, action plan, rebalancing hints, narrative |
| **Performance** | vs SPY/60-40, backtests (1Y/3Y/5Y), benchmark table |
| **Risk & Diversification** | Explainability, VaR/CVaR, stress tests, correlation heatmap |
| **What-If** | Monte Carlo fan chart, goal tracker, tweak workbench (sliders) |
| **Compare** | Side-by-side two strategies with winner badges |
| **Data & Ops** | Quote quality, ops monitor, alerts |

### Extra capabilities

- **About You** risk questionnaire (age, horizon, drawdown) tilts cash buffer and weight dispersion.
- **Market ribbon** — scrolling live tape at the top of the page.
- **Saved portfolios** and **share links** (`/?p=<id>`).
- **Download CSV** and **Download PDF** exports.
- **Demo mode fallback** — optional checkbox in the left panel (or `QPL_DEMO_MODE=1` env var) uses synthetic prices when live APIs fail; useful for offline demos, not required for normal use.

---

## How allocation works

For each candidate stock we know:

- A **conviction score** (0–1) from the strategy definition
- An **annualized volatility** (rolling, from market history)

Each holding's raw weight is:

```
weight_i  ∝  conviction_i  /  max(volatility_i, volatility_floor)
```

Weights are normalized, then positions below **$100** per line are pruned unless that would drop below **3** holdings.

**Risk-profile tilt** (optional):

- More cash reserved for conservative profiles (up to ~12%)
- Dispersion exponent flattens (conservative) or steepens (aggressive) weights

See [portfolio_engine.py](portfolio_engine.py) for the full implementation.

---

## Risk profile

| Question | Effect |
|---|---|
| Age | Younger → higher risk score; older → more cash buffer |
| Years until you need it | Longer horizon → higher risk score |
| Max drawdown you can stomach (%) | Direct mapping to score |

Risk score is 0–100. Labels: *Conservative · Balanced · Growth · Aggressive* (pill next to **Live** after generate).

---

## Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                        Browser (Chart.js)                       │
│   Tabs · Tweak sliders · Goal tracker · Theme · Onboarding tour │
└────────────────────────┬───────────────────────────────────────┘
                         │  REST/JSON
┌────────────────────────▼───────────────────────────────────────┐
│                       Flask app.py                              │
│  Pydantic validation · enrich_portfolio_payload · CSV/PDF       │
└──┬─────────┬──────────┬──────────┬─────────┬──────────────────┘
   │         │          │          │         │
   ▼         ▼          ▼          ▼         ▼
┌──────┐ ┌──────────┐ ┌──────┐ ┌────────┐ ┌──────────┐
│engine│ │analytics │ │ risk │ │tracker │ │data_fetch│
│      │ │ MC/back  │ │ VaR/ │ │  saved │ │ yfinance │
│sizing│ │  test    │ │stress│ │snapshot│ │  +stooq  │
└──────┘ └──────────┘ └──────┘ └────────┘ └──────────┘
   │          ┌──────────────┐
   └────────► │ observability│
              │  + alerting  │
              └──────────────┘
```

**Data flow:** yfinance first → Stooq CSV fallback → optional demo-mode synthetic prices. Each quote includes source, age, and reliability metadata.

---

## Project layout

```
.
├── app.py                  # Flask app, endpoints, payload enrichment
├── portfolio_engine.py     # allocation sizing + risk-profile tilt
├── portfolio_analytics.py  # backtest, MC, correlation, tweak workbench
├── portfolio_tracker.py    # JSON snapshot persistence + saved list
├── risk_model.py           # microstructure cost, VaR/CVaR, stress tests
├── data_fetcher.py         # multi-source quotes, history, news
├── strategies.py           # five strategies → ticker mappings
├── alerting.py             # rule-based ops alerts
├── observability.py        # structured JSON logging
├── schemas.py              # Pydantic request schemas
├── config.py               # tunable knobs (env-overridable)
├── templates/index.html    # tab-based dashboard
├── static/
│   ├── css/style.css
│   └── js/app.js
├── tests/
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```

---

## API reference

| Method | Path | Purpose |
|---|---|---|
| `GET`  | `/` | Render the dashboard |
| `POST` | `/generate-portfolio` | Build a portfolio (amount + strategies + optional risk_profile) |
| `POST` | `/refresh-portfolio` | Refresh prices for an existing allocation |
| `POST` | `/compare-strategies` | Side-by-side comparison of two strategies |
| `GET`  | `/saved-portfolios` | List saved portfolios |
| `GET`  | `/portfolio/<id>` | Load a saved portfolio |
| `GET`  | `/portfolio-history/<id>` | Trend snapshots for one portfolio |
| `POST` | `/market-ticker` | Live market ribbon data |
| `GET`  | `/ops-monitor` | Operational metrics |
| `GET`  | `/health` | Health check |
| `GET`  | `/alerts` | Active operational alerts |
| `POST` | `/demo-mode` | Toggle demo mode at runtime |
| `POST` | `/export-csv` | CSV export |
| `POST` | `/run-daily-snapshot` | Refresh snapshots for all saved portfolios |

Example `POST /generate-portfolio` body:

```json
{
  "amount": 10000,
  "strategies": ["Growth Investing", "Quality Investing"],
  "risk_profile": {
    "age": 28,
    "horizon_years": 15,
    "max_drawdown_tolerance_pct": 30
  }
}
```

---

## Configuration

Key environment variables (see [config.py](config.py) for the full list):

| Variable | Default | Description |
|---|---|---|
| `QPL_MIN_INVESTMENT` | `5000` | Minimum investment (USD) |
| `QPL_VOLATILITY_FLOOR` | `0.08` | Floor on vol used in sizing |
| `QPL_DRIFT_THRESHOLD_PCT` | `5.0` | Rebalancing drift threshold |
| `QPL_PORTFOLIO_VAR_LIMIT_PCT` | `2.5` | VaR breach threshold |
| `QPL_MAX_SINGLE_POSITION_PCT` | `25.0` | Max single-position weight |
| `QPL_DEMO_MODE` | `0` | When `1`, use synthetic prices instead of live APIs |
| `QPL_PORT` | `8080` | HTTP port |

---

## Testing

```bash
./run_tests.sh
```

Runs `pytest` with coverage (55 tests, ~65% coverage). The test runner enables demo mode internally so CI does not depend on market APIs.

---

Built with Python 3.10+, Flask, Pydantic, Chart.js, and yfinance.
