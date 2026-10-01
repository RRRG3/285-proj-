"""Numerical regression tests: accounting identities and data integrity."""
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from data_fetcher import StockDataFetcher
from portfolio_analytics import BacktestConfig, PortfolioAnalytics
from portfolio_engine import PortfolioEngine
from risk_model import MarketMicrostructureRiskModel


class History:
    def __init__(self, frame):
        self.frame = frame

    def get_price_history_frame(self, tickers, start_date, end_date):
        return self.frame.copy(), {t: {"source": "yfinance_download"} for t in self.frame}


def prices(values):
    return pd.DataFrame(values, index=pd.bdate_range("2025-01-01", periods=len(next(iter(values.values())))))


def test_sharpe_uses_arithmetic_excess_returns():
    returns = np.array([0.04, -0.03, 0.02, -0.01])
    values = pd.Series(np.r_[1.0, np.cumprod(1 + returns)])
    metrics = PortfolioAnalytics(None)._performance_metrics(values, 0.05)
    expected = (returns.mean() - (1.05 ** (1 / 252) - 1)) / returns.std(ddof=1) * np.sqrt(252)
    assert metrics["sharpe"] == pytest.approx(expected)


def test_undefined_sharpe_is_not_zero():
    metrics = PortfolioAnalytics(None)._performance_metrics(pd.Series([1.0, 1.0, 1.0]), 0)
    assert metrics["sharpe"] is None


def test_initial_cost_included_in_return_and_drawdown():
    analytics = PortfolioAnalytics(None)
    values, meta = analytics._simulate_rebalanced_portfolio(prices({"A": [100, 100, 100]}), {"A": 1}, 0.01, "none")
    metrics = analytics._performance_metrics(values, 0)
    assert values.iloc[-1] == pytest.approx(1 / 1.01)
    assert metrics["total_return_pct"] == pytest.approx((1 / 1.01 - 1) * 100)
    assert metrics["max_drawdown_pct"] == pytest.approx(metrics["total_return_pct"])
    assert values.iloc[-1] + meta["transaction_cost_paid_pct"] / 100 == pytest.approx(1)


def test_rebalance_charges_both_legs_and_is_self_financing():
    analytics = PortfolioAnalytics(None)
    values, meta = analytics._simulate_rebalanced_portfolio(prices({"A": [100, 200], "B": [100, 100]}), {"A": .5, "B": .5}, .01, "daily")
    initial = 1 / 1.01
    before = initial * 1.5
    gross_trade = initial * .5
    assert values.iloc[-1] == pytest.approx(before - .01 * gross_trade)
    assert meta["transaction_cost_paid_pct"] / 100 == pytest.approx(1 - initial + .01 * gross_trade)


@pytest.mark.parametrize("frame", [prices({"A": [100, -1, 101]}), prices({"A": [100, np.nan, 101]}), prices({"A": [100, np.inf, 101]})])
def test_invalid_prices_rejected(frame):
    with pytest.raises(ValueError):
        PortfolioAnalytics(None)._simulate_rebalanced_portfolio(frame, {"A": 1}, .001, "monthly")


def year_frame():
    dates = pd.bdate_range(date.today() - timedelta(days=420), date.today() - timedelta(days=1))
    rng = np.random.default_rng(7)
    return pd.DataFrame({t: 100 * np.cumprod(1 + rng.normal(.0001, .01, len(dates))) for t in ["A", "B", "SPY", "AGG"]}, index=dates)


def portfolio():
    return {"total_value": 1000, "cash_remainder": 200, "allocations": [{"ticker": "A", "weight": .5, "current_value": 400}, {"ticker": "B", "weight": .5, "current_value": 400}]}


def test_horizon_not_extended_by_fetch_buffer():
    result = PortfolioAnalytics(History(year_frame()))._analyze_period(portfolio(), 1, BacktestConfig())
    assert result["status"] == "ok"
    assert pd.Timestamp(result["start_date"]) >= pd.Timestamp(date.today()) - pd.DateOffset(years=1)
    assert result["research_status"] == "historical_replay"


def test_missing_holding_does_not_silently_reweight():
    result = PortfolioAnalytics(History(year_frame().drop(columns="B")))._analyze_period(portfolio(), 1, BacktestConfig())
    assert result["status"] == "insufficient_data"


def test_short_history_cannot_be_labelled_five_years():
    result = PortfolioAnalytics(History(year_frame()))._analyze_period(portfolio(), 5, BacktestConfig())
    assert result["status"] == "insufficient_data"


def test_benchmark_with_shorter_history_is_unavailable():
    frame = year_frame()
    frame.loc[frame.index[:100], "SPY"] = np.nan
    result = PortfolioAnalytics(History(frame))._analyze_period(portfolio(), 1, BacktestConfig())
    assert result["status"] == "ok"
    assert result["benchmarks"]["sp500"] is None


def test_monte_carlo_cash_reduces_volatility_and_is_reproducible():
    analytics = PortfolioAnalytics(History(year_frame()))
    p = portfolio()
    invested = analytics.run_monte_carlo({**p, "cash_remainder": 0}, simulations=80, forecast_days=20)
    half_cash = analytics.run_monte_carlo({**p, "cash_remainder": 500}, simulations=80, forecast_days=20)
    assert half_cash["volatility_daily_pct"] == pytest.approx(invested["volatility_daily_pct"] * .5, abs=1e-6)
    assert half_cash == analytics.run_monte_carlo({**p, "cash_remainder": 500}, simulations=80, forecast_days=20)
    assert half_cash["method"] == "moving_block_bootstrap"


