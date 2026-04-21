"""Tests for PortfolioTracker: snapshot persistence, trend building."""

from __future__ import annotations

import json

from portfolio_tracker import PortfolioTracker


def test_save_and_load_snapshot_roundtrip(tmp_path, sample_portfolio):
    """Saving a snapshot should persist it and be loadable."""
    tracker = PortfolioTracker(data_dir=str(tmp_path))
    tracker.save_portfolio_snapshot(sample_portfolio)

    history_file = tmp_path / "portfolio_history.json"
    assert history_file.exists()

    with open(history_file) as f:
        data = json.load(f)

    assert isinstance(data, (dict, list))


def test_trend_returns_dates_and_values(tmp_path, sample_portfolio):
    """Trend should return date and value arrays of equal length."""
    tracker = PortfolioTracker(data_dir=str(tmp_path))
    portfolio_id = sample_portfolio.get("portfolio_id", "test-abc123")
    for i in range(3):
        snap = {**sample_portfolio, "total_value": 5757.0 + i * 10}
        tracker.save_portfolio_snapshot(snap)

    trend = tracker.get_trend_data(portfolio_id)
    assert "dates" in trend
    assert "values" in trend
    assert len(trend["dates"]) == len(trend["values"])


def test_portfolio_history_returns_list(tmp_path, sample_portfolio):
    """get_portfolio_history should return saved snapshots."""
    tracker = PortfolioTracker(data_dir=str(tmp_path))
    portfolio_id = sample_portfolio.get("portfolio_id", "test-abc123")
    tracker.save_portfolio_snapshot({**sample_portfolio, "total_value": 1000.0})
    tracker.save_portfolio_snapshot({**sample_portfolio, "total_value": 2000.0})

    history = tracker.get_portfolio_history(portfolio_id)
    assert isinstance(history, list)


def test_empty_tracker_returns_empty_history(tmp_path):
    """A new tracker with no saved data should return empty history."""
    tracker = PortfolioTracker(data_dir=str(tmp_path))
    result = tracker.get_portfolio_history("nonexistent-id")
    assert isinstance(result, list)
    assert len(result) == 0


def test_trend_with_no_snapshots_returns_empty(tmp_path):
    """Trend from a fresh tracker should return empty arrays."""
    tracker = PortfolioTracker(data_dir=str(tmp_path))
    trend = tracker.get_trend_data("nonexistent-id")
    assert trend["dates"] == []
    assert trend["values"] == []
