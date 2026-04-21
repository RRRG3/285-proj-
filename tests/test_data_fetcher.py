"""Comprehensive tests for StockDataFetcher: caching, demo mode, reliability scoring."""

from __future__ import annotations

from data_fetcher import StockDataFetcher


def test_demo_mode_source_tag(demo_fetcher):
    """Quotes from demo mode should be tagged as demo_mode_synthetic."""
    quote = demo_fetcher.get_quote("AAPL")
    assert quote is not None
    assert quote["source"] == "demo_mode_synthetic"
    assert "DEMO_MODE" in quote["quality_flags"]


def test_cache_hit_returns_same_object(demo_fetcher):
    """A second get_quote call within cache TTL should return the cached result."""
    first = demo_fetcher.get_quote("MSFT")
    second = demo_fetcher.get_quote("MSFT")
    assert first["price"] == second["price"]
    snapshot = demo_fetcher.get_monitoring_snapshot()
    assert snapshot["counters"]["quote_requests"] >= 1


def test_monitoring_snapshot_structure(demo_fetcher):
    """Monitoring snapshot should contain counters and trend buckets."""
    demo_fetcher.get_quote("AAPL")
    snapshot = demo_fetcher.get_monitoring_snapshot()

    assert "counters" in snapshot
    assert "trend" in snapshot
    assert "recent_errors" in snapshot
    assert len(snapshot["trend"]["labels"]) == 12
    assert snapshot["counters"]["quote_requests"] >= 1


def test_market_clock_returns_valid_structure():
    """Market clock should return a dict with market_status key."""
    fetcher = StockDataFetcher()
    clock = fetcher.get_market_clock()
    assert isinstance(clock, dict)
    assert "market_status" in clock
    assert clock["market_status"] in {"OPEN", "PRE_MARKET", "AFTER_HOURS", "CLOSED"}


def test_quote_enrichment_adds_quality_flags(demo_fetcher):
    """Demo quote should contain reliability_score and quality_flags."""
    quote = demo_fetcher.get_quote("AAPL")
    assert "reliability_score" in quote
    assert "quality_flags" in quote
    assert isinstance(quote["quality_flags"], list)


def test_demo_mode_toggle():
    """set_demo_mode should toggle the internal flag."""
    fetcher = StockDataFetcher()
    initial_state = fetcher.demo_mode_enabled
    assert isinstance(initial_state, bool)
    fetcher.set_demo_mode(True)
    assert fetcher.demo_mode_enabled is True
    fetcher.set_demo_mode(False)
    assert fetcher.demo_mode_enabled is False


def test_demo_mode_get_multiple_prices(demo_fetcher):
    """get_multiple_prices in demo mode should return prices for all tickers."""
    prices = demo_fetcher.get_multiple_prices(["AAPL", "MSFT", "VTI"])
    assert len(prices) == 3
    for ticker, price in prices.items():
        # get_multiple_prices returns {ticker: float}
        assert isinstance(price, (int, float))
        assert price > 0


def test_demo_price_history_frame(demo_fetcher):
    """Demo mode should return a price history frame with no network calls."""
    from datetime import date, timedelta
    end = date.today()
    start = end - timedelta(days=60)
    frame, quality = demo_fetcher.get_price_history_frame(["AAPL", "MSFT"], start, end)
    assert not frame.empty
    assert "AAPL" in frame.columns
    assert "MSFT" in frame.columns
    for ticker in ["AAPL", "MSFT"]:
        assert quality[ticker]["source"] == "demo_mode_synthetic"


def test_get_annualized_volatility_demo(demo_fetcher):
    """Volatility computation should return a positive float in demo mode."""
    vol = demo_fetcher.get_annualized_volatility("AAPL")
    assert isinstance(vol, float)
    assert vol > 0


def test_summarize_quote_quality(demo_fetcher):
    """Quality summary should aggregate flags across multiple quotes."""
    q1 = demo_fetcher.get_quote("AAPL")
    q2 = demo_fetcher.get_quote("MSFT")
    quotes = [q1, q2]
    summary = demo_fetcher.summarize_quote_quality(quotes)
    assert isinstance(summary, dict)
    assert "quotes_received" in summary or "market_status" in summary
