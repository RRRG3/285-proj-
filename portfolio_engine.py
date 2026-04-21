"""Core portfolio allocation and valuation logic."""

import concurrent.futures

from data_fetcher import StockDataFetcher


class PortfolioEngine:
    def __init__(self):
        self.data_fetcher = StockDataFetcher()
        self.min_investment = 5000.0
        self.min_per_stock = 100.0
        self.default_annualized_volatility = 0.30
        self.volatility_floor = 0.08

    def validate_investment(self, amount):
        """Validate that amount meets minimum project requirement."""
        if amount < self.min_investment:
            return False, f"Minimum investment is ${self.min_investment:,.2f}"
        return True, None

    def _build_weight_model(self, stocks):
        tickers = [stock["ticker"] for stock in stocks]
        prices = self.data_fetcher.get_multiple_prices(tickers)

        volatility_map = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(10, len(tickers) or 1)) as executor:
            future_to_ticker = {executor.submit(self.data_fetcher.get_annualized_volatility, t): t for t in tickers}
            for future in concurrent.futures.as_completed(future_to_ticker):
                ticker = future_to_ticker[future]
                try:
                    volatility_map[ticker] = future.result()
                except Exception:
                    volatility_map[ticker] = None

        assets = []
        for stock in stocks:
            ticker = stock["ticker"]
            price = prices.get(ticker)
            if price is None:
                continue

            conviction = float(stock.get("conviction", 0.75))
            raw_volatility = volatility_map.get(ticker)
            annualized_volatility = raw_volatility or self.default_annualized_volatility
            adjusted_volatility = max(annualized_volatility, self.volatility_floor)
            raw_score = conviction / adjusted_volatility

            assets.append(
                {
                    **stock,
                    "price": price,
                    "conviction": conviction,
                    "annualized_volatility": annualized_volatility,
                    "raw_score": raw_score,
                }
            )

        return assets

    @staticmethod
    def derive_risk_score(risk_profile):
        """Map a 3-question risk profile to a 0-100 aggressiveness score.

        Higher = more risk-seeking. Aggressive = boost high-conviction names and use less cash buffer;
        Conservative = compress weight dispersion and reserve more cash.
        """
        if not risk_profile:
            return 60.0  # neutral default
        age = float(risk_profile.get("age", 35))
        horizon = float(risk_profile.get("horizon_years", 10))
        tolerance = float(risk_profile.get("max_drawdown_tolerance_pct", 25))
        # Each dimension contributes ~0-100; we average.
        # Younger -> higher score. 18 yrs ≈ 100, 80 yrs ≈ 0.
        age_component = max(0.0, min(100.0, (80 - age) / (80 - 18) * 100.0))
        # Longer horizon -> higher score (cap at 30 years).
        horizon_component = max(0.0, min(100.0, horizon / 30.0 * 100.0))
        # Tolerance for drawdown -> direct mapping (capped).
        tolerance_component = max(0.0, min(100.0, (tolerance - 5) / 55 * 100.0))
        return float(age_component * 0.35 + horizon_component * 0.30 + tolerance_component * 0.35)

    def _profile_label(self, risk_score):
        if risk_score >= 75:
            return "Aggressive"
        if risk_score >= 55:
            return "Growth"
        if risk_score >= 35:
            return "Balanced"
        return "Conservative"

    def calculate_allocation(self, amount, stocks, risk_profile=None):
        """
        Allocate capital using conviction-weighted inverse volatility sizing,
        optionally tilted by the user's risk profile.

        Portfolio weight formula:
            weight_i ∝ conviction_i / max(volatility_i, volatility_floor)
        """
        if not stocks:
            return None

        modeled_assets = self._build_weight_model(stocks)
        if not modeled_assets:
            return None

        # ---- Risk-profile tilt ---------------------------------------
        risk_score = self.derive_risk_score(risk_profile) if risk_profile else None
        cash_reserve_pct = 0.0
        if risk_score is not None:
            # Higher risk-tolerance -> lower cash reserve (0% at score 100, ~12% at score 0).
            cash_reserve_pct = max(0.0, min(0.12, (100.0 - risk_score) / 100.0 * 0.12))
            # Aggressive profiles steepen the conviction/vol dispersion (^1.6).
            # Conservative profiles flatten it (^0.6) — closer to equal-weight for stability.
            exponent = 0.6 + (risk_score / 100.0) * 1.0  # 0.6 at score 0, 1.6 at score 100
            for asset in modeled_assets:
                asset["raw_score"] = asset["raw_score"] ** exponent

        investable_amount = amount * (1.0 - cash_reserve_pct)
        # ---------------------------------------------------------------

        # Remove micro-positions iteratively unless it would drop below 3 holdings.
        while True:
            score_sum = sum(asset["raw_score"] for asset in modeled_assets)
            if score_sum <= 0:
                return None

            for asset in modeled_assets:
                asset["weight"] = asset["raw_score"] / score_sum

            smallest_target = min(investable_amount * asset["weight"] for asset in modeled_assets)
            if smallest_target >= self.min_per_stock or len(modeled_assets) <= 3:
                break

            modeled_assets.sort(key=lambda item: item["weight"])
            modeled_assets.pop(0)

        allocations = []
        total_allocated = 0.0

        for asset in modeled_assets:
            target_cost = investable_amount * asset["weight"]
            shares = target_cost / asset["price"]
            actual_cost = shares * asset["price"]
            total_allocated += actual_cost

            allocations.append(
                {
                    "ticker": asset["ticker"],
                    "name": asset["name"],
                    "strategy": asset.get("strategy"),
                    "asset_type": asset.get("asset_type", "Stock"),
                    "sector": asset.get("sector", "Other"),
                    "rationale": asset.get("rationale", ""),
                    "conviction": asset["conviction"],
                    "annualized_volatility": asset["annualized_volatility"],
                    "weight": asset["weight"],
                    "weight_pct": asset["weight"] * 100,
                    "shares": shares,
                    "price": asset["price"],
                    "cost": actual_cost,
                }
            )

        cash_remainder = max(amount - total_allocated, 0.0)

        result = {
            "allocations": allocations,
            "total_allocated": total_allocated,
            "cash_remainder": cash_remainder,
            "total_value": total_allocated + cash_remainder,
            "allocation_method": "Conviction-weighted inverse-volatility model",
        }
        if risk_score is not None:
            result["risk_profile"] = {
                **risk_profile,
                "risk_score": round(risk_score, 1),
                "label": self._profile_label(risk_score),
                "cash_reserve_pct": round(cash_reserve_pct * 100.0, 2),
            }
            result["allocation_method"] = (
                f"Conviction-weighted inverse-volatility · {self._profile_label(risk_score)} tilt"
            )
        return result

    def _compute_analytics(self, portfolio):
        allocations = portfolio.get("allocations", [])
        if not allocations:
            return {}

        initial_invested = sum(allocation.get("cost", 0.0) for allocation in allocations)
        current_market_value = sum(allocation.get("current_value", 0.0) for allocation in allocations)
        cash = portfolio.get("cash_remainder", 0.0)
        total_value = current_market_value + cash

        unrealized_pnl = total_value - (initial_invested + cash)
        baseline = initial_invested + cash
        unrealized_return_pct = (unrealized_pnl / baseline * 100) if baseline > 0 else 0.0

        position_weights = []
        if current_market_value > 0:
            position_weights = [
                allocation.get("current_value", 0.0) / current_market_value
                for allocation in allocations
            ]

        hhi = sum(weight * weight for weight in position_weights) if position_weights else 1.0
        effective_holdings = (1.0 / hhi) if hhi > 0 else 0.0
        diversification_score = (
            min(100.0, (effective_holdings / len(position_weights)) * 100.0)
            if position_weights
            else 0.0
        )

        largest_position = max(
            allocations,
            key=lambda item: item.get("current_value", item.get("cost", 0.0)),
        )
        largest_position_value = largest_position.get("current_value", largest_position.get("cost", 0.0))
        largest_position_weight = (
            largest_position_value / current_market_value * 100.0
            if current_market_value > 0
            else 0.0
        )

        return {
            "invested_capital": initial_invested,
            "cash_remainder": cash,
            "current_market_value": current_market_value,
            "total_portfolio_value": total_value,
            "unrealized_pnl": unrealized_pnl,
            "unrealized_return_pct": unrealized_return_pct,
            "effective_holdings": effective_holdings,
            "diversification_score": diversification_score,
            "largest_position_ticker": largest_position.get("ticker"),
            "largest_position_weight_pct": largest_position_weight,
        }

    def calculate_portfolio_value(self, portfolio):
        """Refresh each holding with latest price and recompute portfolio metrics."""
        if not portfolio or "allocations" not in portfolio:
            return portfolio

        total_market_value = 0.0
        collected_quotes = []

        # Pre-fetch all quotes in parallel
        tickers = [alloc["ticker"] for alloc in portfolio["allocations"]]
        bulk_quotes = self.data_fetcher.get_multiple_quotes(tickers)

        for allocation in portfolio["allocations"]:
            ticker = allocation["ticker"]
            shares = allocation["shares"]

            quote = bulk_quotes.get(ticker)
            if quote and quote.get("price") is not None:
                current_price = quote["price"]
                allocation["quote_source"] = quote.get("source")
                allocation["quote_timestamp"] = quote.get("timestamp")
                allocation["quote_age_seconds"] = quote.get("age_seconds")
                allocation["quote_is_stale"] = quote.get("is_stale", False)
                allocation["market_status"] = quote.get("market_status")
                allocation["quote_reliability_score"] = quote.get("reliability_score", 0.0)
                collected_quotes.append(quote)
            else:
                current_price = allocation["price"]
                allocation["quote_source"] = "allocation_fallback"
                allocation["quote_is_stale"] = True
                allocation["market_status"] = self.data_fetcher.get_market_clock().get("market_status")
                allocation["quote_reliability_score"] = 0.4
                collected_quotes.append(
                    {
                        "ticker": ticker,
                        "price": current_price,
                        "timestamp": None,
                        "age_seconds": None,
                        "source": "allocation_fallback",
                        "market_status": allocation["market_status"],
                        "is_stale": True,
                        "quality_flags": ["FALLBACK_SOURCE", "STALE_QUOTE"],
                        "reliability_score": 0.4,
                        "currency": "USD",
                    }
                )

            current_value = shares * current_price
            allocation["current_price"] = current_price
            allocation["current_value"] = current_value
            cost_basis = float(allocation.get("cost", 0.0) or 0.0)
            position_pnl = current_value - cost_basis
            allocation["position_pnl"] = position_pnl
            allocation["position_return_pct"] = (
                (position_pnl / cost_basis) * 100.0 if cost_basis > 0 else 0.0
            )
            total_market_value += current_value

        # Performance attribution: % of total portfolio PnL contributed per holding.
        total_cost = float(sum(a.get("cost", 0.0) for a in portfolio["allocations"]))
        total_pnl = total_market_value - total_cost
        for allocation in portfolio["allocations"]:
            position_pnl = float(allocation.get("position_pnl", 0.0) or 0.0)
            allocation["contribution_pct"] = (
                (position_pnl / total_cost) * 100.0 if total_cost > 0 else 0.0
            )
            allocation["contribution_share_pct"] = (
                (position_pnl / total_pnl) * 100.0 if abs(total_pnl) > 1e-6 else 0.0
            )

        portfolio["total_value"] = total_market_value + portfolio.get("cash_remainder", 0.0)
        portfolio["metrics"] = self._compute_analytics(portfolio)
        portfolio["data_quality"] = self.data_fetcher.summarize_quote_quality(collected_quotes)
        return portfolio

    def generate_portfolio(self, amount, selected_strategies, stocks, risk_profile=None):
        """Generate a complete portfolio response payload."""
        is_valid, error = self.validate_investment(amount)
        if not is_valid:
            return {"error": error}

        portfolio = self.calculate_allocation(amount, stocks, risk_profile=risk_profile)
        if portfolio is None:
            return {"error": "No stocks available for allocation"}

        portfolio["investment_amount"] = amount
        portfolio["strategies"] = selected_strategies
        portfolio["num_stocks"] = len(portfolio["allocations"])
        return portfolio
