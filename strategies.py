"""Investment strategy to stock/ETF mappings with research-friendly metadata."""

from __future__ import annotations

import sys

from typing import TypedDict, cast

if sys.version_info >= (3, 11):
    from typing import NotRequired
else:
    from typing_extensions import NotRequired


class StrategyStock(TypedDict):
    ticker: str
    name: str
    rationale: str
    conviction: float
    asset_type: str
    sector: str
    strategy: NotRequired[str]


class StrategyDefinition(TypedDict):
    description: str
    stocks: list[StrategyStock]

STRATEGIES: dict[str, StrategyDefinition] = {
    "Ethical Investing": {
        "description": "Companies with strong environmental, social, and governance (ESG) practices",
        "stocks": [
            {
                "ticker": "AAPL",
                "name": "Apple Inc.",
                "rationale": "Carbon neutral commitment and ethical supply chain programs",
                "conviction": 0.92,
                "asset_type": "Stock",
                "sector": "Technology",
            },
            {
                "ticker": "ADBE",
                "name": "Adobe Inc.",
                "rationale": "Consistent ESG reporting and workforce diversity outcomes",
                "conviction": 0.83,
                "asset_type": "Stock",
                "sector": "Technology",
            },
            {
                "ticker": "NSRGY",
                "name": "Nestle S.A.",
                "rationale": "Large-scale water stewardship and sustainable sourcing roadmap",
                "conviction": 0.76,
                "asset_type": "Stock",
                "sector": "Consumer Staples",
            },
            {
                "ticker": "MSFT",
                "name": "Microsoft Corporation",
                "rationale": "Carbon negative target and transparent sustainability governance",
                "conviction": 0.89,
                "asset_type": "Stock",
                "sector": "Technology",
            },
        ],
    },
    "Growth Investing": {
        "description": "High-growth potential companies in innovation-led sectors",
        "stocks": [
            {
                "ticker": "TSLA",
                "name": "Tesla Inc.",
                "rationale": "Energy transition exposure with high long-term growth optionality",
                "conviction": 0.80,
                "asset_type": "Stock",
                "sector": "Consumer Discretionary",
            },
            {
                "ticker": "NVDA",
                "name": "NVIDIA Corporation",
                "rationale": "Leading position in accelerated compute and AI infrastructure",
                "conviction": 0.95,
                "asset_type": "Stock",
                "sector": "Technology",
            },
            {
                "ticker": "AMZN",
                "name": "Amazon.com Inc.",
                "rationale": "Scale advantages across commerce, cloud, and logistics",
                "conviction": 0.87,
                "asset_type": "Stock",
                "sector": "Consumer Discretionary",
            },
            {
                "ticker": "META",
                "name": "Meta Platforms Inc.",
                "rationale": "Operating leverage from digital ads and AI-assisted engagement",
                "conviction": 0.82,
                "asset_type": "Stock",
                "sector": "Communication Services",
            },
        ],
    },
    "Index Investing": {
        "description": "Diversified ETFs tracking broad market exposures",
        "stocks": [
            {
                "ticker": "VTI",
                "name": "Vanguard Total Stock Market ETF",
                "rationale": "Broad U.S. equity beta exposure at low cost",
                "conviction": 0.94,
                "asset_type": "ETF",
                "sector": "Broad Market",
            },
            {
                "ticker": "IXUS",
                "name": "iShares Core MSCI Total International Stock ETF",
                "rationale": "International equity diversification outside U.S. markets",
                "conviction": 0.86,
                "asset_type": "ETF",
                "sector": "International Equity",
            },
            {
                "ticker": "ILTB",
                "name": "iShares Core 10+ Year USD Bond ETF",
                "rationale": "Duration ballast for risk moderation and diversification",
                "conviction": 0.74,
                "asset_type": "ETF",
                "sector": "Fixed Income",
            },
            {
                "ticker": "SPY",
                "name": "SPDR S&P 500 ETF Trust",
                "rationale": "Highly liquid exposure to large-cap U.S. equity index",
                "conviction": 0.90,
                "asset_type": "ETF",
                "sector": "Broad Market",
            },
        ],
    },
    "Quality Investing": {
        "description": "Established firms with resilient cash flows and durable business models",
        "stocks": [
            {
                "ticker": "JNJ",
                "name": "Johnson & Johnson",
                "rationale": "Defensive healthcare mix with steady profitability profile",
                "conviction": 0.84,
                "asset_type": "Stock",
                "sector": "Healthcare",
            },
            {
                "ticker": "PG",
                "name": "Procter & Gamble Co.",
                "rationale": "Pricing power and stable demand in essential categories",
                "conviction": 0.81,
                "asset_type": "Stock",
                "sector": "Consumer Staples",
            },
            {
                "ticker": "KO",
                "name": "The Coca-Cola Company",
                "rationale": "Global brand moat and consistent free cash flow generation",
                "conviction": 0.79,
                "asset_type": "Stock",
                "sector": "Consumer Staples",
            },
            {
                "ticker": "V",
                "name": "Visa Inc.",
                "rationale": "Network-effect economics and structurally high margins",
                "conviction": 0.88,
                "asset_type": "Stock",
                "sector": "Financials",
            },
        ],
    },
    "Value Investing": {
        "description": "Companies with comparatively attractive valuation multiples",
        "stocks": [
            {
                "ticker": "BRK-B",
                "name": "Berkshire Hathaway Inc. Class B",
                "rationale": "Diversified earnings streams with disciplined capital allocation",
                "conviction": 0.93,
                "asset_type": "Stock",
                "sector": "Financials",
            },
            {
                "ticker": "BAC",
                "name": "Bank of America Corporation",
                "rationale": "Large deposit franchise and leverage to rates/credit cycles",
                "conviction": 0.77,
                "asset_type": "Stock",
                "sector": "Financials",
            },
            {
                "ticker": "CVX",
                "name": "Chevron Corporation",
                "rationale": "Integrated energy cash generation with shareholder payouts",
                "conviction": 0.80,
                "asset_type": "Stock",
                "sector": "Energy",
            },
            {
                "ticker": "VZ",
                "name": "Verizon Communications Inc.",
                "rationale": "Defensive cash flows and relatively high dividend yield profile",
                "conviction": 0.72,
                "asset_type": "Stock",
                "sector": "Communication Services",
            },
        ],
    },
}

def get_strategy_names() -> list[str]:
    """Return list of available strategy names."""
    return list(STRATEGIES.keys())

def get_stocks_for_strategies(strategy_names: list[str]) -> list[StrategyStock]:
    """
    Get combined list of stocks for selected strategies.

    Args:
        strategy_names: List of strategy names (1 or 2 strategies)

    Returns:
        List of stock dictionaries with ticker, name, and rationale
    """
    all_stocks: list[StrategyStock] = []
    seen: set[str] = set()
    for strategy in strategy_names:
        if strategy in STRATEGIES:
            for stock in STRATEGIES[strategy]["stocks"]:
                ticker = stock["ticker"]
                if ticker in seen:
                    continue
                merged = cast(StrategyStock, dict(stock))
                merged["strategy"] = strategy
                all_stocks.append(merged)
                seen.add(ticker)
    return all_stocks

def get_strategy_description(strategy_name: str) -> str:
    """Get description for a specific strategy."""
    strategy = STRATEGIES.get(strategy_name)
    if not strategy:
        return ""
    return strategy["description"]
