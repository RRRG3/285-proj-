"""Tests for the centralized AppConfig configuration module."""

from __future__ import annotations

from config import AppConfig, _env_bool, _env_float, _env_int


def test_default_config_has_sane_values():
    """Default config should have reasonable production defaults."""
    config = AppConfig()
    assert config.portfolio.min_investment == 5000.0
    assert config.data.price_cache_seconds == 60
    assert config.risk.var_confidence == 0.95
    assert config.analytics.drift_threshold_pct == 5.0
    assert config.server.port == 8080


def test_env_float_returns_default_on_missing():
    assert _env_float("QPL_NONEXISTENT_KEY_FLOAT", 42.0) == 42.0


def test_env_float_returns_parsed_value(monkeypatch):
    monkeypatch.setenv("QPL_TEST_FLOAT", "3.14")
    assert _env_float("QPL_TEST_FLOAT", 0.0) == 3.14


def test_env_float_returns_default_on_invalid(monkeypatch):
    monkeypatch.setenv("QPL_TEST_FLOAT_BAD", "not_a_number")
    assert _env_float("QPL_TEST_FLOAT_BAD", 1.0) == 1.0


def test_env_int_returns_default_on_missing():
    assert _env_int("QPL_NONEXISTENT_KEY_INT", 99) == 99


def test_env_int_returns_parsed_value(monkeypatch):
    monkeypatch.setenv("QPL_TEST_INT", "7")
    assert _env_int("QPL_TEST_INT", 0) == 7


def test_env_bool_returns_default_on_missing():
    assert _env_bool("QPL_NONEXISTENT_KEY_BOOL", False) is False
    assert _env_bool("QPL_NONEXISTENT_KEY_BOOL", True) is True


def test_env_bool_recognizes_true_values(monkeypatch):
    for truthy in ["1", "true", "yes", "on"]:
        monkeypatch.setenv("QPL_TEST_BOOL", truthy)
        assert _env_bool("QPL_TEST_BOOL", False) is True


def test_env_bool_recognizes_false_values(monkeypatch):
    for falsy in ["0", "false", "no", "off"]:
        monkeypatch.setenv("QPL_TEST_BOOL", falsy)
        assert _env_bool("QPL_TEST_BOOL", True) is False


def test_config_is_frozen():
    """AppConfig should be immutable (frozen=True)."""
    config = AppConfig()
    try:
        config.portfolio = None  # type: ignore
        assert False, "Should have raised FrozenInstanceError"
    except AttributeError:
        pass


def test_sub_configs_are_frozen():
    """Sub-configs should also be immutable."""
    config = AppConfig()
    try:
        config.portfolio.min_investment = 999  # type: ignore
        assert False, "Should have raised FrozenInstanceError"
    except AttributeError:
        pass
