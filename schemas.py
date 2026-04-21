"""Pydantic request schemas for strict API validation."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from strategies import STRATEGIES

ALLOWED_STRATEGIES = frozenset(STRATEGIES.keys())


class BaseStrictModel(BaseModel):
    """Common strict schema defaults for API request payloads."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )


class RiskProfile(BaseStrictModel):
    """3-question risk profile that tilts the allocation."""
    age: int = Field(..., ge=18, le=99)
    horizon_years: int = Field(..., ge=1, le=50)
    max_drawdown_tolerance_pct: float = Field(..., ge=5.0, le=60.0)


class GeneratePortfolioRequest(BaseStrictModel):
    amount: float = Field(..., ge=5000)
    strategies: list[str] = Field(..., min_length=1, max_length=2)
    risk_profile: RiskProfile | None = None

    @field_validator("strategies")
    @classmethod
    def _validate_strategy_names(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if isinstance(item, str) and item.strip()]
        if len(cleaned) == 0:
            raise ValueError("Please select 1 or 2 investment strategies")
        if len(cleaned) > 2:
            raise ValueError("Please select 1 or 2 investment strategies")
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("Please select unique investment strategies")
        invalid = [item for item in cleaned if item not in ALLOWED_STRATEGIES]
        if invalid:
            raise ValueError(f"Unknown strategies: {', '.join(invalid)}")
        return cleaned


class AllocationInput(BaseStrictModel):
    ticker: str
    name: str | None = None
    strategy: str | None = None
    asset_type: str | None = None
    rationale: str | None = None
    conviction: float | None = None
    annualized_volatility: float | None = None
    weight: float | None = None
    weight_pct: float | None = None
    shares: float = Field(..., ge=0)
    price: float = Field(..., ge=0)
    cost: float = Field(..., ge=0)
    current_price: float | None = Field(default=None, ge=0)
    current_value: float | None = Field(default=None, ge=0)
    quote_source: str | None = None
    quote_is_stale: bool | None = None


class RefreshPortfolioRequest(BaseStrictModel):
    portfolio_id: str | None = None
    allocations: list[AllocationInput] = Field(..., min_length=1)
    cash_remainder: float = Field(default=0, ge=0)
    investment_amount: float = Field(default=0, ge=0)
    strategies: list[str] = Field(default_factory=list)
    allocation_method: str = Field(default="Conviction-weighted inverse-volatility model")
    total_allocated: float = Field(default=0, ge=0)

    @field_validator("strategies")
    @classmethod
    def _validate_refresh_strategies(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if isinstance(item, str) and item.strip()]
        invalid = [item for item in cleaned if item not in ALLOWED_STRATEGIES]
        if invalid:
            raise ValueError(f"Unknown strategies: {', '.join(invalid)}")
        return cleaned


class DemoModeToggleRequest(BaseStrictModel):
    enabled: bool


class MarketTickerRequest(BaseStrictModel):
    holdings: list[str] = Field(default_factory=list)

    @field_validator("holdings")
    @classmethod
    def _limit_holdings(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip().upper() for item in value if isinstance(item, str) and item.strip()]
        return cleaned[:5]


class ExportCsvRequest(BaseStrictModel):
    investment_amount: float = 0
    total_value: float = 0
    cash_remainder: float = 0
    strategies: list[str] = Field(default_factory=list)
    allocations: list[AllocationInput] = Field(default_factory=list)

    @field_validator("strategies")
    @classmethod
    def _validate_export_strategies(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if isinstance(item, str) and item.strip()]
        invalid = [item for item in cleaned if item not in ALLOWED_STRATEGIES]
        if invalid:
            raise ValueError(f"Unknown strategies: {', '.join(invalid)}")
        return cleaned
