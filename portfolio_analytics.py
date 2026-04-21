"""Advanced portfolio analytics: backtesting, benchmarks, and rebalance signals."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class BacktestConfig:
    transaction_cost_bps: float = 10.0
    rebalance_frequency: str = "monthly"
    risk_free_rate_annual: float = 0.02
    drift_threshold_pct: float = 5.0


class PortfolioAnalytics:
    def __init__(self, data_fetcher):
        self.data_fetcher = data_fetcher
        self.default_horizons = [1, 3, 5]
        self.default_config = BacktestConfig()

    def run_full_analysis(self, portfolio, horizons=None, config=None):
        """Run benchmark comparison, backtests, rebalance, correlation, sector, and Monte Carlo."""
        if config is None:
            config = self.default_config
        if horizons is None:
            horizons = self.default_horizons

        rebalance_payload = self.generate_rebalancing_recommendations(
            portfolio, drift_threshold_pct=config.drift_threshold_pct
        )

        period_payloads = {}
        backtest_rows = []
        aggregated_quality_warnings = []

        for years in horizons:
            label = f"{years}Y"
            period_result = self._analyze_period(portfolio, years, config)
            period_payloads[label] = period_result

            if period_result.get("status") == "ok":
                backtest_rows.append(
                    {
                        "period": label,
                        "start_date": period_result["start_date"],
                        "end_date": period_result["end_date"],
                        "portfolio_end_value": period_result["portfolio"]["end_value"],
                        "portfolio_total_return_pct": period_result["portfolio"]["total_return_pct"],
                        "portfolio_sharpe": period_result["portfolio"]["sharpe"],
                        "portfolio_max_drawdown_pct": period_result["portfolio"]["max_drawdown_pct"],
                        "transaction_cost_paid_pct": period_result["portfolio"]["transaction_cost_paid_pct"],
                        "turnover_pct": period_result["portfolio"]["turnover_pct"],
                        "rebalance_count": period_result["portfolio"]["rebalance_count"],
                    }
                )
            else:
                backtest_rows.append(
                    {
                        "period": label,
                        "status": period_result.get("status", "insufficient_data"),
                        "reason": period_result.get("reason", "Not enough history for backtest."),
                    }
                )

            warnings = period_result.get("quality_warnings", [])
            aggregated_quality_warnings.extend(warnings)

        default_period = "1Y" if "1Y" in period_payloads else next(iter(period_payloads.keys()), None)

        benchmark_comparison = {
            "default_period": default_period,
            "periods": {
                label: payload.get("comparison_table", {"rows": [], "status": payload.get("status")})
                for label, payload in period_payloads.items()
            },
        }

        backtest_payload = {
            "configuration": {
                "transaction_cost_bps": config.transaction_cost_bps,
                "rebalance_frequency": config.rebalance_frequency,
                "risk_free_rate_annual": config.risk_free_rate_annual,
            },
            "periods": backtest_rows,
        }

        correlation_payload = self.compute_correlation_matrix(portfolio)
        sector_payload = self.compute_sector_exposure(portfolio)
        monte_carlo_payload = self.run_monte_carlo(portfolio)
        tweak_workbench_payload = self.compute_tweak_workbench(
            portfolio, risk_free_rate_annual=config.risk_free_rate_annual
        )

        return {
            "configuration": {
                "horizons": [f"{years}Y" for years in horizons],
                "transaction_cost_bps": config.transaction_cost_bps,
                "rebalance_frequency": config.rebalance_frequency,
                "drift_threshold_pct": config.drift_threshold_pct,
            },
            "benchmark_comparison": benchmark_comparison,
            "backtests": backtest_payload,
            "rebalancing_recommendations": rebalance_payload,
            "correlation_matrix": correlation_payload,
            "sector_exposure": sector_payload,
            "monte_carlo": monte_carlo_payload,
            "tweak_workbench": tweak_workbench_payload,
            "quality_warnings": sorted(set(aggregated_quality_warnings)),
        }

    def _analyze_period(self, portfolio, years, config):
        allocations = portfolio.get("allocations", [])
        if not allocations:
            return {"status": "insufficient_data", "reason": "No allocations available."}

        end_date = date.today()
        # Extra buffer helps with non-trading days and sparse symbols.
        start_date = end_date - timedelta(days=years * 366 + 45)

        holding_tickers = [allocation["ticker"] for allocation in allocations]
        benchmark_tickers = ["SPY", "AGG"]
        price_tickers = sorted(set(holding_tickers + benchmark_tickers))

        price_frame, quality_map = self.data_fetcher.get_price_history_frame(
            price_tickers, start_date, end_date
        )
        if price_frame.empty:
            return {
                "status": "insufficient_data",
                "reason": "No historical data returned by providers.",
                "quality_warnings": ["Historical price matrix is empty."],
            }

        quality_warnings = []
        for ticker, metadata in quality_map.items():
            if metadata.get("source") == "unavailable":
                quality_warnings.append(f"{ticker}: no historical source available.")
            elif metadata.get("source") == "stooq_csv":
                quality_warnings.append(f"{ticker}: fallback source used (Stooq).")

        weights = {}
        for allocation in allocations:
            ticker = allocation["ticker"]
            if ticker in price_frame.columns and price_frame[ticker].dropna().shape[0] >= 40:
                weights[ticker] = float(allocation.get("weight", 0.0))

        if not weights:
            return {
                "status": "insufficient_data",
                "reason": "No holdings have enough history for the selected horizon.",
                "quality_warnings": quality_warnings,
            }

        total_weight = sum(weights.values())
        if total_weight <= 0:
            return {
                "status": "insufficient_data",
                "reason": "Invalid target weights after filtering.",
                "quality_warnings": quality_warnings,
            }
        weights = {ticker: weight / total_weight for ticker, weight in weights.items()}

        portfolio_prices = self._prepare_price_slice(price_frame, list(weights.keys()))
        if portfolio_prices.empty or portfolio_prices.shape[0] < 40:
            return {
                "status": "insufficient_data",
                "reason": "Insufficient aligned portfolio history.",
                "quality_warnings": quality_warnings,
            }

        cash_ratio = self._cash_ratio(portfolio)
        portfolio_values, portfolio_meta = self._simulate_rebalanced_portfolio(
            prices=portfolio_prices,
            target_weights=weights,
            transaction_cost_rate=config.transaction_cost_bps / 10000.0,
            rebalance_frequency=config.rebalance_frequency,
            cash_ratio=cash_ratio,
        )
        portfolio_metrics = self._performance_metrics(
            portfolio_values, risk_free_rate_annual=config.risk_free_rate_annual
        )

        # Benchmark 1: SPY (S&P 500 proxy)
        spy_prices = self._prepare_price_slice(price_frame, ["SPY"])
        spy_metrics = None
        spy_returns = pd.Series(dtype="float64")
        if not spy_prices.empty and spy_prices.shape[0] >= 40:
            spy_values, _ = self._simulate_rebalanced_portfolio(
                prices=spy_prices,
                target_weights={"SPY": 1.0},
                transaction_cost_rate=0.0,
                rebalance_frequency="none",
                cash_ratio=0.0,
            )
            spy_metrics = self._performance_metrics(
                spy_values, risk_free_rate_annual=config.risk_free_rate_annual
            )
            spy_returns = spy_values.pct_change().dropna()
        else:
            quality_warnings.append("SPY benchmark unavailable for this horizon.")

        # Benchmark 2: 60/40 SPY + AGG
        sixty_weights = {"SPY": 0.6, "AGG": 0.4}
        sixty_prices = self._prepare_price_slice(price_frame, list(sixty_weights.keys()))
        sixty_metrics = None
        sixty_returns = pd.Series(dtype="float64")
        if not sixty_prices.empty and sixty_prices.shape[0] >= 40:
            sixty_values, _ = self._simulate_rebalanced_portfolio(
                prices=sixty_prices,
                target_weights=sixty_weights,
                transaction_cost_rate=0.0,
                rebalance_frequency="monthly",
                cash_ratio=0.0,
            )
            sixty_metrics = self._performance_metrics(
                sixty_values, risk_free_rate_annual=config.risk_free_rate_annual
            )
            sixty_returns = sixty_values.pct_change().dropna()
        else:
            quality_warnings.append("60/40 benchmark unavailable for this horizon.")

        portfolio_returns = portfolio_values.pct_change().dropna()
        if not spy_returns.empty:
            portfolio_alpha_beta = self._alpha_beta(
                strategy_returns=portfolio_returns,
                market_returns=spy_returns,
                risk_free_rate_annual=config.risk_free_rate_annual,
            )
            portfolio_metrics.update(portfolio_alpha_beta)
            if spy_metrics is not None:
                spy_metrics.update({"alpha_pct": 0.0, "beta": 1.0})
            if sixty_metrics is not None and not sixty_returns.empty:
                sixty_alpha_beta = self._alpha_beta(
                    strategy_returns=sixty_returns,
                    market_returns=spy_returns,
                    risk_free_rate_annual=config.risk_free_rate_annual,
                )
                sixty_metrics.update(sixty_alpha_beta)
        else:
            portfolio_metrics.update({"alpha_pct": None, "beta": None})
            if sixty_metrics is not None:
                sixty_metrics.update({"alpha_pct": None, "beta": None})

        comparison_rows = [
            self._comparison_row("Portfolio", portfolio_metrics, available=True),
            self._comparison_row("S&P 500 (SPY)", spy_metrics, available=spy_metrics is not None),
            self._comparison_row("60/40 (SPY/AGG)", sixty_metrics, available=sixty_metrics is not None),
        ]

        return {
            "status": "ok",
            "start_date": portfolio_prices.index.min().strftime("%Y-%m-%d"),
            "end_date": portfolio_prices.index.max().strftime("%Y-%m-%d"),
            "portfolio": {
                **portfolio_metrics,
                "end_value": float(portfolio_values.iloc[-1]),
                "transaction_cost_paid_pct": portfolio_meta["transaction_cost_paid_pct"],
                "turnover_pct": portfolio_meta["turnover_pct"],
                "rebalance_count": portfolio_meta["rebalance_count"],
            },
            "benchmarks": {
                "sp500": spy_metrics,
                "sixty_forty": sixty_metrics,
            },
            "comparison_table": {
                "status": "ok",
                "rows": comparison_rows,
            },
            "quality_warnings": quality_warnings,
        }

    @staticmethod
    def _cash_ratio(portfolio):
        total_value = float(portfolio.get("total_value", 0.0))
        cash_remainder = float(portfolio.get("cash_remainder", 0.0))
        if total_value <= 0:
            return 0.0
        return max(0.0, min(0.5, cash_remainder / total_value))

    @staticmethod
    def _prepare_price_slice(price_frame, tickers):
        if not tickers:
            return pd.DataFrame()
        available = [ticker for ticker in tickers if ticker in price_frame.columns]
        if not available:
            return pd.DataFrame()
        frame = price_frame[available].copy().sort_index()
        frame = frame.ffill().dropna(how="any")
        return frame

    @staticmethod
    def _should_rebalance(prev_date, current_date, frequency):
        if frequency == "none":
            return False
        if frequency == "daily":
            return True
        if frequency == "weekly":
            return prev_date.isocalendar()[1] != current_date.isocalendar()[1] or prev_date.year != current_date.year
        if frequency == "monthly":
            return prev_date.month != current_date.month or prev_date.year != current_date.year
        if frequency == "quarterly":
            prev_quarter = (prev_date.month - 1) // 3
            current_quarter = (current_date.month - 1) // 3
            return prev_quarter != current_quarter or prev_date.year != current_date.year
        if frequency == "yearly":
            return prev_date.year != current_date.year
        return False

    def _simulate_rebalanced_portfolio(
        self,
        prices,
        target_weights,
        transaction_cost_rate,
        rebalance_frequency,
        cash_ratio=0.0,
    ):
        if prices.empty:
            return pd.Series(dtype="float64"), {
                "transaction_cost_paid_pct": 0.0,
                "turnover_pct": 0.0,
                "rebalance_count": 0,
            }

        tickers = list(target_weights.keys())
        prices = prices[tickers].copy()
        prices = prices.ffill().dropna()
        if prices.empty:
            return pd.Series(dtype="float64"), {
                "transaction_cost_paid_pct": 0.0,
                "turnover_pct": 0.0,
                "rebalance_count": 0,
            }

        weights = np.array([target_weights[ticker] for ticker in tickers], dtype=float)
        weight_sum = weights.sum()
        if weight_sum <= 0:
            weights = np.ones_like(weights) / len(weights)
        else:
            weights = weights / weight_sum

        returns = prices.pct_change().fillna(0.0)
        invested_initial = 1.0 - cash_ratio
        initial_cost = invested_initial * transaction_cost_rate
        invested_after_cost = max(0.0, invested_initial - initial_cost)
        holding_values = invested_after_cost * weights
        cash_value = cash_ratio

        total_values = [holding_values.sum() + cash_value]
        turnover_value = invested_initial
        transaction_cost_value = initial_cost
        rebalance_count = 0

        for idx in range(1, len(returns.index)):
            day_returns = returns.iloc[idx].to_numpy(dtype=float)
            holding_values = holding_values * (1.0 + day_returns)
            invested_value = float(holding_values.sum())

            previous_date = returns.index[idx - 1]
            current_date = returns.index[idx]

            if self._should_rebalance(previous_date, current_date, rebalance_frequency):
                current_weights = (
                    holding_values / invested_value if invested_value > 0 else weights
                )
                # Turnover is half of the L1 distance between weight vectors.
                trade_value = float(0.5 * np.abs(weights - current_weights).sum() * invested_value)
                trade_cost = trade_value * transaction_cost_rate

                if trade_value > 0:
                    invested_value = max(0.0, invested_value - trade_cost)
                    holding_values = invested_value * weights
                    transaction_cost_value += trade_cost
                    turnover_value += trade_value
                    rebalance_count += 1

            total_values.append(float(holding_values.sum() + cash_value))

        value_series = pd.Series(total_values, index=prices.index, dtype=float)
        meta = {
            "transaction_cost_paid_pct": transaction_cost_value * 100.0,
            "turnover_pct": turnover_value * 100.0,
            "rebalance_count": rebalance_count,
        }
        return value_series, meta

    @staticmethod
    def _max_drawdown(value_series):
        if value_series.empty:
            return 0.0
        running_max = value_series.cummax()
        drawdowns = value_series / running_max - 1.0
        return float(drawdowns.min())

    def _performance_metrics(self, value_series, risk_free_rate_annual):
        if value_series.empty or value_series.shape[0] < 2:
            return {
                "total_return_pct": 0.0,
                "annual_return_pct": 0.0,
                "annual_volatility_pct": 0.0,
                "sharpe": 0.0,
                "max_drawdown_pct": 0.0,
            }

        start_value = float(value_series.iloc[0])
        end_value = float(value_series.iloc[-1])
        total_return = (end_value / start_value - 1.0) if start_value > 0 else 0.0

        daily_returns = value_series.pct_change().dropna()
        n_days = max(1, daily_returns.shape[0])
        annual_factor = 252.0 / n_days
        annual_return = (end_value / start_value) ** annual_factor - 1.0 if start_value > 0 else 0.0
        annual_vol = float(daily_returns.std() * np.sqrt(252.0)) if not daily_returns.empty else 0.0

        sharpe = 0.0
        if annual_vol > 0:
            sharpe = (annual_return - risk_free_rate_annual) / annual_vol

        max_drawdown = self._max_drawdown(value_series)

        return {
            "total_return_pct": total_return * 100.0,
            "annual_return_pct": annual_return * 100.0,
            "annual_volatility_pct": annual_vol * 100.0,
            "sharpe": float(sharpe),
            "max_drawdown_pct": max_drawdown * 100.0,
        }

    @staticmethod
    def _alpha_beta(strategy_returns, market_returns, risk_free_rate_annual):
        aligned = pd.concat([strategy_returns, market_returns], axis=1, join="inner").dropna()
        if aligned.empty or aligned.shape[0] < 5:
            return {"alpha_pct": 0.0, "beta": 0.0}

        aligned.columns = ["strategy", "market"]
        rf_daily = (1.0 + risk_free_rate_annual) ** (1.0 / 252.0) - 1.0

        strategy_excess = aligned["strategy"] - rf_daily
        market_excess = aligned["market"] - rf_daily
        market_var = float(market_excess.var())

        if market_var <= 0:
            return {"alpha_pct": 0.0, "beta": 0.0}

        beta = float(strategy_excess.cov(market_excess) / market_var)
        alpha_daily = float(strategy_excess.mean() - beta * market_excess.mean())
        alpha_annual = alpha_daily * 252.0

        return {"alpha_pct": alpha_annual * 100.0, "beta": beta}

    @staticmethod
    def _comparison_row(label, metrics, available=True):
        if not available or metrics is None:
            return {
                "label": label,
                "available": False,
                "annual_return_pct": None,
                "annual_volatility_pct": None,
                "sharpe": None,
                "max_drawdown_pct": None,
                "alpha_pct": None,
                "beta": None,
            }
        return {
            "label": label,
            "available": True,
            "annual_return_pct": metrics.get("annual_return_pct", 0.0),
            "annual_volatility_pct": metrics.get("annual_volatility_pct", 0.0),
            "sharpe": metrics.get("sharpe", 0.0),
            "max_drawdown_pct": metrics.get("max_drawdown_pct", 0.0),
            "alpha_pct": metrics.get("alpha_pct", 0.0),
            "beta": metrics.get("beta", 0.0),
        }

    def generate_rebalancing_recommendations(self, portfolio, drift_threshold_pct=5.0):
        """Generate trade recommendations when holdings drift from target weights."""
        allocations = portfolio.get("allocations", [])
        if not allocations:
            return {
                "needs_rebalance": False,
                "drift_threshold_pct": drift_threshold_pct,
                "summary": "No holdings available for drift analysis.",
                "recommendations": [],
            }

        invested_value = float(
            sum(allocation.get("current_value", allocation.get("cost", 0.0)) for allocation in allocations)
        )
        if invested_value <= 0:
            return {
                "needs_rebalance": False,
                "drift_threshold_pct": drift_threshold_pct,
                "summary": "Current market value is unavailable, skipping drift analysis.",
                "recommendations": [],
            }

        recommendations = []
        max_drift = 0.0

        for allocation in allocations:
            ticker = allocation["ticker"]
            target_weight = float(allocation.get("weight", 0.0))
            current_value = float(allocation.get("current_value", allocation.get("cost", 0.0)))
            current_weight = current_value / invested_value if invested_value > 0 else 0.0
            drift_pct = (current_weight - target_weight) * 100.0
            abs_drift = abs(drift_pct)
            max_drift = max(max_drift, abs_drift)

            if abs_drift < drift_threshold_pct:
                continue

            target_value = target_weight * invested_value
            trade_value = target_value - current_value
            if trade_value > 0:
                action = "BUY"
            elif trade_value < 0:
                action = "SELL"
            else:
                action = "HOLD"

            price = float(allocation.get("current_price", allocation.get("price", 0.0)))
            shares_delta = (trade_value / price) if price > 0 else 0.0

            recommendations.append(
                {
                    "ticker": ticker,
                    "action": action,
                    "drift_pct": drift_pct,
                    "current_weight_pct": current_weight * 100.0,
                    "target_weight_pct": target_weight * 100.0,
                    "trade_value": trade_value,
                    "shares_delta": shares_delta,
                }
            )

        recommendations.sort(key=lambda item: abs(item["drift_pct"]), reverse=True)
        needs_rebalance = len(recommendations) > 0

        if needs_rebalance:
            summary = (
                f"{len(recommendations)} holdings exceed drift threshold "
                f"({drift_threshold_pct:.1f}%). Maximum drift is {max_drift:.2f}%."
            )
        else:
            summary = (
                f"All holdings are within the {drift_threshold_pct:.1f}% drift threshold. "
                "No rebalance needed now."
            )

        return {
            "needs_rebalance": needs_rebalance,
            "drift_threshold_pct": drift_threshold_pct,
            "max_drift_pct": max_drift,
            "summary": summary,
            "recommendations": recommendations,
        }

    # ------------------------------------------------------------------
    # Correlation matrix
    # ------------------------------------------------------------------

    def compute_correlation_matrix(self, portfolio: dict) -> dict[str, Any]:
        """Compute pairwise return correlation matrix for portfolio holdings."""
        allocations = portfolio.get("allocations", [])
        if len(allocations) < 2:
            return {"status": "insufficient_holdings", "tickers": [], "matrix": []}

        tickers = [a["ticker"] for a in allocations if a.get("ticker")]
        end_date = date.today()
        start_date = end_date - timedelta(days=400)
        frame, _ = self.data_fetcher.get_price_history_frame(tickers, start_date, end_date)
        if frame.empty:
            return {"status": "insufficient_data", "tickers": tickers, "matrix": []}

        available = [t for t in tickers if t in frame.columns and frame[t].dropna().shape[0] >= 30]
        if len(available) < 2:
            return {"status": "insufficient_data", "tickers": available, "matrix": []}

        returns = frame[available].pct_change().dropna()
        if returns.shape[0] < 20:
            return {"status": "insufficient_data", "tickers": available, "matrix": []}

        corr = returns.corr()
        matrix_rows = []
        for ticker in available:
            row = []
            for other in available:
                val = corr.loc[ticker, other]
                row.append(round(float(val), 4) if np.isfinite(val) else 0.0)
            matrix_rows.append(row)

        return {"status": "ok", "tickers": available, "matrix": matrix_rows}

    # ------------------------------------------------------------------
    # Sector exposure
    # ------------------------------------------------------------------

    @staticmethod
    def compute_sector_exposure(portfolio: dict) -> dict[str, Any]:
        """Aggregate portfolio weight by GICS sector."""
        allocations = portfolio.get("allocations", [])
        if not allocations:
            return {"sectors": [], "weights": []}

        sector_weight: dict[str, float] = {}
        for allocation in allocations:
            sector = allocation.get("sector", "Other")
            weight = float(allocation.get("weight", 0.0))
            sector_weight[sector] = sector_weight.get(sector, 0.0) + weight

        total = sum(sector_weight.values()) or 1.0
        sorted_sectors = sorted(sector_weight.items(), key=lambda x: -x[1])

        return {
            "sectors": [s for s, _ in sorted_sectors],
            "weights": [round((w / total) * 100.0, 2) for _, w in sorted_sectors],
        }

    # ------------------------------------------------------------------
    # Tweak workbench: per-ticker mu/sigma + correlation for live what-if
    # ------------------------------------------------------------------

    def compute_tweak_workbench(
        self, portfolio: dict, risk_free_rate_annual: float = 0.02
    ) -> dict[str, Any]:
        """Per-ticker annualized mu/sigma plus correlation matrix for client-side weight tweaks."""
        allocations = portfolio.get("allocations", [])
        if len(allocations) < 2:
            return {"status": "insufficient_holdings"}

        tickers = [a["ticker"] for a in allocations if a.get("ticker")]
        end_date = date.today()
        start_date = end_date - timedelta(days=500)
        frame, _ = self.data_fetcher.get_price_history_frame(tickers, start_date, end_date)
        if frame.empty:
            return {"status": "insufficient_data"}

        available = [t for t in tickers if t in frame.columns and frame[t].dropna().shape[0] >= 30]
        if len(available) < 2:
            return {"status": "insufficient_data"}

        aligned = frame[available].ffill().dropna()
        if aligned.shape[0] < 30:
            return {"status": "insufficient_data"}

        returns = aligned.pct_change().dropna()
        daily_mu = returns.mean()
        daily_sigma = returns.std()
        annual_mu = (1.0 + daily_mu) ** 252.0 - 1.0
        annual_sigma = daily_sigma * np.sqrt(252.0)
        corr = returns.corr()

        weight_map = {a["ticker"]: float(a.get("weight", 0.0)) for a in allocations}
        names_map = {a["ticker"]: a.get("name", a["ticker"]) for a in allocations}

        matrix_rows: list[list[float]] = []
        for ti in available:
            row = []
            for tj in available:
                v = corr.loc[ti, tj]
                row.append(round(float(v), 6) if np.isfinite(v) else 0.0)
            matrix_rows.append(row)

        return {
            "status": "ok",
            "tickers": available,
            "names": [names_map.get(t, t) for t in available],
            "mu_annual_pct": [round(float(annual_mu[t]) * 100.0, 4) for t in available],
            "sigma_annual_pct": [round(float(annual_sigma[t]) * 100.0, 4) for t in available],
            "correlation_matrix": matrix_rows,
            "risk_free_rate_annual_pct": round(risk_free_rate_annual * 100.0, 4),
            "initial_weights": [round(weight_map.get(t, 0.0), 6) for t in available],
            "history_days": int(aligned.shape[0]),
        }

    # ------------------------------------------------------------------
    # Monte Carlo simulation
    # ------------------------------------------------------------------

    def run_monte_carlo(
        self,
        portfolio: dict,
        simulations: int = 1000,
        forecast_days: int = 252,
    ) -> dict[str, Any]:
        """Run Monte Carlo simulation returning percentile fan-chart bands."""
        allocations = portfolio.get("allocations", [])
        if not allocations:
            return {"status": "insufficient_data"}

        tickers = [a["ticker"] for a in allocations if a.get("ticker")]
        end_date = date.today()
        start_date = end_date - timedelta(days=500)
        frame, _ = self.data_fetcher.get_price_history_frame(tickers, start_date, end_date)
        if frame.empty:
            return {"status": "insufficient_data"}

        weights: dict[str, float] = {}
        for allocation in allocations:
            t = allocation["ticker"]
            if t in frame.columns and frame[t].dropna().shape[0] >= 30:
                weights[t] = float(allocation.get("weight", 0.0))

        if not weights:
            return {"status": "insufficient_data"}

        total_w = sum(weights.values()) or 1.0
        weights = {t: w / total_w for t, w in weights.items()}

        aligned = frame[list(weights.keys())].ffill().dropna()
        if aligned.shape[0] < 30:
            return {"status": "insufficient_data"}

        returns = aligned.pct_change().dropna()
        port_returns = sum(returns[t] * w for t, w in weights.items())
        mu = float(port_returns.mean())
        sigma = float(port_returns.std())

        if sigma <= 0:
            return {"status": "insufficient_data"}

        current_value = float(portfolio.get("total_value", 0.0) or 0.0)
        if current_value <= 0:
            current_value = float(
                sum(a.get("current_value", a.get("cost", 0.0)) for a in allocations)
            )
        if current_value <= 0:
            return {"status": "insufficient_data"}

        rng = np.random.default_rng(seed=42)
        terminal_values = np.zeros(simulations)
        # Store path percentiles at monthly intervals for the fan chart.
        sample_days = list(range(0, forecast_days + 1, max(1, forecast_days // 12)))
        if sample_days[-1] != forecast_days:
            sample_days.append(forecast_days)
        path_matrix = np.zeros((simulations, len(sample_days)))

        for sim_idx in range(simulations):
            daily_shocks = rng.normal(mu, sigma, forecast_days)
            cumulative = np.cumprod(1.0 + daily_shocks)
            path_matrix[sim_idx, 0] = current_value
            for col_idx, day in enumerate(sample_days[1:], start=1):
                path_matrix[sim_idx, col_idx] = current_value * cumulative[day - 1]
            terminal_values[sim_idx] = current_value * cumulative[-1]

        percentiles = [5, 25, 50, 75, 95]
        bands: dict[str, list[float]] = {}
        for pct in percentiles:
            band = np.percentile(path_matrix, pct, axis=0)
            bands[f"p{pct}"] = [round(float(v), 2) for v in band]

        terminal_stats = {
            f"p{pct}": round(float(np.percentile(terminal_values, pct)), 2)
            for pct in percentiles
        }

        return {
            "status": "ok",
            "simulations": simulations,
            "forecast_days": forecast_days,
            "current_value": round(current_value, 2),
            "sample_days": sample_days,
            "bands": bands,
            "terminal_distribution": terminal_stats,
            "expected_return_daily_pct": round(mu * 100, 6),
            "volatility_daily_pct": round(sigma * 100, 6),
        }
