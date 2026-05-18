"""Shared pytest fixtures for the Alloc8 test suite."""

from __future__ import annotations

import pandas as pd
import pytest

import app as app_module
from data_fetcher import StockDataFetcher

# -------------------------------------------------------------------
# Fake data providers
# -------------------------------------------------------------------


class FakeHistoryFetcher:
    """Deterministic price history for unit tests."""

    def get_price_history_frame(self, tickers, start_date, end_date):
        dates = pd.bdate_range(start=start_date, end=end_date)
        frame = pd.DataFrame(index=dates)
        for index, ticker in enumerate(tickers):
            base = 100 + index * 10
            trend = pd.Series(range(len(dates)), index=dates) * (0.1 + index * 0.02)
            frame[ticker] = base + trend
        quality = {
            ticker: {"source": "demo_mode_synthetic", "points": len(frame)}
            for ticker in tickers
        }
        return frame, quality


# -------------------------------------------------------------------
# Fixtures
# -------------------------------------------------------------------


@pytest.fixture()
def fake_fetcher():
    """Return a FakeHistoryFetcher suitable for analytics and risk model tests."""
    return FakeHistoryFetcher()


@pytest.fixture()
def demo_fetcher(monkeypatch):
    """Return a StockDataFetcher wired into demo mode with external calls disabled."""
    fetcher = StockDataFetcher()
    fetcher.set_demo_mode(True)

    def _should_not_call(*_args, **_kwargs):
        raise AssertionError("External provider should not be called in demo mode")

    monkeypatch.setattr("data_fetcher.yf.Ticker", _should_not_call)
    return fetcher


@pytest.fixture()
def flask_client():
    """Return a Flask test client with demo mode enabled."""
    app_module.portfolio_engine.data_fetcher.set_demo_mode(True)
    client = app_module.app.test_client()
    yield client
    app_module.portfolio_engine.data_fetcher.set_demo_mode(False)


@pytest.fixture()
def sample_allocations():
    """Return a realistic portfolio allocations list for testing."""
    return [
        {
            "ticker": "AAPL",
            "name": "Apple Inc.",
            "strategy": "Ethical Investing",
            "asset_type": "Stock",
            "sector": "Technology",
            "rationale": "Carbon neutral commitment",
            "conviction": 0.92,
            "annualized_volatility": 0.22,
            "weight": 0.35,
            "weight_pct": 35.0,
            "shares": 10.5,
            "price": 190.0,
            "cost": 1995.0,
            "current_price": 192.0,
            "current_value": 2016.0,
            "quote_source": "demo_mode_synthetic",
            "quote_is_stale": False,
        },
        {
            "ticker": "MSFT",
            "name": "Microsoft Corporation",
            "strategy": "Ethical Investing",
            "asset_type": "Stock",
            "sector": "Technology",
            "rationale": "Carbon negative target",
            "conviction": 0.89,
            "annualized_volatility": 0.20,
            "weight": 0.30,
            "weight_pct": 30.0,
            "shares": 5.0,
            "price": 340.0,
            "cost": 1700.0,
            "current_price": 345.0,
            "current_value": 1725.0,
            "quote_source": "demo_mode_synthetic",
            "quote_is_stale": False,
        },
        {
            "ticker": "VTI",
            "name": "Vanguard Total Stock Market ETF",
            "strategy": "Index Investing",
            "asset_type": "ETF",
            "sector": "Broad Market",
            "rationale": "Broad U.S. equity beta",
            "conviction": 0.94,
            "annualized_volatility": 0.15,
            "weight": 0.35,
            "weight_pct": 35.0,
            "shares": 8.0,
            "price": 250.0,
            "cost": 2000.0,
            "current_price": 252.0,
            "current_value": 2016.0,
            "quote_source": "demo_mode_synthetic",
            "quote_is_stale": False,
        },
    ]


@pytest.fixture()
def sample_portfolio(sample_allocations):
    """Return a complete portfolio dict suitable for analytics and risk tests."""
    return {
        "portfolio_id": "test-abc123",
        "investment_amount": 6000.0,
        "total_value": 5757.0,
        "strategies": ["Ethical Investing", "Index Investing"],
        "allocation_method": "Conviction-Weighted Inverse Volatility",
        "cash_remainder": 305.0,
        "total_allocated": 5695.0,
        "allocations": sample_allocations,
    }
