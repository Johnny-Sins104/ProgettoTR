# PROMPT 29.4.4 — Conservative paper-only shadow-to-paper unlock gate

## Scope

This patch converts the best shadow profile from Prompt 29.4.3 into a controlled paper-only entry gate.
It does not change the core `DecisionEngine` thresholds and does not enable live or testnet execution.

Initial controlled profile:

```text
BTC_ONLY_40_Q60
```

Rules:

```text
symbol allowlist: BTC/USDT
accepted diagnostic filter: META_PROB_LOW
minimum AI probability: 40.0
minimum setup quality: 60.0
technical gate: unchanged / required
unlock max positions: 1
risk per trade: unchanged
cost model: unchanged
live/testnet: blocked
```

## Files changed

```text
.env.example
docs/patch_reports/PROMPT_29_4_4_PATCH_REPORT.md
trading_bot/config.py
trading_bot/run_paper_trading.py
trading_bot/core/paper_engine.py
trading_bot/core/paper_performance.py
trading_bot/core/paper_shadow_simulation.py
trading_bot/core/paper_unlock_gate.py
```

## New config

```env
PAPER_ENTRY_UNLOCK_ENABLED=0
PAPER_UNLOCK_PROFILE=BTC_ONLY_40_Q60
PAPER_UNLOCK_ALLOWED_SYMBOLS=BTC/USDT
PAPER_UNLOCK_ALLOWED_FILTERS=META_PROB_LOW
PAPER_UNLOCK_MIN_AI_PROB=40.0
PAPER_UNLOCK_MIN_SETUP_QUALITY=60.0
PAPER_UNLOCK_REQUIRE_TECH_GATE=1
PAPER_UNLOCK_MAX_POSITIONS=1
PAPER_UNLOCK_LIVE_BLOCK=1
PAPER_UNLOCK_TAG=PAPER_UNLOCK_29_4_4
```

`PAPER_ENTRY_UNLOCK_ENABLED` remains off by default.

## Runtime behavior

When enabled, the engine evaluates rejected paper diagnostics. If a diagnostic satisfies the `BTC_ONLY_40_Q60` profile, it emits:

```text
PAPER_UNLOCK_EVALUATED
PAPER_UNLOCK_SIGNAL
SIGNAL_DETECTED
PAPER_ORDER_SUBMITTED
ORDER_FILLED
POSITION_OPENED
```

The order metadata includes:

```text
paper_unlock=true
unlock_profile=BTC_ONLY_40_Q60
unlock_tag=PAPER_UNLOCK_29_4_4
```

Telegram sends:

```text
PAPER UNLOCK SIGNAL
PAPER ORDER FILLED
PAPER POSITION OPENED
PAPER POSITION MONITOR
```

## Safety guarantees

```text
live execution remains disabled
ExchangeBrokerAdapter remains BLOCKED_DESIGN_STUB
no API secrets are required
no live/testnet order path is added
risk per trade is unchanged
max unlock positions is capped to 1
unlock is paper-only and opt-in
```

## Validation

Static validation performed:

```text
python -m py_compile trading_bot/config.py
python -m py_compile trading_bot/run_paper_trading.py
python -m py_compile trading_bot/core/paper_engine.py
python -m py_compile trading_bot/core/paper_unlock_gate.py
python -m py_compile trading_bot/core/paper_shadow_simulation.py
python -m py_compile trading_bot/core/paper_performance.py
```

A unit smoke test of `evaluate_paper_unlock()` accepted a BTC/USDT META_PROB_LOW diagnostic with `ai_prob=44.4`, `setup_quality=86.6`, `technical_score=-61`, and rejected ETH/USDT under the BTC-only profile.

Full runtime was not executed in the sandbox because `ccxt` is not installed there.
