# NO_CANDIDATE — Edge research declaration (STRAT-01 → STRAT-03)

Date: 2026-06-10 (UTC). Branch: `strat/edge-research-01`.
Authoritative machine-readable result: `data/edge_research_report.json`
(`edge_demonstrated: false`). Final-OOS opened exactly once
(`data/edge_research/oos_access_log.json`); re-running phase 4 is refused
by construction.

## Verdict

**NO_CANDIDATE.** Neither shortlisted configuration survives the final
out-of-sample gates post-costs. Nothing is integrated into the paper
runner. No gate was lowered, no configuration was added after the
declaration, no trade-count target was optimised.

## Shortlist outcome on final-OOS (2025-08-22 → 2026-06-10, realistic costs)

### XS04 — xs_momentum (3d formation, 3d hold, long-only), hash c82d1ad00543a60c

| Gate | Threshold | Observed | Margin |
|---|---|---|---|
| trades >= 50 | 50 | 98 | +48 PASS |
| profit factor > 1.20 | 1.20 | 0.890 | -0.310 FAIL |
| net PnL > 0 | 0 | -54.67 | -54.67 FAIL |
| max drawdown <= 15% | 15% | 22.99% | -7.99 pt FAIL |
| DSR >= 0.95 (36 trials) | 0.95 | 0.014 | -0.936 FAIL |
| PBO < 0.50 | 0.50 | 0.084 | +0.416 PASS |
| severe scenario > 0 | 0 | -159.39 | FAIL |
| top-3 trades <= 35% gross profit | 0.35 | 0.589 | -0.239 FAIL |
| best-month-removed PnL > 0 | 0 | -160.63 | FAIL |
| no OOS contamination | — | certified | PASS |

### XS08 — xs_momentum (7d formation, 3d hold, long-only), hash f709f5388599a588

| Gate | Threshold | Observed | Margin |
|---|---|---|---|
| trades >= 50 | 50 | 98 | +48 PASS |
| profit factor > 1.20 | 1.20 | 0.886 | -0.314 FAIL |
| net PnL > 0 | 0 | -50.91 | -50.91 FAIL |
| max drawdown <= 15% | 15% | 15.58% | -0.58 pt FAIL |
| DSR >= 0.95 (36 trials) | 0.95 | 0.009 | -0.941 FAIL |
| PBO < 0.50 | 0.50 | 0.084 | +0.416 PASS |
| severe scenario > 0 | 0 | -156.22 | FAIL |
| top-3 trades <= 35% gross profit | 0.35 | 0.415 | -0.065 FAIL |
| best-month-removed PnL > 0 | 0 | -103.78 | FAIL |
| no OOS contamination | — | certified | PASS |

The decisive failure for both is the sign of the OOS edge itself
(PF ≈ 0.89, negative net PnL): the validation-period profitability
(Nov 2024 – Aug 2025) did not persist into the OOS regime. The low PBO
(0.084) and the passed plateau/walk-forward checks show this was not a
classic single-optimum overfit; it is a genuine regime dependence that
the validation window could not falsify and the final-OOS did.

## Family proximity to thresholds

1. **xs_momentum** — closest. Train and validation positive on 4/12
   configs, severe-scenario positive on validation, plateau coherent.
   Failed only at the final-OOS regime shift.
2. **volatility_breakout** — distant. Only VB12 positive on both splits,
   with validation drawdown (22%) already beyond eligibility.
3. **trend_pullback** — dead. 12/12 configurations negative on both
   train and validation post-costs.

## Justified extensions (for a future, separately authorised iteration)

- **More history, not more configs:** Binance Futures public klines cap
  this dataset at ~4y by request pagination; bulk monthly archives
  (data.binance.vision) would extend BTC/ETH to 2019+ and add at least
  one full bear/bull cycle to train, making the walk-forward folds less
  regime-lopsided.
- **Regime-conditional cross-sectional momentum** (e.g. only when the
  panel's aggregate trend filter is on) is the only economically
  motivated refinement suggested by the fold structure — it would be a
  NEW declared family in a NEW research cycle with a fresh OOS, since
  this final-OOS is now burnt for the XS family.
- A wider asset panel (10–15 perpetuals) would raise cross-sectional
  breadth, the main statistical weakness of a 5-asset ranking.

## What does NOT follow from this result

- No integration into the clean paper runner.
- No relaxation of any gate.
- No reuse of the 2025-08-22 → 2026-06-10 final-OOS for any further
  selection on these families.
