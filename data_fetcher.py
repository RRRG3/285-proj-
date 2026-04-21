"""Market data fetcher with reliability checks and source fallback."""

from __future__ import annotations

import concurrent.futures
import csv
import hashlib
import io
import math
import os
import time as time_module
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import yfinance as yf

from observability import get_structured_logger, log_event


class StockDataFetcher:
    def __init__(self):
        self.logger = get_structured_logger("qpl.data")
        self.cache = {}
        self.price_cache_seconds = 60
        self.history_cache_seconds = 300
        self.volatility_cache_seconds = 900
        self.matrix_cache_seconds = 600
        self.quote_stale_seconds_open = 15 * 60
        self.quote_stale_seconds_other = 24 * 60 * 60
        self.request_timeout_seconds = 5
        self.ny_tz = ZoneInfo("America/New_York")
        self.demo_mode_enabled = os.environ.get("QPL_DEMO_MODE", "0").lower() in {"1", "true", "yes", "on"}
        self.demo_catalog = {
            "AAPL": 206.30,
            "ADBE": 497.20,
            "NSRGY": 102.15,
            "MSFT": 416.80,
            "TSLA": 182.40,
            "NVDA": 955.10,
            "AMZN": 185.30,
            "META": 497.90,
            "VTI": 265.50,
            "IXUS": 66.40,
            "ILTB": 50.30,
            "SPY": 521.70,
            "JNJ": 153.40,
            "PG": 165.70,
            "KO": 62.80,
            "V": 279.30,
            "BRK-B": 493.00,
            "BAC": 39.60,
            "CVX": 162.20,
            "VZ": 42.80,
            "QQQ": 446.20,
            "AGG": 97.10,
            "^VIX": 16.20,
            "^TNX": 4.18,
            "DX-Y.NYB": 104.20,
        }
        self.monitoring = {
            "quote_requests": 0,
            "quote_failures": 0,
            "yfinance_failures": 0,
            "stooq_failures": 0,
            "history_requests": 0,
            "history_failures": 0,
            "fallback_quotes": 0,
            "stale_quotes": 0,
            "demo_quotes_served": 0,
        }
        self.monitor_events = []
        self.max_monitor_events = 2000

    def _cache_get(self, key):
        cached = self.cache.get(key)
        if not cached:
            return None
        created_at, ttl_seconds, value = cached
        if time_module.time() - created_at <= ttl_seconds:
            return value
        return None

    def _cache_set(self, key, value, ttl_seconds):
        self.cache[key] = (time_module.time(), ttl_seconds, value)

    def set_demo_mode(self, enabled):
        """Enable or disable synthetic market-data fallback mode."""
        self.demo_mode_enabled = bool(enabled)
        self._record_event("demo_mode_toggle", detail={"enabled": self.demo_mode_enabled})

    def _increment_monitor(self, key, delta=1):
        self.monitoring[key] = self.monitoring.get(key, 0) + delta

    def _trim_monitor_events(self):
        if len(self.monitor_events) > self.max_monitor_events:
            overflow = len(self.monitor_events) - self.max_monitor_events
            del self.monitor_events[:overflow]

    def _record_event(self, event_type, ticker=None, detail=None):
        payload = {
            "ts": datetime.now(timezone.utc),
            "event_type": event_type,
            "ticker": ticker,
            "detail": detail or {},
        }
        self.monitor_events.append(payload)
        self._trim_monitor_events()

    def _record_error(self, stage, ticker, error):
        text = str(error)
        self._record_event(
            "error",
            ticker=ticker,
            detail={"stage": stage, "message": text[:240]},
        )
        log_event(
            self.logger,
            "warning",
            "data_fetch_error",
            stage=stage,
            ticker=ticker,
            error=text[:240],
        )

    def _base_price_for_ticker(self, ticker):
        if ticker in self.demo_catalog:
            return float(self.demo_catalog[ticker])
        # Deterministic base in [40, 260] for unknown symbols.
        digest = hashlib.sha256(ticker.encode("utf-8")).hexdigest()
        span = int(digest[:8], 16) / 0xFFFFFFFF
        return 40.0 + span * 220.0

    def _demo_price_for_ticker(self, ticker, now_utc=None):
        if now_utc is None:
            now_utc = datetime.now(timezone.utc)
        base = self._base_price_for_ticker(ticker)
        bucket = now_utc.minute // 5
        digest = hashlib.sha256(f"{ticker}-{now_utc.date()}-{bucket}".encode("utf-8")).hexdigest()
        noise_unit = int(digest[:8], 16) / 0xFFFFFFFF
        intraday_noise = (noise_unit - 0.5) * 0.024  # +/- 1.2%
        return max(1.0, base * (1.0 + intraday_noise))

    def _quote_from_demo_mode(self, ticker):
        now_utc = datetime.now(timezone.utc)
        return {
            "price": self._demo_price_for_ticker(ticker, now_utc=now_utc),
            "timestamp": now_utc,
            "source": "demo_mode_synthetic",
            "market_state": self._market_status_from_clock(),
            "currency": "USD",
        }

    def _demo_history_series(self, ticker, start_date, end_date):
        dates = pd.bdate_range(start=start_date, end=end_date)
        if len(dates) == 0:
            return pd.Series(dtype="float64")

        base = self._base_price_for_ticker(ticker)
        closes = []
        for index, dt_value in enumerate(dates):
            date_key = dt_value.strftime("%Y-%m-%d")
            digest = hashlib.sha256(f"{ticker}-{date_key}".encode("utf-8")).hexdigest()
            random_component = int(digest[:8], 16) / 0xFFFFFFFF
            noise = (random_component - 0.5) * 0.05  # +/- 2.5%
            drift = 0.0004 * index
            closes.append(max(1.0, base * (1.0 + drift + noise)))

        return pd.Series(closes, index=dates, dtype="float64")

    @staticmethod
    def _safe_float(value):
        try:
            if value in (None, "", "N/D"):
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    def _market_status_from_clock(self):
        now_et = datetime.now(self.ny_tz)
        if now_et.weekday() >= 5:
            return "CLOSED"

        current_time = now_et.time()
        if time(9, 30) <= current_time < time(16, 0):
            return "OPEN"
        if time(4, 0) <= current_time < time(9, 30):
            return "PRE_MARKET"
        if time(16, 0) <= current_time < time(20, 0):
            return "AFTER_HOURS"
        return "CLOSED"

    @staticmethod
    def _normalize_market_state(raw_state):
        if not raw_state:
            return None

        state = str(raw_state).upper()
        mapping = {
            "REGULAR": "OPEN",
            "OPEN": "OPEN",
            "CLOSED": "CLOSED",
            "CLOSE": "CLOSED",
            "PRE": "PRE_MARKET",
            "PREPRE": "PRE_MARKET",
            "POST": "AFTER_HOURS",
            "POSTPOST": "AFTER_HOURS",
        }
        return mapping.get(state, None)

    def get_market_clock(self):
        """Return market session metadata based on U.S. market hours."""
        now_et = datetime.now(self.ny_tz)
        return {
            "as_of": now_et.isoformat(),
            "timezone": "America/New_York",
            "market_status": self._market_status_from_clock(),
            "weekday": now_et.strftime("%A"),
        }

    def _stooq_symbol(self, ticker):
        return f"{ticker.lower().replace('.', '-').replace('/', '-')}.us"

    def _quote_from_yfinance_fast_info(self, stock):
        fast_info = getattr(stock, "fast_info", {}) or {}
        price = (
            fast_info.get("lastPrice")
            or fast_info.get("regularMarketPrice")
            or fast_info.get("previousClose")
        )
        if not price:
            return None

        return {
            "price": float(price),
            "timestamp": None,
            "source": "yfinance_fast_info",
            "market_state": fast_info.get("marketState"),
        }

    def _quote_from_yfinance_info(self, stock):
        info = stock.info
        if not isinstance(info, dict):
            return None

        price = (
            info.get("currentPrice")
            or info.get("regularMarketPrice")
            or info.get("previousClose")
        )
        if not price:
            return None

        timestamp = None
        quote_timestamp = info.get("regularMarketTime")
        if quote_timestamp:
            timestamp = datetime.fromtimestamp(float(quote_timestamp), tz=timezone.utc)

        return {
            "price": float(price),
            "timestamp": timestamp,
            "source": "yfinance_info",
            "market_state": info.get("marketState"),
            "currency": info.get("currency"),
        }

    def _quote_from_yfinance_history(self, stock):
        hist = stock.history(period="5d", interval="1d")
        if hist.empty:
            return None

        close = self._safe_float(hist["Close"].iloc[-1])
        if close is None:
            return None

        idx = hist.index[-1]
        if isinstance(idx, pd.Timestamp):
            timestamp = idx.to_pydatetime()
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=self.ny_tz)
        else:
            timestamp = datetime.now(self.ny_tz)

        return {
            "price": close,
            "timestamp": timestamp,
            "source": "yfinance_history",
            "market_state": None,
        }

    def _quote_from_stooq(self, ticker):
        symbol = self._stooq_symbol(ticker)
        url = f"https://stooq.com/q/l/?s={symbol}&f=sd2t2ohlcv&h&e=csv"
        response = requests.get(url, timeout=self.request_timeout_seconds)
        if not response.ok or not response.text:
            return None

        reader = csv.DictReader(io.StringIO(response.text))
        row = next(reader, None)
        if not row:
            return None

        close = self._safe_float(row.get("Close"))
        if close is None:
            return None

        timestamp = None
        date_part = row.get("Date")
        time_part = row.get("Time")
        if date_part and date_part != "N/D":
            try:
                if time_part and time_part != "N/D":
                    timestamp = datetime.fromisoformat(f"{date_part} {time_part}").replace(
                        tzinfo=self.ny_tz
                    )
                else:
                    timestamp = datetime.fromisoformat(date_part).replace(
                        hour=16, minute=0, second=0, tzinfo=self.ny_tz
                    )
            except ValueError:
                timestamp = None

        return {
            "price": close,
            "timestamp": timestamp,
            "source": "stooq_csv",
            "market_state": None,
        }

    def _enrich_quote(self, ticker, quote):
        timestamp = quote.get("timestamp")
        if timestamp and timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)

        now_utc = datetime.now(timezone.utc)
        age_seconds = None
        if timestamp is not None:
            age_seconds = max(0.0, (now_utc - timestamp.astimezone(timezone.utc)).total_seconds())

        market_status = self._normalize_market_state(quote.get("market_state"))
        if market_status is None:
            market_status = self._market_status_from_clock()

        stale_limit = (
            self.quote_stale_seconds_open if market_status == "OPEN" else self.quote_stale_seconds_other
        )
        is_stale = bool(age_seconds is not None and age_seconds > stale_limit)

        source = quote.get("source", "unknown")
        base_reliability = {
            "yfinance_fast_info": 0.95,
            "yfinance_info": 0.90,
            "yfinance_history": 0.76,
            "stooq_csv": 0.68,
            "demo_mode_synthetic": 0.72,
        }.get(source, 0.60)

        quality_flags = []
        if source in {"yfinance_history", "stooq_csv"}:
            quality_flags.append("FALLBACK_SOURCE")
            base_reliability -= 0.08
        if source == "demo_mode_synthetic":
            quality_flags.append("DEMO_MODE")
            quality_flags.append("FALLBACK_SOURCE")
            base_reliability -= 0.05
        if is_stale:
            quality_flags.append("STALE_QUOTE")
            base_reliability -= 0.25
        if age_seconds is None:
            quality_flags.append("TIMESTAMP_UNAVAILABLE")
            base_reliability -= 0.04

        reliability_score = max(0.0, min(1.0, base_reliability))

        return {
            "ticker": ticker,
            "price": float(quote["price"]),
            "timestamp": timestamp.isoformat() if timestamp else None,
            "age_seconds": age_seconds,
            "source": source,
            "market_status": market_status,
            "is_stale": is_stale,
            "quality_flags": quality_flags,
            "reliability_score": reliability_score,
            "currency": quote.get("currency", "USD"),
        }

    def get_quote(self, ticker):
        """
        Get quote + quality metadata for a ticker.

        Returns:
            dict | None
        """
        self._increment_monitor("quote_requests", 1)
        cache_key = ("quote", ticker)
        cached_quote = self._cache_get(cache_key)
        if cached_quote is not None:
            return cached_quote

        if self.demo_mode_enabled:
            quote = self._quote_from_demo_mode(ticker)
            enriched_quote = self._enrich_quote(ticker, quote)
            self._increment_monitor("demo_quotes_served", 1)
            self._increment_monitor("fallback_quotes", 1)
            self._record_event("demo_quote_served", ticker=ticker)
            self._cache_set(cache_key, enriched_quote, self.price_cache_seconds)
            return enriched_quote

        quote = None
        errors = []
        try:
            stock = yf.Ticker(ticker)
            for method in (
                self._quote_from_yfinance_fast_info,
                self._quote_from_yfinance_info,
                self._quote_from_yfinance_history,
            ):
                try:
                    quote = method(stock)
                    if quote:
                        break
                except Exception as exc:
                    errors.append(str(exc))
                    self._increment_monitor("yfinance_failures", 1)
                    self._record_error("yfinance_quote_method", ticker, exc)
        except Exception as exc:
            errors.append(str(exc))
            self._increment_monitor("yfinance_failures", 1)
            self._record_error("yfinance_quote_init", ticker, exc)

        if not quote:
            try:
                quote = self._quote_from_stooq(ticker)
            except Exception as exc:
                errors.append(str(exc))
                self._increment_monitor("stooq_failures", 1)
                self._record_error("stooq_quote", ticker, exc)

        if not quote:
            self._increment_monitor("quote_failures", 1)
            self._record_event("quote_unavailable", ticker=ticker)
            if errors:
                print(f"Error fetching quote for {ticker}: {' | '.join(errors)}")
            return None

        enriched_quote = self._enrich_quote(ticker, quote)
        if "FALLBACK_SOURCE" in enriched_quote.get("quality_flags", []):
            self._increment_monitor("fallback_quotes", 1)
            self._record_event("fallback_quote", ticker=ticker, detail={"source": enriched_quote.get("source")})
        if enriched_quote.get("is_stale"):
            self._increment_monitor("stale_quotes", 1)
            self._record_event("stale_quote", ticker=ticker, detail={"source": enriched_quote.get("source")})

        self._cache_set(cache_key, enriched_quote, self.price_cache_seconds)
        return enriched_quote

    def get_current_price(self, ticker):
        """Get near real-time price for one ticker."""
        quote = self.get_quote(ticker)
        if quote:
            return quote["price"]
        return None

    def get_multiple_quotes(self, tickers):
        """Return quotes for all tickers that can be resolved, using parallel requests."""
        quotes = {}
        unique_tickers = list(set(tickers))

        with concurrent.futures.ThreadPoolExecutor(max_workers=min(10, len(unique_tickers) or 1)) as executor:
            future_to_ticker = {executor.submit(self.get_quote, t): t for t in unique_tickers}
            for future in concurrent.futures.as_completed(future_to_ticker):
                ticker = future_to_ticker[future]
                try:
                    quote = future.result()
                    if quote:
                        quotes[ticker] = quote
                except Exception as exc:
                    log_event(self.logger, "error", "parallel_quote_fetch_failed", ticker=ticker, error=str(exc))
        return quotes

    def get_multiple_prices(self, tickers):
        """Return `{ticker: price}` for all tickers that resolved successfully."""
        quotes = self.get_multiple_quotes(tickers)
        return {ticker: payload["price"] for ticker, payload in quotes.items()}

    def summarize_quote_quality(self, quotes):
        """Aggregate quality diagnostics for a list of quote payloads."""
        if not quotes:
            market_clock = self.get_market_clock()
            return {
                "market_status": market_clock["market_status"],
                "as_of": market_clock["as_of"],
                "quotes_received": 0,
                "stale_count": 0,
                "fallback_count": 0,
                "average_reliability": 0.0,
                "stale_tickers": [],
                "fallback_tickers": [],
                "demo_mode_enabled": self.demo_mode_enabled,
            }

        stale_tickers = [quote["ticker"] for quote in quotes if quote.get("is_stale")]
        fallback_tickers = [
            quote["ticker"] for quote in quotes if "FALLBACK_SOURCE" in quote.get("quality_flags", [])
        ]
        reliability_values = [quote.get("reliability_score", 0.0) for quote in quotes]

        statuses = [quote.get("market_status", "UNKNOWN") for quote in quotes]
        status_counter = Counter(statuses)
        dominant_status = status_counter.most_common(1)[0][0] if status_counter else "UNKNOWN"

        return {
            "market_status": dominant_status,
            "as_of": datetime.now(timezone.utc).isoformat(),
            "quotes_received": len(quotes),
            "stale_count": len(stale_tickers),
            "fallback_count": len(fallback_tickers),
            "average_reliability": sum(reliability_values) / len(reliability_values),
            "stale_tickers": stale_tickers,
            "fallback_tickers": fallback_tickers,
            "demo_mode_enabled": self.demo_mode_enabled,
        }

    def _history_from_stooq(self, ticker, start_date, end_date):
        symbol = self._stooq_symbol(ticker)
        url = f"https://stooq.com/q/d/l/?s={symbol}&i=d"
        response = requests.get(url, timeout=self.request_timeout_seconds)
        if not response.ok or not response.text:
            return pd.Series(dtype="float64")

        frame = pd.read_csv(io.StringIO(response.text))
        if frame.empty or "Date" not in frame.columns or "Close" not in frame.columns:
            return pd.Series(dtype="float64")

        frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce")
        frame["Close"] = pd.to_numeric(frame["Close"], errors="coerce")
        frame = frame.dropna(subset=["Date", "Close"])
        frame = frame.sort_values("Date")
        frame = frame[(frame["Date"] >= pd.Timestamp(start_date)) & (frame["Date"] <= pd.Timestamp(end_date))]
        if frame.empty:
            return pd.Series(dtype="float64")
        return frame.set_index("Date")["Close"]

    def get_price_history_frame(self, tickers, start_date, end_date):
        """
        Get a daily close-price DataFrame for multiple tickers with fallback.

        Returns:
            (pd.DataFrame, dict) where dict maps ticker to source metadata.
        """
        self._increment_monitor("history_requests", 1)
        normalized_tickers = sorted(set(tickers))
        cache_key = (
            "matrix",
            tuple(normalized_tickers),
            start_date.isoformat(),
            end_date.isoformat(),
        )
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached[0].copy(), dict(cached[1])

        if self.demo_mode_enabled:
            quality_map = {}
            close_df = pd.DataFrame()
            for ticker in normalized_tickers:
                demo_series = self._demo_history_series(ticker, start_date, end_date)
                if demo_series.empty:
                    quality_map[ticker] = {"source": "unavailable", "points": 0}
                    continue
                demo_frame = demo_series.rename(ticker).to_frame()
                close_df = demo_frame if close_df.empty else close_df.join(demo_frame, how="outer")
                quality_map[ticker] = {"source": "demo_mode_synthetic", "points": int(demo_series.shape[0])}
                self._record_event("demo_history_used", ticker=ticker)

            close_df = close_df.sort_index().dropna(how="all") if not close_df.empty else close_df
            self._cache_set(cache_key, (close_df.copy(), dict(quality_map)), self.matrix_cache_seconds)
            return close_df, quality_map

        quality_map = {ticker: {"source": "unavailable"} for ticker in normalized_tickers}
        close_df = pd.DataFrame()

        if normalized_tickers:
            try:
                downloaded = yf.download(
                    tickers=normalized_tickers,
                    start=start_date,
                    end=end_date + timedelta(days=1),
                    interval="1d",
                    auto_adjust=True,
                    progress=False,
                    threads=True,
                    group_by="column",
                )

                if isinstance(downloaded, pd.DataFrame) and not downloaded.empty:
                    if isinstance(downloaded.columns, pd.MultiIndex):
                        if "Close" in downloaded.columns.get_level_values(0):
                            close_df = downloaded["Close"].copy()
                        elif "Adj Close" in downloaded.columns.get_level_values(0):
                            close_df = downloaded["Adj Close"].copy()
                    else:
                        # Single ticker shape
                        if "Close" in downloaded.columns:
                            ticker = normalized_tickers[0]
                            close_df = downloaded[["Close"]].rename(columns={"Close": ticker})
                        elif "Adj Close" in downloaded.columns:
                            ticker = normalized_tickers[0]
                            close_df = downloaded[["Adj Close"]].rename(columns={"Adj Close": ticker})
            except Exception as exc:
                print(f"Error downloading matrix via yfinance: {exc}")
                self._increment_monitor("yfinance_failures", 1)
                self._record_error("yfinance_matrix", ",".join(normalized_tickers), exc)

        if isinstance(close_df, pd.Series):
            close_df = close_df.to_frame()

        if not close_df.empty:
            close_df.index = pd.to_datetime(close_df.index)
            close_df = close_df.sort_index()
            close_df = close_df.apply(pd.to_numeric, errors="coerce")
            for ticker in close_df.columns:
                if ticker in quality_map and close_df[ticker].dropna().shape[0] > 0:
                    quality_map[ticker] = {"source": "yfinance_download"}

        # Fallback to Stooq for missing tickers
        for ticker in normalized_tickers:
            needs_fallback = (
                close_df.empty
                or ticker not in close_df.columns
                or close_df[ticker].dropna().shape[0] < 20
            )
            if not needs_fallback:
                continue

            try:
                stooq_series = self._history_from_stooq(ticker, start_date, end_date)
                if stooq_series.empty:
                    continue

                stooq_series = stooq_series.rename(ticker)
                stooq_frame = stooq_series.to_frame()
                if close_df.empty:
                    close_df = stooq_frame
                else:
                    if ticker in close_df.columns:
                        close_df[ticker] = close_df[ticker].combine_first(stooq_frame[ticker])
                    else:
                        close_df = close_df.join(stooq_frame, how="outer")

                quality_map[ticker] = {"source": "stooq_csv"}
            except Exception as exc:
                print(f"Error fetching Stooq history for {ticker}: {exc}")
                self._increment_monitor("stooq_failures", 1)
                self._record_error("stooq_history", ticker, exc)

        if not close_df.empty:
            close_df = close_df.sort_index()
            close_df = close_df.loc[
                (close_df.index >= pd.Timestamp(start_date)) & (close_df.index <= pd.Timestamp(end_date))
            ]
            close_df = close_df.dropna(how="all")

        for ticker in normalized_tickers:
            if ticker in close_df.columns:
                quality_map[ticker]["points"] = int(close_df[ticker].dropna().shape[0])
            else:
                quality_map[ticker]["points"] = 0
                quality_map[ticker]["source"] = "unavailable"

        if close_df.empty:
            self._increment_monitor("history_failures", 1)
            self._record_event("history_unavailable", detail={"tickers": normalized_tickers})
        else:
            fallback_count = sum(
                1
                for ticker in normalized_tickers
                if quality_map.get(ticker, {}).get("source") in {"stooq_csv", "demo_mode_synthetic"}
            )
            if fallback_count > 0:
                self._record_event("history_fallback_batch", detail={"count": fallback_count})

        self._cache_set(cache_key, (close_df.copy(), dict(quality_map)), self.matrix_cache_seconds)
        return close_df, quality_map

    def get_historical_data(self, ticker, days=5):
        """
        Get historical close data for the most recent trading days.

        Returns:
            list[tuple[str, float]] as (YYYY-MM-DD, close)
        """
        cache_key = ("history", ticker, days)
        cached_history = self._cache_get(cache_key)
        if cached_history is not None:
            return cached_history

        end_date = date.today()
        start_date = end_date - timedelta(days=days + 12)
        frame, _ = self.get_price_history_frame([ticker], start_date, end_date)

        if frame.empty or ticker not in frame.columns:
            return []

        series = frame[ticker].dropna().tail(days)
        result = [(idx.strftime("%Y-%m-%d"), float(price)) for idx, price in series.items()]
        self._cache_set(cache_key, result, self.history_cache_seconds)
        return result

    def get_bulk_recent_history(self, tickers, days=5):
        """
        Return close history maps for multiple tickers.

        Returns:
            dict[str, dict[str, float]] as `{ticker: {date: close}}`
        """
        history_map = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(10, len(tickers) or 1)) as executor:
            future_to_ticker = {executor.submit(self.get_historical_data, t, days=days): t for t in tickers}
            for future in concurrent.futures.as_completed(future_to_ticker):
                ticker = future_to_ticker[future]
                try:
                    entries = future.result()
                    if entries:
                        history_map[ticker] = {day: close for day, close in entries}
                except Exception:
                    pass
        return history_map

    def get_annualized_volatility(self, ticker, lookback_days=90):
        """
        Estimate annualized volatility from daily close-to-close returns.

        Returns:
            float | None
        """
        cache_key = ("volatility", ticker, lookback_days)
        cached_volatility = self._cache_get(cache_key)
        if cached_volatility is not None:
            return cached_volatility

        end_date = date.today()
        start_date = end_date - timedelta(days=lookback_days + 60)
        frame, _ = self.get_price_history_frame([ticker], start_date, end_date)
        if frame.empty or ticker not in frame.columns:
            return None

        returns = frame[ticker].dropna().pct_change().dropna().tail(lookback_days)
        if returns.empty:
            return None

        volatility = float(returns.std() * math.sqrt(252))
        if volatility <= 0:
            return None

        self._cache_set(cache_key, volatility, self.volatility_cache_seconds)
        return volatility

    def validate_ticker(self, ticker):
        """Check if a ticker is valid and has an accessible market price."""
        quote = self.get_quote(ticker)
        return bool(quote and quote.get("price") is not None)

    def get_monitoring_snapshot(self):
        """Return operational telemetry for UI/dashboard monitoring."""
        now = datetime.now(timezone.utc)
        lookback_hours = 12
        threshold = now - timedelta(hours=lookback_hours)
        recent_events = [event for event in self.monitor_events if event["ts"] >= threshold]

        labels = []
        fallback_counts = []
        error_counts = []
        for hours_ago in range(lookback_hours - 1, -1, -1):
            bucket_start = (now - timedelta(hours=hours_ago)).replace(minute=0, second=0, microsecond=0)
            bucket_end = bucket_start + timedelta(hours=1)
            labels.append(bucket_start.strftime("%H:%M"))

            fallback_count = sum(
                1
                for event in recent_events
                if event["event_type"] in {"fallback_quote", "history_fallback_batch", "demo_history_used"}
                and bucket_start <= event["ts"] < bucket_end
            )
            error_count = sum(
                1
                for event in recent_events
                if event["event_type"] in {"error", "quote_unavailable", "history_unavailable"}
                and bucket_start <= event["ts"] < bucket_end
            )
            fallback_counts.append(fallback_count)
            error_counts.append(error_count)

        error_samples = []
        for event in reversed(recent_events):
            if event["event_type"] != "error":
                continue
            detail = event.get("detail", {})
            ticker = event.get("ticker") or "N/A"
            stage = detail.get("stage", "unknown")
            message = detail.get("message", "unknown error")
            error_samples.append(f"{ticker} [{stage}] {message}")
            if len(error_samples) >= 5:
                break

        quote_requests = max(1, self.monitoring.get("quote_requests", 0))
        quote_failures = self.monitoring.get("quote_failures", 0)
        failure_rate = (quote_failures / quote_requests) * 100.0

        return {
            "demo_mode_enabled": self.demo_mode_enabled,
            "counters": dict(self.monitoring),
            "failure_rate_pct": failure_rate,
            "recent_errors": error_samples,
            "trend": {
                "labels": labels,
                "fallback_counts": fallback_counts,
                "error_counts": error_counts,
            },
            "summary": (
                f"Quotes {self.monitoring.get('quote_requests', 0)} requests / "
                f"{quote_failures} failures ({failure_rate:.2f}% failure rate), "
                f"{self.monitoring.get('fallback_quotes', 0)} fallback quotes."
            ),
            "as_of": now.isoformat(),
        }

    def get_news(self, ticker: str, limit: int = 3) -> list[dict]:
        """Fetch a small set of recent news headlines for a ticker.

        Returns a list of {title, publisher, url, published_at} dicts. Falls back
        to deterministic synthetic items in demo mode and on any provider failure.
        """
        cache_key = f"news::{ticker}::{limit}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        if self.demo_mode_enabled:
            items = self._demo_news_items(ticker, limit)
            self._cache_set(cache_key, items, 600)
            return items

        try:
            stock = yf.Ticker(ticker)
            raw = getattr(stock, "news", None) or []
            items: list[dict] = []
            for entry in raw[:limit]:
                content = entry.get("content") if isinstance(entry, dict) else None
                if isinstance(content, dict):
                    title = content.get("title")
                    publisher = (content.get("provider") or {}).get("displayName") or content.get("publisher")
                    url = (content.get("clickThroughUrl") or {}).get("url") or (content.get("canonicalUrl") or {}).get("url")
                    published = content.get("pubDate") or content.get("displayTime")
                else:
                    title = entry.get("title")
                    publisher = entry.get("publisher")
                    url = entry.get("link")
                    ts = entry.get("providerPublishTime")
                    published = (
                        datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
                        if isinstance(ts, (int, float))
                        else None
                    )
                if not title:
                    continue
                items.append(
                    {
                        "title": title,
                        "publisher": publisher or "—",
                        "url": url,
                        "published_at": published,
                    }
                )
            if not items:
                items = self._demo_news_items(ticker, limit)
            self._cache_set(cache_key, items, 600)
            return items
        except Exception as exc:  # pragma: no cover - network surface
            self._record_error("news_fetch", ticker, exc)
            items = self._demo_news_items(ticker, limit)
            self._cache_set(cache_key, items, 600)
            return items

    def _demo_news_items(self, ticker: str, limit: int) -> list[dict]:
        templates = [
            ("{t}: analysts revisit price targets ahead of next earnings cycle", "Markets Daily"),
            ("Sector rotation lifts {t} as macro narrative shifts", "Capital Edge"),
            ("Options flow on {t} skews bullish for the upcoming week", "Volatility Watch"),
            ("{t} CFO comments on margin trajectory and capital plans", "Investor Brief"),
            ("Index rebalance window puts modest pressure on {t}", "Index Insights"),
        ]
        digest = int(hashlib.sha256(ticker.encode("utf-8")).hexdigest(), 16)
        chosen = []
        for offset in range(limit):
            tmpl_idx = (digest + offset) % len(templates)
            title, publisher = templates[tmpl_idx]
            published = (datetime.now(timezone.utc) - timedelta(hours=2 * (offset + 1))).isoformat()
            chosen.append({
                "title": title.format(t=ticker),
                "publisher": publisher,
                "url": None,
                "published_at": published,
            })
        return chosen

    def get_news_for_tickers(self, tickers: list[str], limit_each: int = 3) -> dict[str, list[dict]]:
        """Fetch news for many tickers in parallel."""
        if not tickers:
            return {}
        result: dict[str, list[dict]] = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(tickers))) as executor:
            futures = {executor.submit(self.get_news, t, limit_each): t for t in tickers}
            for future in concurrent.futures.as_completed(futures):
                ticker = futures[future]
                try:
                    result[ticker] = future.result()
                except Exception:
                    result[ticker] = []
        return result