def test_monte_carlo_rejects_missing_holdings():
    assert PortfolioAnalytics(History(year_frame().drop(columns="B"))).run_monte_carlo(portfolio())["status"] == "insufficient_data"


def test_var_includes_cash_and_never_reports_negative_loss():
    model = MarketMicrostructureRiskModel(History(year_frame()))
    p = portfolio()
    full = model._var_cvar_payload(p["allocations"], 800)
    half = model._var_cvar_payload(p["allocations"], 1600)
    assert half["daily_var_pct"] == pytest.approx(full["daily_var_pct"] * .5)
    assert half["daily_var_dollars"] == pytest.approx(full["daily_var_dollars"])
    rising = prices({"A": list(range(100, 200)), "B": list(range(200, 300))})
    assert MarketMicrostructureRiskModel(History(rising))._var_cvar_payload(p["allocations"], 1000)["daily_var_pct"] == 0


def test_position_cap_retains_excess_as_cash(monkeypatch):
    engine = PortfolioEngine()
    monkeypatch.setattr(engine, "_build_weight_model", lambda stocks: [dict(ticker=str(i), name=str(i), price=100, conviction=1, annualized_volatility=.2, raw_score=score) for i, score in enumerate([100, 1, 1])])
    result = engine.calculate_allocation(10000, [1])
    assert max(a["cost"] for a in result["allocations"]) <= 2500 + 1e-8
    assert result["cash_remainder"] >= 2500 - 1e-8
    assert sum(a["weight"] for a in result["allocations"]) == pytest.approx(1)
    assert result["total_allocated"] + result["cash_remainder"] == pytest.approx(10000)


def test_live_news_failure_does_not_fabricate_headlines(monkeypatch):
    fetcher = StockDataFetcher()
    fetcher.set_demo_mode(False)
    monkeypatch.setattr("data_fetcher.yf.Ticker", lambda _: (_ for _ in ()).throw(RuntimeError("offline")))
    assert fetcher.get_news("AAPL") == []


def test_demo_news_explicitly_labelled():
    fetcher = StockDataFetcher()
    fetcher.set_demo_mode(True)
    assert all(item["is_synthetic"] and item["title"].startswith("[DEMO]") for item in fetcher.get_news("AAPL"))


def test_unknown_quote_time_is_not_fresh():
    quote = StockDataFetcher()._enrich_quote("A", {"price": 100, "timestamp": None, "source": "yfinance_fast_info"})
    assert quote["is_stale"] is True
    assert "TIMESTAMP_UNAVAILABLE" in quote["quality_flags"]


def test_history_fallback_replaces_instead_of_splicing(monkeypatch):
    fetcher = StockDataFetcher()
    fetcher.set_demo_mode(False)
    dates = pd.bdate_range("2025-01-01", periods=30)
    yahoo = pd.DataFrame({"Close": [100.] * 5}, index=dates[:5])
    stooq = pd.Series([200.] * 30, index=dates)
    monkeypatch.setattr("data_fetcher.yf.download", lambda **kwargs: yahoo)
    monkeypatch.setattr(fetcher, "_history_from_stooq", lambda *args: stooq)
    frame, quality = fetcher.get_price_history_frame(["A"], dates[0].date(), dates[-1].date())
    assert frame["A"].tolist() == [200.] * 30
    assert quality["A"]["price_basis"] == "unverified_adjustment"


def test_comparison_lines_start_at_same_value(tmp_path):
    from portfolio_tracker import PortfolioTracker
    class Recent:
        def get_bulk_recent_history(self, tickers, days):
            return {t: {"2025-01-02": 100., "2025-01-03": 110.} for t in tickers}
    p = {"investment_amount": 1000, "cash_remainder": 200, "allocations": [{"ticker": "A", "shares": 5, "price": 160}]}
    result = PortfolioTracker(data_dir=str(tmp_path)).build_comparison_trend(p, Recent())
    assert result["portfolio"][0] == result["sp500"][0] == result["sixty_forty"][0]
    assert result["portfolio"][1] == pytest.approx(1000 * 750 / 700, abs=.01)


def test_trend_never_backfills_from_current_price(tmp_path):
    from portfolio_tracker import PortfolioTracker
    class Recent:
        def get_bulk_recent_history(self, tickers, days):
            return {"A": {"2025-01-02": 100}}
    p = {"allocations": [{"ticker": "A", "shares": 1}, {"ticker": "B", "shares": 1, "price": 200}]}
    assert PortfolioTracker(data_dir=str(tmp_path)).build_market_trend(p, Recent())["values"] == []


def test_generate_portfolio_integration(tmp_path, monkeypatch):
    import json
    import app as app_module
    from portfolio_tracker import PortfolioTracker
    monkeypatch.setattr(app_module, "portfolio_tracker", PortfolioTracker(data_dir=str(tmp_path)))
    app_module.portfolio_engine.data_fetcher.set_demo_mode(True)
    response = app_module.app.test_client().post("/generate-portfolio", json={"amount": 10000, "strategies": ["Growth Investing"]})
    assert response.status_code == 200
    payload = response.get_json()
    # All API numbers must be strict JSON; NaN/Infinity must not escape to clients.
    json.dumps(payload, allow_nan=False)
    assert payload["backtest_analysis"]["research_status"] == "historical_replay"
    assert all(a["cost"] <= 2500 + 1e-8 for a in payload["allocations"])
    assert payload["monte_carlo"]["method"] == "moving_block_bootstrap"
