"""Microstructure-aware execution and portfolio risk analytics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, cast

import numpy as np
import pandas as pd


@dataclass
class RiskConfig:
    participation_rate: float = 0.10
    commission_bps: float = 1.0
    spread_floor_bps: float = 2.0
    spread_volatility_multiplier: float = 35.0
    impact_coefficient_bps: float = 18.0
    var_confidence: float = 0.95
    portfolio_var_limit_pct: float = 2.5
    max_single_position_pct: float = 25.0
    stress_warning_drawdown_pct: float = -8.0


ADV_HINTS_USD = {
    "AAPL": 11_000_000_000,
    "MSFT": 9_000_000_000,
    "NVDA": 15_000_000_000,
    "AMZN": 8_000_000_000,
    "META": 7_000_000_000,
    "SPY": 35_000_000_000,
    "QQQ": 18_000_000_000,
    "VTI": 2_500_000_000,
    "BRK-B": 1_800_000_000,
    "BAC": 2_400_000_000,
    "CVX": 1_700_000_000,
}


class MarketMicrostructureRiskModel:
    def __init__(self, data_fetcher, config: RiskConfig | None = None):
        self.data_fetcher = data_fetcher
        self.config = config or RiskConfig()

    def _estimate_adv_dollars(self, ticker: str, price: float) -> float:
        hinted = ADV_HINTS_USD.get(ticker)
        if hinted:
            return float(hinted)

        # Fallback ADV proxy based on price bucket.
        if price >= 400:
            return 2_000_000_000.0
        if price >= 100:
            return 900_000_000.0
        if price >= 50:
            return 450_000_000.0
        return 180_000_000.0

    def _effective_spread_bps(self, annualized_volatility: float) -> float:
        return max(
            self.config.spread_floor_bps,
            annualized_volatility * self.config.spread_volatility_multiplier,
        )

    def _market_impact_bps(self, trade_notional: float, adv_dollars: float) -> float:
        if adv_dollars <= 0:
            return self.config.impact_coefficient_bps

        execution_bucket = max(adv_dollars * self.config.participation_rate, 1.0)
        effective_participation = max(trade_notional, 0.0) / execution_bucket
        return self.config.impact_coefficient_bps * np.sqrt(max(effective_participation, 0.0))

    @staticmethod
    def _asset_bucket(allocation: dict[str, Any]) -> str:
        ticker = str(allocation.get("ticker", "")).upper()
        asset_type = str(allocation.get("asset_type", "Stock")).upper()
        if asset_type == "ETF" and ticker in {"AGG", "ILTB", "TLT", "BND"}:
            return "BOND"
        if asset_type == "ETF":
            return "EQUITY"
        return "EQUITY"

    def _execution_cost_payload(self, allocation: dict[str, Any]) -> dict[str, Any]:
        ticker = allocation.get("ticker")
        current_value = float(allocation.get("current_value", allocation.get("cost", 0.0)))
        annualized_vol = float(allocation.get("annualized_volatility", 0.25))
        price = float(allocation.get("current_price", allocation.get("price", 1.0)) or 1.0)

        adv_dollars = self._estimate_adv_dollars(str(ticker), price)
        notional = current_value
        spread_bps = self._effective_spread_bps(annualized_vol)
        impact_bps = self._market_impact_bps(notional, adv_dollars)
        commission_bps = self.config.commission_bps
        total_bps = commission_bps + (spread_bps * 0.5) + impact_bps
        expected_cost = notional * total_bps / 10_000.0

        return {
            "ticker": ticker,
            "notional": notional,
            "adv_dollars": adv_dollars,
            "spread_bps": spread_bps,
            "impact_bps": impact_bps,
            "commission_bps": commission_bps,
            "total_cost_bps": total_bps,
            "expected_execution_cost": expected_cost,
        }

    def _portfolio_returns(self, allocations: list[dict[str, Any]]) -> pd.Series:
        if not allocations:
            return pd.Series(dtype="float64")

        tickers = [allocation.get("ticker") for allocation in allocations if allocation.get("ticker")]
        if not tickers:
            return pd.Series(dtype="float64")

        end_date = date.today()
        start_date = end_date - timedelta(days=420)
        frame, _ = self.data_fetcher.get_price_history_frame(tickers, start_date, end_date)
        if frame.empty:
            return pd.Series(dtype="float64")

        weights = {
            allocation["ticker"]: float(allocation.get("weight", 0.0))
            for allocation in allocations
            if allocation.get("ticker") in frame.columns
        }
        if not weights:
            return pd.Series(dtype="float64")

        total = sum(weights.values())
        if total <= 0:
            return pd.Series(dtype="float64")

        normalized = {ticker: value / total for ticker, value in weights.items()}
        aligned = frame[list(normalized.keys())].ffill().dropna()
        if aligned.shape[0] < 30:
            return pd.Series(dtype="float64")

        returns = aligned.pct_change().dropna()
        portfolio_returns = sum(returns[ticker] * weight for ticker, weight in normalized.items())
        return portfolio_returns

    def _var_cvar_payload(self, allocations: list[dict[str, Any]], portfolio_value: float) -> dict[str, Any]:
        returns = self._portfolio_returns(allocations)
        if returns.empty:
            return {
                "status": "insufficient_data",
                "daily_var_pct": None,
                "daily_cvar_pct": None,
                "daily_var_dollars": None,
                "daily_cvar_dollars": None,
                "annualized_volatility_pct": None,
            }

        alpha = 1.0 - self.config.var_confidence
        quantile = float(np.quantile(returns, alpha))
        tail_returns = returns[returns <= quantile]
        cvar = float(tail_returns.mean()) if not tail_returns.empty else quantile

        annualized_vol = float(returns.std() * np.sqrt(252.0))

        daily_var_pct = -quantile * 100.0
        daily_cvar_pct = -cvar * 100.0

        return {
            "status": "ok",
            "daily_var_pct": daily_var_pct,
            "daily_cvar_pct": daily_cvar_pct,
            "daily_var_dollars": portfolio_value * daily_var_pct / 100.0,
            "daily_cvar_dollars": portfolio_value * daily_cvar_pct / 100.0,
            "annualized_volatility_pct": annualized_vol * 100.0,
        }

    def _limit_checks(self, allocations: list[dict[str, Any]], var_payload: dict[str, Any]) -> list[dict[str, Any]]:
        breaches: list[dict[str, Any]] = []

        for allocation in allocations:
            position_pct = float(allocation.get("weight_pct", 0.0))
            if position_pct > self.config.max_single_position_pct:
                breaches.append(
                    {
                        "rule": "MAX_SINGLE_POSITION",
                        "severity": "high",
                        "message": (
                            f"{allocation.get('ticker')} weight {position_pct:.2f}% exceeds "
                            f"limit {self.config.max_single_position_pct:.2f}%"
                        ),
                    }
                )

        daily_var_pct = var_payload.get("daily_var_pct")
        if isinstance(daily_var_pct, (int, float)) and daily_var_pct > self.config.portfolio_var_limit_pct:
            breaches.append(
                {
                    "rule": "PORTFOLIO_DAILY_VAR",
                    "severity": "medium",
                    "message": (
                        f"Daily VaR {daily_var_pct:.2f}% exceeds "
                        f"limit {self.config.portfolio_var_limit_pct:.2f}%"
                    ),
                }
            )

        return breaches

    def _stress_test_payload(self, allocations: list[dict[str, Any]], portfolio_value: float) -> dict[str, Any]:
        scenarios: list[dict[str, Any]] = [
            {
                "name": "GFC 2008 (Lehman)",
                "label": "Global Financial Crisis",
                "horizon": "Sept 2008 – Mar 2009",
                "moves": {"EQUITY": -0.38, "BOND": 0.05},
                "kind": "historic",
            },
            {
                "name": "COVID-19 Crash 2020",
                "label": "COVID Drawdown",
                "horizon": "Feb – Mar 2020",
                "moves": {"EQUITY": -0.34, "BOND": -0.03},
                "kind": "historic",
            },
            {
                "name": "Dot-com 2000–02",
                "label": "Dot-com Bust",
                "horizon": "Mar 2000 – Oct 2002",
                "moves": {"EQUITY": -0.45, "BOND": 0.05},
                "kind": "historic",
            },
            {
                "name": "Inflation Shock 2022",
                "label": "Stagflation Tape",
                "horizon": "Jan – Oct 2022",
                "moves": {"EQUITY": -0.19, "BOND": -0.13},
                "kind": "historic",
            },
            {
                "name": "Black Monday 1987",
                "label": "Single-day Crash",
                "horizon": "19 Oct 1987",
                "moves": {"EQUITY": -0.22, "BOND": -0.02},
                "kind": "historic",
            },
            {
                "name": "Equity Shock -8%",
                "label": "Generic Sell-off",
                "horizon": "Hypothetical",
                "moves": {"EQUITY": -0.08, "BOND": -0.015},
                "kind": "hypothetical",
            },
            {
                "name": "Rates +100bp",
                "label": "Rate Shock",
                "horizon": "Hypothetical",
                "moves": {"EQUITY": -0.01, "BOND": -0.06},
                "kind": "hypothetical",
            },
            {
                "name": "Volatility Spike",
                "label": "Vol Regime",
                "horizon": "Hypothetical",
                "moves": {"EQUITY": -0.05, "BOND": -0.02},
                "kind": "hypothetical",
            },
        ]
        scenario_rows: list[dict[str, Any]] = []
        worst_case_pct = 0.0

        for scenario in scenarios:
            impacts: list[tuple[str, float]] = []
            pnl_dollars = 0.0
            for allocation in allocations:
                ticker = str(allocation.get("ticker", "UNKNOWN"))
                current_value = float(allocation.get("current_value", allocation.get("cost", 0.0)) or 0.0)
                bucket = self._asset_bucket(allocation)
                shock_map = cast(dict[str, float], scenario["moves"])
                shock_return = float(shock_map.get(bucket, 0.0))
                contribution = current_value * shock_return
                impacts.append((ticker, contribution))
                pnl_dollars += contribution

            pnl_pct = ((pnl_dollars / portfolio_value) * 100.0) if portfolio_value > 0 else 0.0
            worst_position = min(impacts, key=lambda item: item[1], default=("N/A", 0.0))
            scenario_rows.append(
                {
                    "name": scenario["name"],
                    "label": scenario.get("label", scenario["name"]),
                    "horizon": scenario.get("horizon", ""),
                    "kind": scenario.get("kind", "hypothetical"),
                    "pnl_dollars": pnl_dollars,
                    "pnl_pct": pnl_pct,
                    "worst_position_ticker": worst_position[0],
                    "worst_position_pnl": worst_position[1],
                }
            )
            worst_case_pct = min(worst_case_pct, pnl_pct)

        return {
            "scenarios": scenario_rows,
            "worst_case_pct": worst_case_pct,
            "warning_threshold_pct": self.config.stress_warning_drawdown_pct,
            "warning_triggered": worst_case_pct <= self.config.stress_warning_drawdown_pct,
        }

    def build_portfolio_risk_payload(self, portfolio: dict[str, Any]) -> dict[str, Any]:
        allocations = portfolio.get("allocations", [])
        portfolio_value = float(portfolio.get("total_value", 0.0) or 0.0)

        execution_rows = [self._execution_cost_payload(allocation) for allocation in allocations]
        total_expected_cost = float(sum(item["expected_execution_cost"] for item in execution_rows))
        weighted_cost_bps = (
            (total_expected_cost / portfolio_value) * 10_000.0 if portfolio_value > 0 else 0.0
        )

        var_payload = self._var_cvar_payload(allocations, portfolio_value)
        breaches = self._limit_checks(allocations, var_payload)
        stress_payload = self._stress_test_payload(allocations, portfolio_value)

        return {
            "config": {
                "participation_rate": self.config.participation_rate,
                "commission_bps": self.config.commission_bps,
                "var_confidence": self.config.var_confidence,
                "portfolio_var_limit_pct": self.config.portfolio_var_limit_pct,
                "max_single_position_pct": self.config.max_single_position_pct,
                "stress_warning_drawdown_pct": self.config.stress_warning_drawdown_pct,
            },
            "execution_summary": {
                "expected_total_cost": total_expected_cost,
                "expected_total_cost_bps": weighted_cost_bps,
                "largest_execution_cost": max(
                    (item["expected_execution_cost"] for item in execution_rows),
                    default=0.0,
                ),
            },
            "var_cvar": var_payload,
            "stress_tests": stress_payload,
            "limit_breaches": breaches,
            "positions": execution_rows,
        }
