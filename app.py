"""
Flask web application for Stock Portfolio Suggestion Engine.
"""

import csv
import io
import os
import threading
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

from flask import Flask, Response, g, jsonify, render_template, request
from pydantic import ValidationError

from alerting import AlertingEngine
from observability import get_structured_logger, log_event
from portfolio_analytics import PortfolioAnalytics
from portfolio_engine import PortfolioEngine
from portfolio_tracker import PortfolioTracker
from risk_model import MarketMicrostructureRiskModel
from schemas import (
    DemoModeToggleRequest,
    ExportCsvRequest,
    GeneratePortfolioRequest,
    MarketTickerRequest,
    RefreshPortfolioRequest,
)
from strategies import STRATEGIES, get_stocks_for_strategies

app = Flask(__name__)
logger = get_structured_logger("qpl.app")
portfolio_engine = PortfolioEngine()
portfolio_tracker = PortfolioTracker()
portfolio_analytics = PortfolioAnalytics(portfolio_engine.data_fetcher)
risk_model = MarketMicrostructureRiskModel(portfolio_engine.data_fetcher)
alerting_engine = AlertingEngine()

SCHEDULER_INTERVAL_SECONDS = 300
SCHEDULER_RUN_HOUR_ET = 18
_scheduler_state: dict[str, str | None] = {"last_run_date": None}


@app.before_request
def _assign_request_context() -> None:
    g.request_id = str(uuid.uuid4())
    g.request_started_at = time.perf_counter()


@app.after_request
def _log_request_response(response: Response) -> Response:
    started_at = getattr(g, "request_started_at", None)
    latency_ms = None
    if isinstance(started_at, (int, float)):
        latency_ms = round((time.perf_counter() - started_at) * 1000.0, 2)

    request_id = str(getattr(g, "request_id", "unknown"))
    response.headers["X-Request-ID"] = request_id

    log_event(
        logger,
        "info",
        "http_request_completed",
        request_id=request_id,
        method=request.method,
        path=request.path,
        status_code=response.status_code,
        latency_ms=latency_ms,
        remote_addr=request.remote_addr,
    )
    return response


def build_portfolio_explainability(portfolio):
    """Create plain-English explanation of allocations and risk posture."""
    allocations = portfolio.get("allocations", [])
    if not allocations:
        return {
            "risk_profile": "Unavailable",
            "summary": "No holdings are available yet.",
            "top_drivers": [],
            "methodology": "Conviction-weighted inverse-volatility sizing.",
        }

    weighted_volatility = sum(
        float(allocation.get("weight", 0.0)) * float(allocation.get("annualized_volatility", 0.0))
        for allocation in allocations
    )
    weighted_conviction = sum(
        float(allocation.get("weight", 0.0)) * float(allocation.get("conviction", 0.0))
        for allocation in allocations
    )

    if weighted_volatility < 0.17:
        risk_profile = "Conservative-Balanced"
    elif weighted_volatility < 0.27:
        risk_profile = "Balanced"
    else:
        risk_profile = "Growth-Oriented"

    top_holdings = sorted(allocations, key=lambda item: float(item.get("weight", 0.0)), reverse=True)[:3]
    top_drivers = [
        (
            f"{allocation.get('ticker')} at {float(allocation.get('weight_pct', 0.0)):.2f}% "
            f"(conviction {float(allocation.get('conviction', 0.0)):.2f}, "
            f"volatility {float(allocation.get('annualized_volatility', 0.0)) * 100:.2f}%)"
        )
        for allocation in top_holdings
    ]

    strategies = portfolio.get("strategies", [])
    strategy_line = ", ".join(strategies) if strategies else "selected strategy set"
    summary = (
        f"Portfolio tilts to {strategy_line} with a {risk_profile.lower()} profile. "
        f"Average conviction is {weighted_conviction:.2f} and weighted annualized volatility is "
        f"{weighted_volatility * 100:.2f}%."
    )

    return {
        "risk_profile": risk_profile,
        "summary": summary,
        "top_drivers": top_drivers,
        "methodology": (
            "Weights are proportional to conviction divided by volatility, then normalized to 100%."
        ),
    }


