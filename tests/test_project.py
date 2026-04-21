import app as app_module
from data_fetcher import StockDataFetcher
from portfolio_engine import PortfolioEngine
from strategies import STRATEGIES


def test_strategy_catalog_has_required_assets():
    required = {
        "Ethical Investing",
        "Growth Investing",
        "Index Investing",
        "Quality Investing",
        "Value Investing",
    }
    assert required.issubset(set(STRATEGIES.keys()))
    for name in required:
        assert len(STRATEGIES[name]["stocks"]) >= 3


def test_investment_validation_minimum_threshold():
    engine = PortfolioEngine()
    ok, error = engine.validate_investment(4999)
    assert ok is False
    assert "Minimum investment" in error



def test_generate_portfolio_rejects_invalid_strategy_count():
    client = app_module.app.test_client()

    response = client.post(
        "/generate-portfolio",
        json={"amount": 7000, "strategies": []},
    )
    assert response.status_code == 400
    assert "1 or 2" in response.get_json()["error"]



def test_generate_portfolio_rejects_non_list_strategies():
    client = app_module.app.test_client()

    response = client.post(
        "/generate-portfolio",
        json={"amount": 7000, "strategies": "Ethical Investing"},
    )
    assert response.status_code == 400
    assert "1 or 2" in response.get_json()["error"]



def test_demo_mode_quote_fallback_when_live_sources_fail(monkeypatch):
    fetcher = StockDataFetcher()
    fetcher.set_demo_mode(True)

    monkeypatch.setattr("data_fetcher.yf.Ticker", lambda _ticker: object())

    def _raise(*_args, **_kwargs):
        raise RuntimeError("network unavailable")

    monkeypatch.setattr(fetcher, "_quote_from_yfinance_fast_info", _raise)
    monkeypatch.setattr(fetcher, "_quote_from_yfinance_info", _raise)
    monkeypatch.setattr(fetcher, "_quote_from_yfinance_history", _raise)
    monkeypatch.setattr(fetcher, "_quote_from_stooq", _raise)

    quote = fetcher.get_quote("AAPL")

    assert quote is not None
    assert quote["source"] == "demo_mode_synthetic"
    assert "DEMO_MODE" in quote["quality_flags"]



def test_monitoring_snapshot_has_trend_and_counters(monkeypatch):
    fetcher = StockDataFetcher()
    fetcher.set_demo_mode(True)

    monkeypatch.setattr("data_fetcher.yf.Ticker", lambda _ticker: object())
    monkeypatch.setattr(fetcher, "_quote_from_yfinance_fast_info", lambda _stock: None)
    monkeypatch.setattr(fetcher, "_quote_from_yfinance_info", lambda _stock: None)
    monkeypatch.setattr(fetcher, "_quote_from_yfinance_history", lambda _stock: None)
    monkeypatch.setattr(fetcher, "_quote_from_stooq", lambda _ticker: None)

    _ = fetcher.get_quote("MSFT")
    snapshot = fetcher.get_monitoring_snapshot()

    assert "counters" in snapshot
    assert snapshot["counters"]["quote_requests"] >= 1
    assert len(snapshot["trend"]["labels"]) == 12



def test_demo_mode_endpoint_toggle_roundtrip():
    client = app_module.app.test_client()

    enable_response = client.post("/demo-mode", json={"enabled": True})
    assert enable_response.status_code == 200
    assert enable_response.get_json()["demo_mode_enabled"] is True

    disable_response = client.post("/demo-mode", json={"enabled": False})
    assert disable_response.status_code == 200
    assert disable_response.get_json()["demo_mode_enabled"] is False



def test_ops_monitor_endpoint_available():
    client = app_module.app.test_client()
    response = client.get("/ops-monitor")
    assert response.status_code == 200
    payload = response.get_json()
    assert "summary" in payload
    assert "counters" in payload



def test_export_csv_endpoint_returns_downloadable_csv():
    client = app_module.app.test_client()
    payload = {
        "investment_amount": 10000,
        "total_value": 10020,
        "cash_remainder": 20,
        "strategies": ["Index Investing"],
        "allocations": [
            {
                "ticker": "SPY",
                "name": "SPDR S&P 500 ETF Trust",
                "strategy": "Index Investing",
                "weight_pct": 100,
                "shares": 1.0,
                "price": 500,
                "current_price": 501,
                "cost": 500,
                "current_value": 501,
                "quote_source": "demo_mode_synthetic",
                "quote_is_stale": False,
            }
        ],
    }

    response = client.post("/export-csv", json=payload)
    assert response.status_code == 200
    assert "text/csv" in response.headers.get("Content-Type", "")
    assert "Ticker,Name,Strategy" in response.get_data(as_text=True)
