# 285 Project SEP

> Build, track, and stress-test a real stock portfolio in minutes — with live prices, backtests, Monte Carlo forecasts, and a what-if workbench you can drag.

[![Tests](https://img.shields.io/badge/tests-55%20passing-4ade80?style=flat-square)]()
[![Coverage](https://img.shields.io/badge/coverage-65%25-58cbff?style=flat-square)]()
[![Python](https://img.shields.io/badge/python-3.10%2B-blue?style=flat-square)]()
[![License](https://img.shields.io/badge/license-MIT-lightgrey?style=flat-square)]()

A Flask + Pydantic + Chart.js stack with a multi-source data layer, microstructure-aware risk model, and a UI built around six focused tabs (Overview · Performance · Risk · What-If · Compare · Data). Originally built for *285 Software Engineering Processes* and grown into a real allocation tool.

---

## Table of contents

1. [Demo](#demo)
2. [What's interesting about it](#whats-interesting-about-it)
3. [Quick start](#quick-start)
4. [How allocation works](#how-allocation-works)
5. [Risk profile (3 questions)](#risk-profile-3-questions)
6. [Feature tour](#feature-tour)
7. [Architecture](#architecture)
8. [Project layout](#project-layout)
9. [API reference](#api-reference)
10. [Configuration](#configuration)
11. [Testing](#testing)
12. [Roadmap](#roadmap)

---

## Demo

> **TODO:** Replace these with your own assets.
>
> - 30-second Loom: _link goes here_
> - Live deploy: _https://your-deploy-url_
>
> Recommended screenshots (drop into `docs/screenshots/`):
> - `01-landing.png` — landing page with strategy cards showing tickers
> - `02-overview.png` — Overview tab with narrative + holdings + 5-day trend
> - `03-whatif.png` — What-If tab with Monte Carlo cone + tweak workbench sliders
> - `04-stress.png` — Risk tab with stress-test scenario grid (GFC, COVID, etc.)
> - `05-compare.png` — Compare tab with two strategies side-by-side
> - `06-light.png` — Light theme

---

## What's interesting about it

This is not just an allocator. The whole product is built around **what the user actually does next**:

| Question the user has | What we surface |
|---|---|
| *"What should I buy?"* | Conviction-weighted inverse-volatility sizing, tilted by your risk profile |
| *"What does it look like for me specifically?"* | 3-question profile (age, horizon, drawdown tolerance) tilts cash buffer and dispersion |
| *"What do I do Monday morning?"* | Action Plan card: ordered BUY checklist with limit prices, share counts, est. slippage |
| *"What's the worst that can happen?"* | Stress tests against 5 historic regimes (GFC '08, COVID '20, dot-com, '22 inflation, Black Monday) + 3 hypothetical shocks |
| *"What if I change a weight?"* | Tweak Workbench: drag any holding's weight, watch Sharpe / vol / return / Σ recompute live (client-side wᵀΣw) |
| *"Will I hit my goal?"* | Goal Tracker: enter target $ + horizon, get P(reach) under a lognormal model, with goal line drawn on the Monte Carlo cone |
| *"Strategy A vs Strategy B?"* | Compare tab runs both for the same dollar amount and flags winners on Sharpe, Return, MC median, and Drawdown |
| *"Anything happening with my holdings?"* | Live news per holding (yfinance + demo fallback) |
| *"Can I save / share this?"* | Saved portfolios sidebar + share links (`/?p=<id>` deep-loads on visit) |

---

## Quick start

```bash
# Clone & enter
git clone https://github.com/<your-handle>/stock-portfolio-engine
cd stock-portfolio-engine

# Install
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Run (demo mode = offline, deterministic prices)
QPL_DEMO_MODE=1 python app.py
# → http://127.0.0.1:8080
```

Or with Docker:

```bash
docker compose up
# → http://127.0.0.1:8080
```

First-time visitors get a 5-step interactive tour. Dismiss it once and it stays dismissed.

---

## How allocation works

For each candidate stock we know:
- A **conviction score** (0–1) from the strategy definition
- An **annualized volatility** (rolling, from market history)

Each holding's raw weight is:

```
weight_i  ∝  conviction_i  /  max(volatility_i, volatility_floor)
```

We normalize so weights sum to 1, then iteratively prune positions whose target dollar value falls below `$min_per_stock` until the smallest position fits or we'd drop below 3 holdings (the spec floor).

**Risk-profile tilt** then warps this:
- `cash_reserve_pct` rises as risk score falls (0% aggressive → ~12% conservative)
- A dispersion exponent compresses (^0.6) for conservative or steepens (^1.6) for aggressive — flatter weights for stability vs. concentrated bets on the highest conviction-per-vol names.

See [portfolio_engine.py](portfolio_engine.py) for the full implementation.

---

## Risk profile (3 questions)

| Question | What it tilts |
|---|---|
| Age | Younger = higher risk score; older = more cash buffer |
| Years until you need it | Longer horizon = higher risk score |
| Max drawdown you can stomach (%) | Direct mapping to score |

Risk score is a 0–100 weighted average of the three. We label it *Conservative · Balanced · Growth · Aggressive* and stash a tinted pill on the results header.

---

## Feature tour

### Overview tab
- Plain-English **narrative** generated from existing analytics — ties Sharpe, Monte Carlo terminal range, sector tilt, and SPY comparison into 3–5 sentences.
- **Action Plan**: ordered BUY checklist with shares, limit price (last × 1.005), estimated cost, and est. slippage from the microstructure model.
- **Holdings cards** with live attribution chip (% return since allocation), 2 recent news headlines, and per-holding metrics.
- **5-day portfolio trend** chart.
- **Rebalancing recommendations** when any holding drifts past the threshold.

### Performance tab
- 30-day vs SPY/60-40 comparison chart, with sub-charts for portfolio drawdown and rolling 10-day Sharpe.
- 1Y/3Y/5Y backtest grid with annualized return, Sharpe, drawdown, transaction-cost paid, turnover.
- Benchmark table (Portfolio vs SPY vs 60/40) with Alpha and Beta.

### Risk & Diversification tab
- "Why this portfolio" explainability: top weight drivers, sector concentration, volatility floor application.
- Execution & risk controls: VaR/CVaR, position limit breaches, weighted execution cost in bps.
- Allocation donut + sector exposure donut.
- Correlation heatmap (color-coded -1 to 1).
- **Stress tests** — 5 historic regimes + 3 hypothetical shocks, each with PnL%, dollars, and worst position.

### What-If tab
- Monte Carlo fan chart (5/25/50/75/95th percentile bands).
- **Goal Tracker** — input target value + years; we compute P(reach) under a lognormal model and draw the goal line on the MC chart.
- **Tweak Workbench** — slider per holding; live recompute of expected return / vol / Sharpe / effective N / largest weight using wᵀΣw with the cached covariance matrix. Reset / Equal-weight buttons.

### Compare tab
- Pick two strategies, run side-by-side at the same dollar amount.
- Cards show ticker chips, 1Y backtest stats, and Monte Carlo terminal distribution.
- "Best" badges flag the winner on Sharpe / Return / Max DD / MC median.

### Data & Ops tab
- Live data quality summary (avg reliability, market state, fallback rate).
- Operations monitor: quote requests, failures, fallback uses, recent errors, daily fallback trend chart.
- Active alerts surfaced from `alerting.py` rules.

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
   │                                            ▲
   │          ┌──────────────┐                   │
   └────────► │ observability│◄──────────────────┘
              │  + alerting  │
              └──────────────┘
```

**Data reliability:** every market lookup tries yfinance first, falls back to Stooq CSV, and finally to a deterministic demo-mode price. Each quote carries a source, age, and reliability score.

---

## Project layout

```
.
├── app.py                  # Flask app, endpoints, payload enrichment
├── portfolio_engine.py     # allocation sizing + risk-profile tilt
├── portfolio_analytics.py  # backtest, MC, correlation, tweak workbench
├── portfolio_tracker.py    # JSON-based snapshot persistence + saved list
├── risk_model.py           # microstructure cost, VaR/CVaR, stress tests
├── data_fetcher.py         # multi-source quotes, history, news
├── strategies.py           # 5 strategy → tickers mapping
├── alerting.py             # rule-based ops alerts
├── observability.py        # structured JSON logging
├── schemas.py              # Pydantic request schemas
├── config.py               # tunable knobs (env-overridable)
├── templates/index.html    # tab-based dashboard
├── static/
│   ├── css/style.css       # design tokens + layout + Tier S
│   └── js/app.js           # tabs, charts, tweak engine, tour
├── tests/                  # pytest suite (55 tests, 65% coverage)
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```

---

## API reference

| Method | Path | Purpose |
|---|---|---|
| `GET`  | `/`                          | Render the dashboard |
| `POST` | `/generate-portfolio`        | Build a portfolio (amount + strategies + optional risk_profile) |
| `POST` | `/refresh-portfolio`         | Refresh prices for a known allocation |
| `POST` | `/compare-strategies`        | Side-by-side comparison of two strategies |
| `GET`  | `/saved-portfolios`          | List saved portfolios (latest snapshot meta) |
| `GET`  | `/portfolio/<id>`            | Load a saved portfolio (refreshes prices) |
| `GET`  | `/portfolio-history/<id>`    | Trend snapshots for one portfolio |
| `POST` | `/market-ticker`             | Live tape for the top ribbon |
| `GET`  | `/ops-monitor`               | Background ops snapshot |
| `GET`  | `/health`                    | Health check (latency, demo flag, market state) |
| `GET`  | `/alerts`                    | Active operational alerts |
| `POST` | `/demo-mode`                 | Toggle demo mode at runtime |
| `POST` | `/export-csv`                | CSV export of an allocation |
| `POST` | `/run-daily-snapshot`        | Trigger today's snapshot for all saved portfolios |

`POST /generate-portfolio` body:

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

All knobs live in [config.py](config.py) and are overridable via env vars:

| Var | Default | What it does |
|---|---|---|
| `QPL_DEMO_MODE` | `0` | Force deterministic offline prices (recommended for demos / CI) |
| `QPL_MIN_INVESTMENT` | `5000` | Minimum dollar amount enforced server-side |
| `QPL_VOLATILITY_FLOOR` | `0.08` | Floor on per-asset annualized vol used in sizing |
| `QPL_DRIFT_THRESHOLD_PCT` | `5.0` | Threshold for rebalancing recommendations |
| `QPL_PORTFOLIO_VAR_LIMIT_PCT` | `2.5` | VaR breach threshold |
| `QPL_MAX_SINGLE_POSITION_PCT` | `25.0` | Position-size limit (microstructure module) |

…and ~80 more.

---

## Testing

```bash
./run_tests.sh
```

Runs `pytest` against `tests/` with coverage. Demo mode is forced for hermetic runs.

```
55 passed in 1.08s
Required test coverage of 45% reached. Total coverage: 65.29%
```

Modules with 90%+ coverage: `risk_model`, `schemas`, `observability`, `alerting`, `portfolio_analytics`, `config`.

---

## 10 Detailed Test Cases

Below are 10 step-by-step test cases a grader can follow to verify the project's core functions.

### Grading setup

**Requirements:** Python 3.10+, pip

1. Unzip the project and open a terminal in the project folder.
2. Create a virtual environment and install dependencies:

```bash
python3 -m venv venv
source venv/bin/activate    # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

3. Start the app in **demo mode** (stable prices; works offline):

```bash
QPL_DEMO_MODE=1 python app.py
```

4. Open a browser at **`http://127.0.0.1:8080`**.
5. (Optional) Enable the **Demo Mode Fallback** checkbox in the left panel if quotes fail.
6. Dismiss the onboarding tour if it appears.

**Docker alternative:** `docker compose up` → open `http://127.0.0.1:8080`

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
4. Note **Cash Remainder** on Overview and the risk label pill (e.g. Conservative).

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

## Roadmap

Things I'd add next, ordered by user value:

- [ ] Natural-language input via Claude API ("$10k, growth-leaning, 5-year horizon" → strategy + tilts)
- [ ] WebSocket live prices instead of polling
- [ ] Portfolio journal with diff-vs-last-snapshot
- [ ] Tax-aware nudges (wash sale, harvest opportunities)
- [ ] Multi-currency support
- [ ] Frontend e2e tests with Playwright
- [ ] Public live deploy on Fly.io / Railway

---

Built on Python 3.10+, Flask, Pydantic, Chart.js, yfinance, and a healthy respect for what users actually want to do next.