def build_portfolio_narrative(portfolio: dict) -> dict:
    """Compose a plain-English narrative tying analytics together for the user."""
    strategies = portfolio.get("strategies") or []
    total_value = float(portfolio.get("total_value", 0.0) or 0.0)
    num_stocks = portfolio.get("num_stocks") or len(portfolio.get("allocations") or [])
    strategy_phrase = " + ".join(strategies) if strategies else "custom"

    headline = (
        f"This {strategy_phrase} portfolio puts ${total_value:,.0f} across "
        f"{num_stocks} holdings using conviction-weighted, inverse-volatility sizing."
    )

    bullets: list[str] = []

    backtest = portfolio.get("backtest_analysis") or {}
    periods = backtest.get("periods") or []
    one_year = next(
        (p for p in periods if p.get("period") == "1Y" and p.get("portfolio_total_return_pct") is not None),
        None,
    )
    if one_year:
        ret = float(one_year.get("portfolio_total_return_pct") or 0.0)
        sharpe = float(one_year.get("portfolio_sharpe") or 0.0)
        dd = float(one_year.get("portfolio_max_drawdown_pct") or 0.0)
        bullets.append(
            f"Over the past year this exact mix would have returned {ret:+.1f}% with a Sharpe of "
            f"{sharpe:.2f} and a worst-case drawdown of {dd:.1f}%."
        )

    monte = portfolio.get("monte_carlo") or {}
    if monte.get("status") == "ok":
        terminal = monte.get("terminal_distribution") or {}
        median = float(terminal.get("p50") or 0.0)
        p5 = float(terminal.get("p5") or 0.0)
        p95 = float(terminal.get("p95") or 0.0)
        cv = float(monte.get("current_value") or total_value or 0.0)
        if cv > 0 and median > 0:
            median_return = (median / cv - 1.0) * 100.0
            bullets.append(
                f"Looking out 1 year, our Monte Carlo median lands at ${median:,.0f} "
                f"({median_return:+.1f}%); the 5th–95th percentile range spans "
                f"${p5:,.0f} to ${p95:,.0f}."
            )

    sectors = portfolio.get("sector_exposure") or {}
    sector_list = sectors.get("sectors") or []
    sector_weights = sectors.get("weights") or []
    if sector_list and sector_weights:
        top_sector = sector_list[0]
        top_weight = float(sector_weights[0])
        if top_weight >= 35.0:
            bullets.append(
                f"Heads-up: {top_weight:.0f}% of the book sits in {top_sector} — concentrated "
                "by design, but watch sector-specific shocks."
            )
        else:
            bullets.append(
                f"Top sector tilt is {top_sector} at {top_weight:.0f}% — diversified across "
                f"{len(sector_list)} sectors."
            )

    bench = portfolio.get("benchmark_comparison") or {}
    default_period = bench.get("default_period")
    period_payload = (bench.get("periods") or {}).get(default_period or "", {}) if default_period else {}
    rows = period_payload.get("rows") or []
    portfolio_row = next((r for r in rows if r.get("label") == "Portfolio"), None)
    spy_row = next((r for r in rows if str(r.get("label", "")).startswith("S&P")), None)
    if portfolio_row and spy_row:
        p_ret = portfolio_row.get("annual_return_pct")
        s_ret = spy_row.get("annual_return_pct")
        if p_ret is not None and s_ret is not None:
            diff = float(p_ret) - float(s_ret)
            verb = "outperformed" if diff >= 0 else "trailed"
            bullets.append(
                f"Annualized over the {default_period} window this mix {verb} the S&P 500 by "
                f"{abs(diff):.1f} percentage points."
            )

    risk_payload = portfolio.get("microstructure_risk") or {}
    breaches = risk_payload.get("position_limit_breaches") or []
    if breaches:
        bullets.append(
            f"{len(breaches)} position(s) exceed our liquidity-based size cap — consider "
            "trimming the largest holdings before you trade."
        )

    return {"headline": headline, "bullets": bullets}


