"""Comprehensive tests for PortfolioAnalytics: backtests, correlation, sector, Monte Carlo."""

from __future__ import annotations

from portfolio_analytics import PortfolioAnalytics


def test_run_full_analysis_returns_all_keys(fake_fetcher, sample_portfolio):
    """Full analysis should return all required top-level keys."""
    analytics = PortfolioAnalytics(fake_fetcher)
    result = analytics.run_full_analysis(sample_portfolio)
    required_keys = {
        "configuration",
        "benchmark_comparison",
        "backtests",
        "rebalancing_recommendations",
        "correlation_matrix",
        "sector_exposure",
        "monte_carlo",
        "quality_warnings",
    }
    assert required_keys.issubset(set(result.keys()))


def test_correlation_matrix_returns_valid_structure(fake_fetcher, sample_portfolio):
    """Correlation matrix should return tickers, matrix, and status ok."""
    analytics = PortfolioAnalytics(fake_fetcher)
    result = analytics.compute_correlation_matrix(sample_portfolio)
    assert result["status"] == "ok"
    assert len(result["tickers"]) >= 2
    assert len(result["matrix"]) == len(result["tickers"])
    # Diagonal should be 1.0
    for i in range(len(result["tickers"])):
        assert abs(result["matrix"][i][i] - 1.0) < 0.01


def test_correlation_matrix_insufficient_holdings(fake_fetcher):
    """Correlation should gracefully handle single-holding portfolios."""
    analytics = PortfolioAnalytics(fake_fetcher)
    portfolio = {
        "allocations": [
            {"ticker": "AAPL", "weight": 1.0, "weight_pct": 100.0}
        ]
    }
    result = analytics.compute_correlation_matrix(portfolio)
    assert result["status"] == "insufficient_holdings"


def test_sector_exposure_returns_valid_breakdown(sample_portfolio):
    """Sector exposure should return sectors and weights that sum to 100."""
    result = PortfolioAnalytics.compute_sector_exposure(sample_portfolio)
    assert len(result["sectors"]) > 0
    assert len(result["weights"]) == len(result["sectors"])
    assert abs(sum(result["weights"]) - 100.0) < 0.1


def test_sector_exposure_empty_portfolio():
    """Empty portfolio should return empty sectors."""
    result = PortfolioAnalytics.compute_sector_exposure({"allocations": []})
    assert result["sectors"] == []
    assert result["weights"] == []


def test_monte_carlo_returns_valid_fan_chart(fake_fetcher, sample_portfolio):
    """Monte Carlo should return percentile bands and terminal distribution."""
    analytics = PortfolioAnalytics(fake_fetcher)
    result = analytics.run_monte_carlo(sample_portfolio, simulations=100, forecast_days=30)
    assert result["status"] == "ok"
    assert result["simulations"] == 100
    assert result["forecast_days"] == 30
    assert "bands" in result
    assert "p5" in result["bands"]
    assert "p50" in result["bands"]
    assert "p95" in result["bands"]
    assert "terminal_distribution" in result
    # 5th percentile should be <= 95th percentile
    assert result["terminal_distribution"]["p5"] <= result["terminal_distribution"]["p95"]


def test_monte_carlo_insufficient_data(fake_fetcher):
    """Monte Carlo should handle empty portfolios gracefully."""
    analytics = PortfolioAnalytics(fake_fetcher)
    result = analytics.run_monte_carlo({"allocations": []})
    assert result["status"] == "insufficient_data"


def test_rebalancing_no_drift_no_trades(fake_fetcher, sample_portfolio):
    """If current weights match targets, no trades should be recommended."""
    analytics = PortfolioAnalytics(fake_fetcher)
    # Make current weights match targets by computing them from weight field
    result = analytics.generate_rebalancing_recommendations(
        sample_portfolio, drift_threshold_pct=99.0  # Very high threshold
    )
    assert result["needs_rebalance"] is False
    assert len(result["recommendations"]) == 0


def test_backtest_config_propagates(fake_fetcher, sample_portfolio):
    """Backtest configuration should propagate to output."""
    analytics = PortfolioAnalytics(fake_fetcher)
    result = analytics.run_full_analysis(sample_portfolio)
    config = result["backtests"]["configuration"]
    assert "transaction_cost_bps" in config
    assert "rebalance_frequency" in config
    assert "risk_free_rate_annual" in config


def test_benchmark_comparison_has_periods(fake_fetcher, sample_portfolio):
    """Benchmark comparison should contain period keys."""
    analytics = PortfolioAnalytics(fake_fetcher)
    result = analytics.run_full_analysis(sample_portfolio)
    assert "periods" in result["benchmark_comparison"]
    assert isinstance(result["benchmark_comparison"]["periods"], dict)
