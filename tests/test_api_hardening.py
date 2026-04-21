from __future__ import annotations

import pandas as pd

import app as app_module
from risk_model import MarketMicrostructureRiskModel


class _HistoryFetcher:
    def get_price_history_frame(self, tickers, start_date, end_date):
        dates = pd.bdate_range(start=start_date, end=end_date)
        frame = pd.DataFrame(index=dates)
        for index, ticker in enumerate(tickers):
            frame[ticker] = 100 + index + (pd.Series(range(len(dates)), index=dates) * 0.2)
        return frame, {ticker: {"source": "demo_mode_synthetic", "points": len(frame)} for ticker in tickers}


def test_health_endpoint_has_request_id_and_scheduler_state():
    client = app_module.app.test_client()
    response = client.get("/health")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ok"
    assert "scheduler" in payload
    assert "X-Request-ID" in response.headers


def test_generate_portfolio_rejects_under_minimum_amount():
    client = app_module.app.test_client()
    response = client.post(
        "/generate-portfolio",
        json={"amount": 4999, "strategies": ["Ethical Investing"]},
    )
    assert response.status_code == 400
    assert "Minimum investment amount" in response.get_json()["error"]


def test_generate_portfolio_rejects_unknown_strategy_name():
    client = app_module.app.test_client()
    response = client.post(
        "/generate-portfolio",
        json={"amount": 7000, "strategies": ["Moonshot Investing"]},
    )
    assert response.status_code == 400
    assert "Unknown strategies" in response.get_json()["error"]


def test_refresh_portfolio_rejects_extra_fields():
    client = app_module.app.test_client()
    response = client.post(
        "/refresh-portfolio",
        json={
            "allocations": [
                {"ticker": "SPY", "shares": 1.0, "price": 500.0, "cost": 500.0, "unexpected": "field"}
            ],
            "cash_remainder": 0.0,
        },
    )
    assert response.status_code == 400
    assert "Invalid portfolio payload for refresh" in response.get_json()["error"]


def test_market_ticker_validation_rejects_non_list_holdings():
    client = app_module.app.test_client()
    response = client.post("/market-ticker", json={"holdings": "AAPL"})
    assert response.status_code == 400
    assert "Invalid market ticker request" in response.get_json()["error"]


def test_risk_payload_includes_stress_scenarios():
    fetcher = _HistoryFetcher()
    model = MarketMicrostructureRiskModel(fetcher)
    payload = model.build_portfolio_risk_payload(
        {
            "total_value": 15000.0,
            "allocations": [
                {
                    "ticker": "AAPL",
                    "asset_type": "Stock",
                    "weight": 0.6,
                    "weight_pct": 60.0,
                    "annualized_volatility": 0.22,
                    "current_value": 9000.0,
                    "current_price": 200.0,
                },
                {
                    "ticker": "ILTB",
                    "asset_type": "ETF",
                    "weight": 0.4,
                    "weight_pct": 40.0,
                    "annualized_volatility": 0.15,
                    "current_value": 6000.0,
                    "current_price": 50.0,
                },
            ],
        }
    )

    stress = payload["stress_tests"]
    assert len(stress["scenarios"]) >= 3
    scenario_kinds = {s.get("kind") for s in stress["scenarios"]}
    assert "historic" in scenario_kinds
    assert "hypothetical" in scenario_kinds
    assert "warning_triggered" in stress