def build_action_plan(portfolio: dict) -> dict:
    """Turn an allocation into a concrete buy-side checklist with execution-cost estimate."""
    allocations = portfolio.get("allocations") or []
    if not allocations:
        return {"orders": [], "summary": "No holdings to trade."}

    risk_payload = portfolio.get("microstructure_risk") or {}
    cost_rows = {row.get("ticker"): row for row in (risk_payload.get("positions") or [])}

    orders = []
    total_cost = 0.0
    estimated_slippage_total = 0.0
    for allocation in allocations:
        ticker = allocation.get("ticker")
        shares = float(allocation.get("shares") or 0.0)
        price = float(allocation.get("current_price") or allocation.get("price") or 0.0)
        cost = shares * price
        total_cost += cost
        cost_meta = cost_rows.get(ticker, {})
        slippage = float(cost_meta.get("expected_execution_cost") or 0.0)
        estimated_slippage_total += slippage
        orders.append({
            "action": "BUY",
            "ticker": ticker,
            "name": allocation.get("name") or ticker,
            "shares": round(shares, 4),
            "shares_whole": int(shares),
            "fractional_share": round(shares - int(shares), 4),
            "limit_price": round(price * 1.005, 2) if price else None,
            "estimated_cost": round(cost, 2),
            "estimated_execution_cost": round(slippage, 2),
            "weight_pct": round(float(allocation.get("weight_pct") or 0.0), 2),
        })

    cash_remainder = float(portfolio.get("cash_remainder") or 0.0)
    return {
        "orders": orders,
        "total_buy_value": round(total_cost, 2),
        "cash_to_hold": round(cash_remainder, 2),
        "estimated_slippage_total": round(estimated_slippage_total, 2),
        "open_at_hint": "Place orders at the next regular market open. Use limit prices ~0.5% above last to clear without chasing.",
        "summary": (
            f"{len(orders)} buys totaling {locale_currency(total_cost)} "
            f"+ {locale_currency(cash_remainder)} cash; est. execution cost {locale_currency(estimated_slippage_total)}."
        ),
    }


def locale_currency(value: float) -> str:
    try:
        return f"${float(value):,.2f}"
    except Exception:
        return "$0.00"


def _history_change_percent(price_frame, ticker):
    if price_frame.empty or ticker not in price_frame.columns:
        return None

    series = price_frame[ticker].dropna()
    if series.shape[0] < 2:
        return None

    latest = float(series.iloc[-1])
    previous = float(series.iloc[-2])
    if previous == 0:
        return None
    return ((latest - previous) / previous) * 100.0


def build_market_ticker_snapshot(holdings=None):
    """Build live tape payload used by the top ribbon."""
    if holdings is None:
        holdings = []

    default_symbols = [
        ("SPY", "SPY"),
        ("QQQ", "QQQ"),
        ("^TNX", "UST10Y"),
        ("^VIX", "VIX"),
        ("AGG", "US BOND"),
        ("DX-Y.NYB", "USD INDEX"),
    ]
    holding_symbols = [(ticker, f"HOLD {ticker}") for ticker in holdings[:2] if isinstance(ticker, str)]
    symbol_pairs = holding_symbols + default_symbols

    unique_symbols = []
    seen = set()
    for symbol, label in symbol_pairs:
        if symbol not in seen:
            unique_symbols.append((symbol, label))
            seen.add(symbol)

    symbols_only = [symbol for symbol, _ in unique_symbols]
    quote_map = portfolio_engine.data_fetcher.get_multiple_quotes(symbols_only)

    today = date.today()
    start = today - timedelta(days=12)
    history_frame, _ = portfolio_engine.data_fetcher.get_price_history_frame(symbols_only, start, today)

    entries = []
    for symbol, label in unique_symbols:
        quote = quote_map.get(symbol)
        price = quote.get("price") if quote else None
        if price is None:
            if history_frame.empty or symbol not in history_frame.columns:
                continue
            series = history_frame[symbol].dropna()
            if series.empty:
                continue
            price = float(series.iloc[-1])

        change_pct = _history_change_percent(history_frame, symbol)
        entries.append(
            {
                "symbol": symbol,
                "label": label,
                "price": float(price),
                "change_pct": change_pct,
                "source": quote.get("source") if quote else "history_close",
                "market_status": (
                    quote.get("market_status")
                    if quote
                    else portfolio_engine.data_fetcher.get_market_clock().get("market_status")
                ),
            }
        )

    return {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "entries": entries,
    }

