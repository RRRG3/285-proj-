"""Centralized application configuration with environment-variable overrides.

Every tunable constant lives here so operators can adjust behavior without
touching source code.  Values fall through in this order:

    1. Explicit environment variable  (``QPL_*``)
    2. Default defined in this module
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env_float(key: str, default: float) -> float:
    raw = os.environ.get(key)
    if raw is None:
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _env_int(key: str, default: int) -> int:
    raw = os.environ.get(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _env_bool(key: str, default: bool) -> bool:
    raw = os.environ.get(key)
    if raw is None:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class PortfolioConfig:
    """Portfolio engine tuning knobs."""

    min_investment: float = _env_float("QPL_MIN_INVESTMENT", 5000.0)
    min_per_stock: float = _env_float("QPL_MIN_PER_STOCK", 100.0)
    default_annualized_volatility: float = _env_float("QPL_DEFAULT_VOL", 0.30)
    volatility_floor: float = _env_float("QPL_VOL_FLOOR", 0.08)


@dataclass(frozen=True)
class DataConfig:
    """Market data fetching parameters."""

    price_cache_seconds: int = _env_int("QPL_PRICE_CACHE_SEC", 60)
    history_cache_seconds: int = _env_int("QPL_HISTORY_CACHE_SEC", 300)
    volatility_cache_seconds: int = _env_int("QPL_VOL_CACHE_SEC", 900)
    matrix_cache_seconds: int = _env_int("QPL_MATRIX_CACHE_SEC", 600)
    quote_stale_seconds_open: int = _env_int("QPL_STALE_OPEN_SEC", 900)
    quote_stale_seconds_other: int = _env_int("QPL_STALE_OTHER_SEC", 86400)
    request_timeout_seconds: int = _env_int("QPL_REQUEST_TIMEOUT_SEC", 5)
    demo_mode_enabled: bool = _env_bool("QPL_DEMO_MODE", False)


@dataclass(frozen=True)
class RiskConfig:
    """Risk model thresholds and coefficients."""

    participation_rate: float = _env_float("QPL_RISK_PARTICIPATION", 0.10)
    commission_bps: float = _env_float("QPL_RISK_COMMISSION_BPS", 1.0)
    spread_floor_bps: float = _env_float("QPL_RISK_SPREAD_FLOOR_BPS", 2.0)
    spread_volatility_multiplier: float = _env_float("QPL_RISK_SPREAD_VOL_MULT", 35.0)
    impact_coefficient_bps: float = _env_float("QPL_RISK_IMPACT_COEFF_BPS", 18.0)
    var_confidence: float = _env_float("QPL_VAR_CONFIDENCE", 0.95)
    portfolio_var_limit_pct: float = _env_float("QPL_VAR_LIMIT_PCT", 2.5)
    max_single_position_pct: float = _env_float("QPL_MAX_POSITION_PCT", 25.0)
    stress_warning_drawdown_pct: float = _env_float("QPL_STRESS_WARN_PCT", -8.0)


@dataclass(frozen=True)
class AnalyticsConfig:
    """Backtest and analytics parameters."""

    transaction_cost_bps: float = _env_float("QPL_TXN_COST_BPS", 10.0)
    rebalance_frequency: str = os.environ.get("QPL_REBALANCE_FREQ", "monthly")
    risk_free_rate_annual: float = _env_float("QPL_RISK_FREE_RATE", 0.02)
    drift_threshold_pct: float = _env_float("QPL_DRIFT_THRESHOLD_PCT", 5.0)
    default_horizons: tuple[int, ...] = (1, 3, 5)
    monte_carlo_simulations: int = _env_int("QPL_MC_SIMULATIONS", 1000)
    monte_carlo_days: int = _env_int("QPL_MC_DAYS", 252)


@dataclass(frozen=True)
class SchedulerConfig:
    """Background scheduler parameters."""

    interval_seconds: int = _env_int("QPL_SCHEDULER_INTERVAL_SEC", 300)
    run_hour_et: int = _env_int("QPL_SCHEDULER_RUN_HOUR_ET", 18)


@dataclass(frozen=True)
class ServerConfig:
    """Flask server parameters."""

    port: int = _env_int("QPL_PORT", 8080)
    debug: bool = _env_bool("QPL_DEBUG", True)
    log_dir: str = os.environ.get("QPL_LOG_DIR", "logs")
    data_dir: str = os.environ.get("QPL_DATA_DIR", "data")


@dataclass(frozen=True)
class FrontendConfig:
    """Client-side polling intervals (exposed to JS via template context)."""

    auto_refresh_interval_ms: int = _env_int("QPL_AUTO_REFRESH_MS", 10000)
    market_tape_interval_ms: int = _env_int("QPL_TAPE_INTERVAL_MS", 15000)
    ops_monitor_interval_ms: int = _env_int("QPL_OPS_MONITOR_MS", 15000)


@dataclass(frozen=True)
class AppConfig:
    """Root configuration container aggregating all sub-configs."""

    portfolio: PortfolioConfig = field(default_factory=PortfolioConfig)
    data: DataConfig = field(default_factory=DataConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    analytics: AnalyticsConfig = field(default_factory=AnalyticsConfig)
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    frontend: FrontendConfig = field(default_factory=FrontendConfig)


# Singleton used throughout the application.
settings = AppConfig()
