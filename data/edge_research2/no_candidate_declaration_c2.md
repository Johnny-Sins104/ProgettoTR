# NO_CANDIDATE — Cycle 2 edge research declaration

Date: 2026-06-10 (UTC). Branch: `strat/edge-research-02`. Cycle 2 of a
declared maximum of 3. Machine-readable result:
`data/edge_research_report_c2.json` (`edge_demonstrated: false`).

## Verdict

**NO_CANDIDATE.** The shortlist after the regime-stratified eligibility
gate is **empty**, so the cycle-2 final-OOS (2025-02-24 → 2026-06-10)
was **never opened** and remains uncontaminated. Nothing is integrated
into the paper runner, no gate was lowered.

## What cycle 2 tested

- 6.4 years (2020-01 → 2026-06) of checksum-verified bulk data for the
  16 earliest Binance UM USDT perpetuals (point-in-time panel,
  survivorship-free: EOSUSDT ends at its 2025-05 delisting).
- 48 configurations in 4 families, declared with rationale before any
  validation metric; causal BTC SMA200 regime filter declared a priori
  and counted as parameters; cumulative trial log now at **84** distinct
  configurations (36 cycle 1 + 48 cycle 2).

## Why nothing reached the shortlist

The new gate required net-positivity in ≥ 2 distinct regimes
(bull/bear/chop, ≥ 10 validation trades each). The result is categorical:

| Family | Verdict on the multi-regime train/validation |
|---|---|
| volatility_breakout_c2 | 12/12 negative on train post-costs |
| trend_pullback_c2 | 12/12 deeply negative (worst: −15.9k R train) |
| xs_momentum_c2 (broad panel) | only XS211 positive on both splits, weak (val PF 1.06) |
| xs_momentum_regime_c2 (NEW) | best of cycle (XSR03 val PF 1.56; XSR04 1.39) |

**Every configuration with positive validation PnL earns it exclusively
in the bull regime.** Examples (validation, realistic costs):

- XSR04 (not_bear): bull +61.9 R (125 trades) / chop −3.2 R (27) / bear n/a → 1 regime
- XSR03 (bull_only): single-regime by construction → can never satisfy the gate
- XS211: bull +40.1 R (250) / bear −11.8 R (10) / chop −8.0 R (54) → 1 regime
- Best non-bull cell across all 48 configs: **negative everywhere**
  (chop and bear are net-negative for every config with ≥ 10 trades).

CSCV PBO on the cycle-2 panel: 0.408 (< 0.50 but far weaker than
cycle 1's 0.084, consistent with a thin, regime-bound signal).

## Cycle-3 verdict (required by the declared 3-cycle ceiling)

**A cycle 3 of this research program is NOT justified.** The failure is
structural, not marginal:

1. The binding gate is regime breadth, and no configuration is "close":
   the best non-bull regime result in 84 cumulative trials across two
   independent datasets is negative. There is no margin to close with
   more history or more symbols — both were already extended this cycle.
2. The only persistent signal found in two cycles is "long crypto
   momentum during bull regimes". Cycle 1 demonstrated empirically what
   that is worth out-of-sample when the regime turns (PF 0.89, net
   negative); a bull-only strategy's viability rests entirely on regime
   persistence, which is the exact failure mode already observed.
3. Post-costs, every intraday mean-reversion (pullback) and breakout
   family is dead on 6.4 years of data; the cost-to-edge ratio at 15m/5m
   with taker execution leaves no room.

**Honest conclusion: there is no extractable edge at our cost model on
these timeframes (15m signal / 5m execution) with these strategy
classes and this universe.** Re-running a third cycle with variations
of the same families would be number-hunting against the declared
methodology.

What could legitimately change this conclusion is a DIFFERENT research
program (new roadmap, new contract, fresh OOS), not a cycle 3: e.g.
maker-only execution economics, funding-rate carry, higher timeframes
(4h/1d), or regime-persistence modelling as the object of research
rather than a filter. Any such program must start from STRAT-01 again.

## Final-OOS status

- Cycle-1 OOS (2025-08-22 → 2026-06-10): burnt in cycle 1.
- Cycle-2 OOS (2025-02-24 → 2026-06-10): **never opened** (empty
  shortlist; `oos_access_log.json` does not exist). It remains valid
  for a future, differently-scoped research program.