def enrich_portfolio_payload(portfolio):
    """Attach live value, trend, and advanced analytics to a portfolio payload."""
    # Calculate current market value for existing holdings.
    portfolio = portfolio_engine.calculate_portfolio_value(portfolio)

    # Save snapshot and attach ID.
    portfolio_id = portfolio_tracker.save_portfolio_snapshot(portfolio)
    portfolio['portfolio_id'] = portfolio_id

    # Build 5-day trend from market closes.
    trend_data = portfolio_tracker.build_market_trend(
        portfolio,
        portfolio_engine.data_fetcher,
        days=5
    )
    if not trend_data['dates']:
        trend_data = portfolio_tracker.get_trend_data(portfolio_id)
    portfolio['trend_data'] = trend_data
    portfolio['comparison_trend'] = portfolio_tracker.build_comparison_trend(
        portfolio,
        portfolio_engine.data_fetcher,
        days=30
    )

    # Advanced analytics bundle.
    advanced_analytics = portfolio_analytics.run_full_analysis(portfolio)
    portfolio['benchmark_comparison'] = advanced_analytics['benchmark_comparison']
    portfolio['backtest_analysis'] = advanced_analytics['backtests']
    portfolio['rebalancing_recommendations'] = advanced_analytics['rebalancing_recommendations']
    portfolio['correlation_matrix'] = advanced_analytics['correlation_matrix']
    portfolio['sector_exposure'] = advanced_analytics['sector_exposure']
    portfolio['monte_carlo'] = advanced_analytics['monte_carlo']
    portfolio['tweak_workbench'] = advanced_analytics['tweak_workbench']
    portfolio['analysis_configuration'] = advanced_analytics['configuration']
    portfolio['analysis_quality_warnings'] = advanced_analytics['quality_warnings']
    portfolio['explainability'] = build_portfolio_explainability(portfolio)
    portfolio['microstructure_risk'] = risk_model.build_portfolio_risk_payload(portfolio)
    # News attached per-allocation for the holdings cards
    try:
        tickers = [a['ticker'] for a in portfolio.get('allocations', []) if a.get('ticker')]
        news_map = portfolio_engine.data_fetcher.get_news_for_tickers(tickers, limit_each=2)
        for allocation in portfolio.get('allocations', []):
            allocation['news'] = news_map.get(allocation.get('ticker'), [])
    except Exception as exc:
        log_event(logger, 'warning', 'news_enrichment_failed', error=str(exc))
    portfolio['narrative'] = build_portfolio_narrative(portfolio)
    portfolio['action_plan'] = build_action_plan(portfolio)
    ops_monitor = portfolio_engine.data_fetcher.get_monitoring_snapshot()
    ops_monitor['alerts'] = alerting_engine.evaluate(ops_monitor)
    portfolio['ops_monitor'] = ops_monitor
    portfolio['demo_mode_enabled'] = portfolio_engine.data_fetcher.demo_mode_enabled
    portfolio['last_updated'] = datetime.now(timezone.utc).isoformat()

    return portfolio

@app.route('/')
def index():
    """Render main page."""
    return render_template(
        'index.html',
        strategy_data=STRATEGIES,
        demo_mode_enabled=portfolio_engine.data_fetcher.demo_mode_enabled,
    )

@app.route('/favicon.ico')
def favicon():
    """Return an empty favicon response to avoid noisy 404 logs in development."""
    return '', 204


