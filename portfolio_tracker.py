"""Portfolio historical tracking, comparison trends, and background refresh support."""

import hashlib
import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path


class PortfolioTracker:
    def __init__(self, data_dir="data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)
        self.history_file = self.data_dir / "portfolio_history.json"
        self.max_days = 5

    def _load_history(self):
        """Load portfolio history from disk."""
        if not self.history_file.exists():
            return {}

        try:
            with open(self.history_file, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except Exception as exc:
            print(f"Error loading history: {exc}")
            return {}

    def _save_history(self, history):
        """Persist portfolio history to disk."""
        try:
            with open(self.history_file, "w", encoding="utf-8") as handle:
                json.dump(history, handle, indent=2)
        except Exception as exc:
            print(f"Error saving history: {exc}")

    def _generate_portfolio_id(self, portfolio):
        """
        Generate a deterministic ID including composition + sizing.

        This avoids collisions when portfolios share tickers but differ by
        weights, share counts, strategies, or investment amount.
        """
        allocations = []
        for allocation in portfolio.get("allocations", []):
            allocations.append(
                {
                    "ticker": allocation.get("ticker"),
                    "shares": round(float(allocation.get("shares", 0.0)), 6),
                    "weight": round(float(allocation.get("weight", 0.0)), 6),
                }
            )
        allocations.sort(key=lambda item: (item["ticker"] or ""))

        fingerprint_payload = {
            "strategies": sorted(portfolio.get("strategies", [])),
            "investment_amount": round(float(portfolio.get("investment_amount", 0.0)), 2),
            "allocations": allocations,
        }
        fingerprint = hashlib.sha256(
            json.dumps(fingerprint_payload, sort_keys=True).encode("utf-8")
        ).hexdigest()[:16]
        return f"portfolio_{fingerprint}"

    def _get_close_on_or_before(self, date_to_close, date_label):
        """Return closest available close on or before `date_label`."""
        if date_label in date_to_close:
            return date_to_close[date_label]

        older_dates = [date for date in date_to_close if date <= date_label]
        if not older_dates:
            return None
        return date_to_close[max(older_dates)]

    def _portfolio_blueprint_from_payload(self, portfolio):
        """Persist the minimal deterministic payload required for background refresh."""
        allocations = []
        for allocation in portfolio.get("allocations", []):
            allocations.append(
                {
                    "ticker": allocation.get("ticker"),
                    "name": allocation.get("name"),
                    "strategy": allocation.get("strategy"),
                    "asset_type": allocation.get("asset_type", "Stock"),
                    "rationale": allocation.get("rationale", ""),
                    "conviction": float(allocation.get("conviction", 0.0)),
                    "annualized_volatility": float(allocation.get("annualized_volatility", 0.0)),
                    "weight": float(allocation.get("weight", 0.0)),
                    "weight_pct": float(allocation.get("weight_pct", 0.0)),
                    "shares": float(allocation.get("shares", 0.0)),
                    "price": float(allocation.get("price", 0.0)),
                    "cost": float(allocation.get("cost", 0.0)),
                }
            )

        return {
            "investment_amount": float(portfolio.get("investment_amount", 0.0)),
            "strategies": list(portfolio.get("strategies", [])),
            "allocation_method": portfolio.get(
                "allocation_method",
                "Conviction-weighted inverse-volatility model",
            ),
            "cash_remainder": float(portfolio.get("cash_remainder", 0.0)),
            "total_allocated": float(portfolio.get("total_allocated", 0.0)),
            "allocations": allocations,
        }

    def build_market_trend(self, portfolio, data_fetcher, days=5):
        """
        Build 5-day trend using real market close history for held assets.

        Returns:
            dict with `dates` and `values`
        """
        allocations = portfolio.get("allocations", [])
        if not allocations:
            return {"dates": [], "values": []}

        tickers = [allocation["ticker"] for allocation in allocations]
        history_map = data_fetcher.get_bulk_recent_history(tickers, days=days)
        if not history_map:
            return {"dates": [], "values": []}

        date_set = set()
        for ticker_history in history_map.values():
            date_set.update(ticker_history.keys())

        dates = sorted(date_set)[-days:]
        values = []
        cash_remainder = portfolio.get("cash_remainder", 0.0)

        for date_label in dates:
            day_total = cash_remainder
            for allocation in allocations:
                ticker = allocation["ticker"]
                ticker_history = history_map.get(ticker, {})
                close_price = self._get_close_on_or_before(ticker_history, date_label)
                if close_price is None:
                    close_price = allocation.get("price", 0.0)
                day_total += allocation["shares"] * close_price
            values.append(round(day_total, 2))

        return {"dates": dates, "values": values}

    def build_comparison_trend(self, portfolio, data_fetcher, days=30):
        """
        Build normalized multi-line trend for Portfolio vs SPY vs 60/40.

        Returns:
            dict with `dates`, `portfolio`, `sp500`, `sixty_forty`
        """
        allocations = portfolio.get("allocations", [])
        if not allocations:
            return {"dates": [], "portfolio": [], "sp500": [], "sixty_forty": []}

        benchmark_tickers = ["SPY", "AGG"]
        tickers = [allocation["ticker"] for allocation in allocations] + benchmark_tickers
        history_map = data_fetcher.get_bulk_recent_history(tickers, days=days)
        if not history_map:
            return {"dates": [], "portfolio": [], "sp500": [], "sixty_forty": []}

        date_set = set()
        for ticker_history in history_map.values():
            date_set.update(ticker_history.keys())
        dates = sorted(date_set)[-days:]
        if not dates:
            return {"dates": [], "portfolio": [], "sp500": [], "sixty_forty": []}

        cash_remainder = float(portfolio.get("cash_remainder", 0.0))
        portfolio_values = []
        for date_label in dates:
            day_total = cash_remainder
            for allocation in allocations:
                ticker = allocation["ticker"]
                ticker_history = history_map.get(ticker, {})
                close_price = self._get_close_on_or_before(ticker_history, date_label)
                if close_price is None:
                    close_price = allocation.get("current_price", allocation.get("price", 0.0))
                day_total += float(allocation.get("shares", 0.0)) * float(close_price)
            portfolio_values.append(float(day_total))

        base_value = float(portfolio.get("investment_amount") or 0.0)
        if base_value <= 0 and portfolio_values:
            base_value = float(portfolio_values[0])
        if base_value <= 0:
            base_value = 1.0

        spy_history = history_map.get("SPY", {})
        agg_history = history_map.get("AGG", {})
        spy_initial = self._get_close_on_or_before(spy_history, dates[0]) or 0.0
        agg_initial = self._get_close_on_or_before(agg_history, dates[0]) or 0.0
        if spy_initial <= 0:
            spy_initial = 1.0
        if agg_initial <= 0:
            agg_initial = 1.0

        sp500_values = []
        sixty_forty_values = []
        last_spy_ratio = 1.0
        last_agg_ratio = 1.0
        for date_label in dates:
            spy_close = self._get_close_on_or_before(spy_history, date_label)
            agg_close = self._get_close_on_or_before(agg_history, date_label)

            if spy_close and spy_close > 0:
                last_spy_ratio = float(spy_close) / float(spy_initial)
            if agg_close and agg_close > 0:
                last_agg_ratio = float(agg_close) / float(agg_initial)

            sp500_values.append(base_value * last_spy_ratio)
            sixty_forty_values.append(base_value * (0.6 * last_spy_ratio + 0.4 * last_agg_ratio))

        return {
            "dates": dates,
            "portfolio": [round(value, 2) for value in portfolio_values],
            "sp500": [round(value, 2) for value in sp500_values],
            "sixty_forty": [round(value, 2) for value in sixty_forty_values],
        }

    def save_portfolio_snapshot(self, portfolio):
        """Save (or replace) today's snapshot for this portfolio."""
        portfolio_id = self._generate_portfolio_id(portfolio)
        history = self._load_history()

        if portfolio_id not in history:
            history[portfolio_id] = {
                "created_date": datetime.now().strftime("%Y-%m-%d"),
                "strategies": portfolio.get("strategies", []),
                "snapshots": [],
            }

        history[portfolio_id]["portfolio_blueprint"] = self._portfolio_blueprint_from_payload(portfolio)

        snapshot = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "timestamp": datetime.now().isoformat(),
            "total_value": portfolio.get("total_value", 0.0),
            "allocations": [],
        }

        for allocation in portfolio.get("allocations", []):
            snapshot["allocations"].append(
                {
                    "ticker": allocation["ticker"],
                    "shares": allocation["shares"],
                    "price": allocation.get("current_price", allocation.get("price", 0.0)),
                    "value": allocation.get("current_value", allocation.get("cost", 0.0)),
                }
            )

        today = snapshot["date"]
        existing_snapshots = history[portfolio_id]["snapshots"]
        existing_snapshots = [item for item in existing_snapshots if item["date"] != today]
        existing_snapshots.append(snapshot)
        existing_snapshots = sorted(existing_snapshots, key=lambda item: item["date"])[-self.max_days :]

        history[portfolio_id]["snapshots"] = existing_snapshots
        self._save_history(history)
        return portfolio_id

    def list_saved_portfolio_blueprints(self):
        """Return `{portfolio_id: blueprint}` for background refresh jobs."""
        history = self._load_history()
        blueprints = {}
        for portfolio_id, entry in history.items():
            blueprint = entry.get("portfolio_blueprint")
            if isinstance(blueprint, dict) and blueprint.get("allocations"):
                blueprints[portfolio_id] = deepcopy(blueprint)
        return blueprints

    def refresh_all_saved_portfolios(self, portfolio_engine):
        """
        Refresh market values for all known portfolio blueprints.

        Returns:
            dict with `updated_count` and `portfolio_ids`.
        """
        blueprints = self.list_saved_portfolio_blueprints()
        if not blueprints:
            return {"updated_count": 0, "portfolio_ids": []}

        updated_ids = []
        for portfolio_id, blueprint in blueprints.items():
            try:
                refreshed = portfolio_engine.calculate_portfolio_value(deepcopy(blueprint))
                refreshed["portfolio_id"] = portfolio_id
                self.save_portfolio_snapshot(refreshed)
                updated_ids.append(portfolio_id)
            except Exception as exc:
                print(f"Background refresh failed for {portfolio_id}: {exc}")

        return {"updated_count": len(updated_ids), "portfolio_ids": updated_ids}

    def get_portfolio_history(self, portfolio_id):
        """Return historical snapshots for one portfolio ID."""
        history = self._load_history()
        if portfolio_id not in history:
            return []
        return history[portfolio_id]["snapshots"]

    def list_saved_portfolios_summary(self):
        """Return a list of saved portfolios with metadata for the UI sidebar."""
        history = self._load_history()
        summaries = []
        for portfolio_id, entry in history.items():
            blueprint = entry.get("portfolio_blueprint") or {}
            snapshots = entry.get("snapshots") or []
            latest = snapshots[-1] if snapshots else {}
            summaries.append({
                "portfolio_id": portfolio_id,
                "strategies": blueprint.get("strategies") or entry.get("strategies") or [],
                "investment_amount": blueprint.get("investment_amount", 0.0),
                "created_date": entry.get("created_date"),
                "last_snapshot_date": latest.get("date"),
                "last_total_value": latest.get("total_value"),
                "ticker_count": len(blueprint.get("allocations") or []),
            })
        summaries.sort(key=lambda item: (item.get("last_snapshot_date") or "", item["portfolio_id"]), reverse=True)
        return summaries

    def load_saved_portfolio_blueprint(self, portfolio_id):
        """Return the stored blueprint for a portfolio_id, or None."""
        history = self._load_history()
        entry = history.get(portfolio_id)
        if not entry:
            return None
        blueprint = entry.get("portfolio_blueprint")
        if not isinstance(blueprint, dict) or not blueprint.get("allocations"):
            return None
        return deepcopy(blueprint)

    def get_trend_data(self, portfolio_id):
        """Return saved snapshot trend for one portfolio."""
        snapshots = self.get_portfolio_history(portfolio_id)
        if not snapshots:
            return {"dates": [], "values": []}
        return {
            "dates": [snapshot["date"] for snapshot in snapshots],
            "values": [snapshot["total_value"] for snapshot in snapshots],
        }
