# Research methodology and validation boundary

Alloc8 is a research and portfolio illustration app. This revision improves numerical correctness and the honesty of its outputs. It does not establish predictive skill, calibrated trade probabilities, or institutional execution quality. No broker or model integration is enabled.

## Allocation

Subjective conviction scores tilt inverse-volatility weights. They are **not** probabilities and must not be used as Kelly inputs. The allocation engine redistributes capital subject to a configurable single-position ceiling (default 25% of initial total capital). When available holdings cannot absorb the budget within the ceiling, the balance stays in cash. `weight` remains a fraction of invested assets; `portfolio_weight_pct` reports the initial fraction of total capital. Ongoing risk checks use current dollar exposure divided by NAV. Limits at allocation do not prevent later market-driven concentration.

Missing volatility uses an explicitly tagged default; nonfinite or nonpositive quotes are excluded. This heuristic is not an optimized, independently validated trading strategy. Correlations, sectors and risk-profile questionnaires do not establish suitability or alpha.

## Historical replay

- Today’s selected securities and target weights are replayed over a requested calendar horizon. Current selection, conviction and volatility estimates can embed hindsight and survivorship bias. **Results are not out-of-sample strategy tests.**
- The current daily candle is excluded. A download buffer does not lengthen the evaluation horizon. Each held security must have complete, finite, positive aligned prices. At least 90% of approximate weekday observations and coverage within seven calendar days of each endpoint are required. Missing holdings are not silently dropped or rescaled.
- This completeness check is conservative and uses weekdays, not an authoritative exchange holiday calendar. A feed-wide missing date cannot be fully detected without such a calendar.
- Benchmarks use exactly the portfolio dates. A benchmark with incomplete data is unavailable, rather than compared over a different sample. Flat per-notional costs apply to benchmarks too; SPY is buy-and-hold, 60/40 is monthly rebalanced.
- Yahoo history requests provider-adjusted closes. Stooq fallback replaces a whole ticker series rather than splicing prices with potentially incompatible adjustment factors. Stooq's adjustment basis is unverified and visibly flagged. Provider-adjusted data are not independently audited corporate-action records.
- Return and drawdown include opening fees relative to pre-trade capital. Opening notional is `(1 - cash_fraction) / (1 + cost_rate)` for a unit starting NAV. Subsequent rebalance fees use **both** buy and sell notionals, solving post-fee holdings and costs against the available budget. No money is created to pay fees.
- Gross turnover and cumulative costs are reported relative to initial capital, not average NAV. Cash is a fixed dollar reserve earning zero. Rebalances restore the relative risky-asset weights, not a constant cash percentage.
- Returns use 252-session annualization. Sharpe uses annualized arithmetic mean daily excess returns divided by annualized sample volatility; it does not use CAGR in the numerator. Opening fees are included in the first holding-period return. Undefined Sharpe/alpha/beta are unavailable, not zero.
- Fractional holdings, close-price execution, a constant risk-free rate, and a flat transaction-cost estimate are simplifying assumptions. There is no order book, fill simulator, capacity model, borrow model, tax calculation, or measured latency/slippage calibration.

The 30-day chart is a separate, cost-free buy-and-hold illustration using the current share mix. All lines start at identical capital on the same date; missing prices are never filled with today's price. It is not an actual account performance record.

## Risk and scenarios

Historical VaR and expected shortfall apply **current dollar exposures / NAV**, so cash reduces percentage risk and is not assumed invested. Missing holdings make the calculation unavailable. Loss estimates have a zero floor. The available lookback and confidence level accompany the result; tail losses can exceed either metric. Named crash scenarios remain broad hypothetical bucket shocks, not event-by-event portfolio reconstructions.

The fan chart uses a reproducible moving-block bootstrap (seed 42, 10-session blocks) of joint portfolio returns. This retains observed tails and short-range dependence within blocks, but cannot represent unobserved crises or guarantee future distributions. It assumes constant risky weights and a constant cash fraction with zero yield and excludes future trading costs. Bands are historical scenarios, not validated prediction intervals. The goal calculator is a **separate illustrative lognormal terminal-value model**, not a bootstrap probability, barrier-hit estimate, or calibrated forecast.

Execution-cost panels use heuristic ADV/spread/impact parameters, not executable market quotes. Source quality scores are heuristics, not measured probabilities of correctness. Unknown quote timestamps are treated as stale/unverified. Live news failures produce no headlines; synthetic headlines appear only in explicit demo mode and carry a DEMO label.

## What is needed before stronger claims

1. Licensed, versioned point-in-time data, corporate actions, delistings, trading calendars and consistent timestamps/currencies; automated reconciliation to an independent source.
2. A strategy defined before evaluation, with lagged features, rolling training windows, untouched chronological holdouts and a record of every strategy tried. A threshold on the best in-sample Sharpe is not evidence of an edge.
3. Tests for leakage, multiple comparisons, parameter stability, capacity, costs, market regimes and uncertainty, plus a reproducible experiment registry.
4. Broker paper fills reconciled to expected fills, calibrated probabilities measured on held-out decisions, and independent risk controls tested through outages and restarts.
5. Operational and independent model review. This app currently has no live-order path or validated trading strategy.

## References

- William F. Sharpe, [The Sharpe Ratio](https://web.stanford.edu/~wfsharpe/art/sr/SR.htm), 1994: differential-return mean and standard deviation, with limitations of time scaling.
- Bailey et al., [Pseudo-Mathematics and Financial Charlatanism: The Effects of Backtest Overfitting on Out-of-Sample Performance](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2308659), 2014: repeated strategy selection can overfit historical performance.

## Verification

Run `./run_tests.sh`. Numerical regressions cover self-financing fees, two-sided turnover, Sharpe, initial drawdown, invalid data, complete horizon enforcement, benchmark date alignment, cash-sensitive scenarios/VaR, position ceilings, provider replacement, news provenance and chart normalization. A full portfolio-generation integration test rejects nonfinite JSON. Tests use deterministic local data and do not prove live-data quality or profitable performance.