@app.route('/market-ticker', methods=['POST'])
def market_ticker():
    """Return live market ribbon data with optional top holdings."""
    try:
        payload = request.get_json(silent=True) or {}
        validated = MarketTickerRequest.model_validate(payload)
        snapshot = build_market_ticker_snapshot(holdings=validated.holdings)
        return jsonify(snapshot)
    except ValidationError as exc:
        log_event(logger, "warning", "market_ticker_validation_failed", details=exc.errors())
        return jsonify({"error": "Invalid market ticker request", "details": exc.errors()}), 400
    except Exception as exc:
        log_event(logger, "error", "market_ticker_failed", error=str(exc))
        return jsonify({"error": str(exc)}), 500


@app.route('/ops-monitor', methods=['GET'])
def ops_monitor():
    """Return backend operational monitoring metrics for UI panel."""
    try:
        snapshot = portfolio_engine.data_fetcher.get_monitoring_snapshot()
        snapshot["alerts"] = alerting_engine.evaluate(snapshot)
        return jsonify(snapshot)
    except Exception as exc:
        log_event(logger, "error", "ops_monitor_failed", error=str(exc))
        return jsonify({"error": str(exc)}), 500


@app.route('/health', methods=['GET'])
def health() -> Response:
    """Health endpoint exposing basic service state."""
    clock = portfolio_engine.data_fetcher.get_market_clock()
    payload: dict[str, Any] = {
        "status": "ok",
        "service": "quantum-portfolio-lab",
        "market_status": clock.get("market_status"),
        "demo_mode_enabled": portfolio_engine.data_fetcher.demo_mode_enabled,
        "scheduler": {
            "interval_seconds": SCHEDULER_INTERVAL_SECONDS,
            "run_hour_et": SCHEDULER_RUN_HOUR_ET,
            "last_run_date": _scheduler_state.get("last_run_date"),
        },
        "as_of": datetime.now(timezone.utc).isoformat(),
    }
    return jsonify(payload)


@app.route('/alerts', methods=['GET'])
def alerts():
    """Return persisted alert state for monitoring consumers."""
    try:
        return jsonify(alerting_engine.get_snapshot())
    except Exception as exc:
        log_event(logger, "error", "alerts_endpoint_failed", error=str(exc))
        return jsonify({"error": str(exc)}), 500


@app.route('/demo-mode', methods=['GET', 'POST'])
def demo_mode():
    """Get or update demo mode state for synthetic fallback dataset."""
    try:
        if request.method == 'POST':
            data = request.get_json(silent=True) or {}
            validated = DemoModeToggleRequest.model_validate(data)
            portfolio_engine.data_fetcher.set_demo_mode(validated.enabled)
            log_event(
                logger,
                "info",
                "demo_mode_updated",
                enabled=portfolio_engine.data_fetcher.demo_mode_enabled,
            )
        snapshot = portfolio_engine.data_fetcher.get_monitoring_snapshot()
        return jsonify(
            {
                "demo_mode_enabled": portfolio_engine.data_fetcher.demo_mode_enabled,
                "summary": snapshot.get("summary"),
                "as_of": snapshot.get("as_of"),
            }
        )
    except ValidationError as exc:
        log_event(logger, "warning", "demo_mode_validation_failed", details=exc.errors())
        return jsonify({"error": "Invalid demo mode request", "details": exc.errors()}), 400
    except Exception as exc:
        log_event(logger, "error", "demo_mode_failed", error=str(exc))
        return jsonify({"error": str(exc)}), 500

