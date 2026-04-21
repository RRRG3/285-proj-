from __future__ import annotations

import pandas as pd

from alerting import AlertingEngine
from data_fetcher import StockDataFetcher
from risk_model import MarketMicrostructureRiskModel
from schemas import GeneratePortfolioRequest


class FakeHistoryFetcher:
    def get_price_history_frame(self, tickers, start_date, end_date):
        dates = pd.bdate_range(start=start_date, end=end_date)
        frame = pd.DataFrame(index=dates)
        for index, ticker in enumerate(tickers):
            frame[ticker] = 100 + (index * 3) + (pd.Series(range(len(dates)), index=dates) * (0.1 + index * 0.02))
        quality = {ticker: {"source": "demo_mode_synthetic", "points": len(frame)} for ticker in tickers}
        return frame, quality


def test_schema_limits_strategies_to_two():
    request = GeneratePortfolioRequest(amount=10000, strategies=["Ethical Investing", "Value Investing"])
    assert len(request.strategies) == 2



def test_alerting_engine_persists_active_and_resolved(tmp_path):
    path = tmp_path / "alerts.json"
    engine = AlertingEngine(path=str(path))

    triggered = engine.evaluate(
        {
            "failure_rate_pct": 8.0,
            "counters": {"fallback_quotes": 30, "stale_quotes": 0},
        }
    )
    assert triggered["active_count"] >= 1

    resolved = engine.evaluate(
        {
            "failure_rate_pct": 0.1,
            "counters": {"fallback_quotes": 0, "stale_quotes": 0},
        }
    )
    assert resolved["active_count"] == 0
    assert len(resolved["history"]) >= 1



def test_demo_mode_short_circuits_external_quote_calls(monkeypatch):
    fetcher = StockDataFetcher()
    fetcher.set_demo_mode(True)

    def should_not_call(*_args, **_kwargs):
        raise AssertionError("external provider should not be called in demo mode")

    monkeypatch.setattr("data_fetcher.yf.Ticker", should_not_call)

    quote = fetcher.get_quote("AAPL")
    assert quote is not None
    assert quote["source"] == "demo_mode_synthetic"



def test_risk_model_produces_var_and_execution_payload():
    fetcher = FakeHistoryFetcher()
    model = MarketMicrostructureRiskModel(fetcher)

    portfolio = {
        "total_value": 12000,
        "allocations": [
            {
                "ticker": "AAPL",
                "weight": 0.5,
                "weight_pct": 50,
                "annualized_volatility": 0.2,
                "current_value": 6000,
                "current_price": 200,
            },
            {
                "ticker": "MSFT",
                "weight": 0.5,
                "weight_pct": 50,
                "annualized_volatility": 0.18,
                "current_value": 6000,
                "current_price": 300,
            },
        ],
    }

    payload = model.build_portfolio_risk_payload(portfolio)

    assert "execution_summary" in payload
    assert payload["execution_summary"]["expected_total_cost"] > 0
    assert payload["var_cvar"]["status"] == "ok"
    assert payload["var_cvar"]["daily_var_pct"] is not None