@app.route('/generate-portfolio', methods=['POST'])
def generate_portfolio():
    """Generate portfolio based on user input."""
    try:
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({'error': 'Request body must be valid JSON'}), 400

        validated = GeneratePortfolioRequest.model_validate(data)
        amount = validated.amount
        selected_strategies = validated.strategies
        risk_profile = validated.risk_profile.model_dump() if validated.risk_profile else None

        # Get stocks for selected strategies
        stocks = get_stocks_for_strategies(selected_strategies)

        # Generate portfolio
        portfolio = portfolio_engine.generate_portfolio(
            amount, selected_strategies, stocks, risk_profile=risk_profile
        )

        if 'error' in portfolio:
            return jsonify(portfolio), 400

        portfolio = enrich_portfolio_payload(portfolio)
        log_event(
            logger,
            "info",
            "portfolio_generated",
            strategies=selected_strategies,
            amount=amount,
            positions=len(portfolio.get("allocations", [])),
            total_value=portfolio.get("total_value"),
        )

        return jsonify(portfolio)
    except ValidationError as exc:
        details = exc.errors()
        log_event(logger, "warning", "portfolio_generation_validation_failed", details=details)
        amount_errors = [item for item in details if item.get("loc") == ("amount",)]
        if amount_errors:
            return jsonify({'error': 'Minimum investment amount is $5,000.'}), 400
        strategy_errors = [item for item in details if item.get("loc") == ("strategies",)]
        if strategy_errors:
            unknown_messages = [
                item.get("msg", "")
                for item in strategy_errors
                if "Unknown strategies" in str(item.get("msg", ""))
            ]
            if unknown_messages:
                normalized = unknown_messages[0].replace("Value error, ", "")
                return jsonify({'error': normalized}), 400
            return jsonify({'error': 'Please select 1 or 2 investment strategies'}), 400
        return jsonify({'error': 'Invalid portfolio request', 'details': details}), 400
    except Exception as e:
        log_event(logger, "error", "portfolio_generation_failed", error=str(e))
        return jsonify({'error': str(e)}), 500

@app.route('/refresh-portfolio', methods=['POST'])
def refresh_portfolio():
    """Refresh prices and analytics for an existing portfolio without re-buying."""
    try:
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({'error': 'Request body must be valid JSON'}), 400

        validated = RefreshPortfolioRequest.model_validate(data)

        portfolio = {
            'portfolio_id': validated.portfolio_id,
            'allocations': [allocation.model_dump() for allocation in validated.allocations],
            'cash_remainder': float(validated.cash_remainder),
            'investment_amount': float(validated.investment_amount),
            'strategies': list(validated.strategies),
            'allocation_method': validated.allocation_method,
            'total_allocated': float(validated.total_allocated),
        }

        portfolio = enrich_portfolio_payload(portfolio)
        log_event(
            logger,
            "info",
            "portfolio_refreshed",
            strategies=portfolio.get("strategies", []),
            positions=len(portfolio.get("allocations", [])),
            total_value=portfolio.get("total_value"),
        )
        return jsonify(portfolio)

    except ValidationError as exc:
        log_event(logger, "warning", "portfolio_refresh_validation_failed", details=exc.errors())
        return jsonify({'error': 'Invalid portfolio payload for refresh', 'details': exc.errors()}), 400
    except Exception as e:
        log_event(logger, "error", "portfolio_refresh_failed", error=str(e))
        return jsonify({'error': str(e)}), 500

@app.route('/portfolio-history/<portfolio_id>', methods=['GET'])
def get_portfolio_history(portfolio_id):
    """Get historical data for a portfolio."""
    try:
        trend_data = portfolio_tracker.get_trend_data(portfolio_id)
        return jsonify(trend_data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/saved-portfolios', methods=['GET'])
def list_saved_portfolios():
    """List saved portfolios for the sidebar."""
    try:
        summaries = portfolio_tracker.list_saved_portfolios_summary()
        return jsonify({"portfolios": summaries[:25]})
    except Exception as exc:
        log_event(logger, "error", "saved_portfolios_failed", error=str(exc))
        return jsonify({"error": str(exc)}), 500


@app.route('/portfolio/<portfolio_id>', methods=['GET'])
def load_saved_portfolio(portfolio_id):
    """Load a saved portfolio by ID, refresh prices, and return the full payload."""
    try:
        blueprint = portfolio_tracker.load_saved_portfolio_blueprint(portfolio_id)
        if not blueprint:
            return jsonify({"error": "Portfolio not found."}), 404
        portfolio = portfolio_engine.calculate_portfolio_value(blueprint)
        portfolio = enrich_portfolio_payload(portfolio)
        return jsonify(portfolio)
    except Exception as exc:
        log_event(logger, "error", "load_saved_portfolio_failed", error=str(exc), portfolio_id=portfolio_id)
        return jsonify({"error": str(exc)}), 500


@app.route('/compare-strategies', methods=['POST'])
def compare_strategies():
    """Generate two portfolios for the same amount with different strategies and return summary metrics."""
    try:
        data = request.get_json() or {}
        amount = float(data.get('amount') or 5000)
        if amount < 5000:
            return jsonify({"error": "Minimum amount is $5,000."}), 400
        strategy_a = data.get('strategy_a')
        strategy_b = data.get('strategy_b')
        if not strategy_a or not strategy_b:
            return jsonify({"error": "Both strategy_a and strategy_b are required."}), 400
        if strategy_a == strategy_b:
            return jsonify({"error": "Pick two different strategies."}), 400

        results = []
        for strategy_name in (strategy_a, strategy_b):
            stocks = get_stocks_for_strategies([strategy_name])
            portfolio = portfolio_engine.generate_portfolio(amount, [strategy_name], stocks)
            if portfolio.get('error'):
                return jsonify({"error": portfolio['error']}), 400
            portfolio = portfolio_engine.calculate_portfolio_value(portfolio)
            mc = portfolio_analytics.run_monte_carlo(portfolio, simulations=500)
            backtest = portfolio_analytics._analyze_period(
                portfolio, years=1, config=portfolio_analytics.default_config
            ) if portfolio.get('allocations') else {"status": "insufficient_data"}
            row = {
                "strategy": strategy_name,
                "tickers": [a['ticker'] for a in portfolio.get('allocations', [])],
                "weights_pct": [round(a.get('weight_pct', 0.0), 2) for a in portfolio.get('allocations', [])],
                "current_value": portfolio.get('total_value'),
                "monte_carlo_median_1y": (mc.get('terminal_distribution') or {}).get('p50') if mc.get('status') == 'ok' else None,
                "monte_carlo_p5_1y": (mc.get('terminal_distribution') or {}).get('p5') if mc.get('status') == 'ok' else None,
                "monte_carlo_p95_1y": (mc.get('terminal_distribution') or {}).get('p95') if mc.get('status') == 'ok' else None,
                "backtest_1y_return_pct": backtest.get('portfolio', {}).get('total_return_pct') if backtest.get('status') == 'ok' else None,
                "backtest_1y_sharpe": backtest.get('portfolio', {}).get('sharpe') if backtest.get('status') == 'ok' else None,
                "backtest_1y_max_drawdown_pct": backtest.get('portfolio', {}).get('max_drawdown_pct') if backtest.get('status') == 'ok' else None,
                "annualized_volatility_pct": (mc.get('volatility_daily_pct') or 0) * (252 ** 0.5) if mc.get('status') == 'ok' else None,
            }
            results.append(row)
        return jsonify({"amount": amount, "results": results})
    except Exception as exc:
        log_event(logger, "error", "compare_strategies_failed", error=str(exc))
        return jsonify({"error": str(exc)}), 500


@app.route('/export-csv', methods=['POST'])
def export_csv():
    """Export the current portfolio payload as CSV."""
    try:
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify({"error": "Request body must be valid JSON"}), 400
        validated = ExportCsvRequest.model_validate(payload)

        output = io.StringIO()
        writer = csv.writer(output)

        writer.writerow(["Quantum Portfolio Lab Report"])
        writer.writerow(["Generated At (UTC)", datetime.now(timezone.utc).isoformat()])
        writer.writerow(["Investment Amount", validated.investment_amount])
        writer.writerow(["Total Value", validated.total_value])
        writer.writerow(["Cash Remainder", validated.cash_remainder])
        writer.writerow(["Strategies", " + ".join(validated.strategies)])
        writer.writerow([])
        writer.writerow(
            [
                "Ticker",
                "Name",
                "Strategy",
                "Weight %",
                "Shares",
                "Entry Price",
                "Current Price",
                "Invested",
                "Current Value",
                "Quote Source",
                "Quote Stale",
            ]
        )

        for allocation in validated.allocations:
            writer.writerow(
                [
                    allocation.ticker,
                    allocation.name,
                    allocation.strategy,
                    round(float(allocation.weight_pct or 0.0), 4),
                    round(float(allocation.shares), 6),
                    round(float(allocation.price), 4),
                    round(float(allocation.current_price if allocation.current_price is not None else allocation.price), 4),
                    round(float(allocation.cost), 4),
                    round(float(allocation.current_value if allocation.current_value is not None else allocation.cost), 4),
                    allocation.quote_source,
                    allocation.quote_is_stale,
                ]
            )

        csv_data = output.getvalue()
        filename = f"portfolio-report-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.csv"
        log_event(
            logger,
            "info",
            "portfolio_exported_csv",
            strategies=validated.strategies,
            allocations=len(validated.allocations),
            filename=filename,
        )
        return Response(
            csv_data,
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )
    except ValidationError as exc:
        log_event(logger, "warning", "export_csv_validation_failed", details=exc.errors())
        return jsonify({"error": "Invalid export payload", "details": exc.errors()}), 400
    except Exception as exc:
        log_event(logger, "error", "export_csv_failed", error=str(exc))
        return jsonify({"error": str(exc)}), 500


@app.route('/run-daily-snapshot', methods=['POST'])
def run_daily_snapshot():
    """Manual trigger for server-side daily snapshot refresh."""
    try:
        result = portfolio_tracker.refresh_all_saved_portfolios(portfolio_engine)
        log_event(logger, "info", "daily_snapshot_run", **result)
        return jsonify({"status": "ok", **result})
    except Exception as exc:
        log_event(logger, "error", "daily_snapshot_failed", error=str(exc))
        return jsonify({"error": str(exc)}), 500


def _daily_snapshot_scheduler_loop():
    while True:
        try:
            now_et = datetime.now(portfolio_engine.data_fetcher.ny_tz)
            today_key = now_et.strftime("%Y-%m-%d")
            if now_et.hour >= SCHEDULER_RUN_HOUR_ET and _scheduler_state["last_run_date"] != today_key:
                result = portfolio_tracker.refresh_all_saved_portfolios(portfolio_engine)
                _scheduler_state["last_run_date"] = today_key
                log_event(
                    logger,
                    "info",
                    "scheduler_daily_snapshot_complete",
                    updated_count=result.get("updated_count", 0),
                )
        except Exception as exc:
            log_event(logger, "error", "scheduler_daily_snapshot_failed", error=str(exc))

        time.sleep(SCHEDULER_INTERVAL_SECONDS)


def start_background_scheduler():
    thread = threading.Thread(target=_daily_snapshot_scheduler_loop, daemon=True)
    thread.start()
    log_event(logger, "info", "scheduler_started", interval_seconds=SCHEDULER_INTERVAL_SECONDS)

if __name__ == '__main__':
    debug_mode = os.environ.get("QPL_DEBUG", "1").lower() in {"1", "true", "yes", "on"}
    host = os.environ.get("QPL_HOST", "0.0.0.0")
    try:
        port = int(os.environ.get("QPL_PORT", "8080"))
    except ValueError:
        port = 8080

    print("Starting Stock Portfolio Suggestion Engine...")
    print(f"Navigate to: http://localhost:{port}")
    print("Select 1-2 strategies and enter investment amount (min $5000)")
    should_start_scheduler = os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not debug_mode
    if should_start_scheduler:
        start_background_scheduler()
    log_event(logger, "info", "app_start", debug=debug_mode, host=host, port=port)
    app.run(host=host, debug=debug_mode, port=port)
