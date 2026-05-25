# Prompt 29.4.4c — Paper unlock profile refinement design

Diagnostic-only design patch after 29.5.0j.

## Scope

This patch drafts a paper-only profile specification from the independently validated `map_score_65_79_all` stability candidate. It does not activate the profile and does not change trading behavior.

## Added files

- `trading_bot/core/paper_unlock_profile_refinement.py`
- `trading_bot/run_paper_unlock_profile_refinement.py`
- `trading_bot/test_paper_unlock_profile_refinement.py`
- `data/paper_unlock_profile_refinement_report.json` generated locally by the runner

## Safety invariant

- No orders
- No live execution
- No testnet execution
- No paper unlock activation
- No risk increase
- No threshold mutation
- No automatic profile activation

## Candidate profile

`MAP_SCORE_65_79_REPAIRED_STABILITY_V1`

Source: 29.5.0j `map_score_65_79_all` stability candidate.

The report defines a profile spec, blocked states and next-patch requirements for a future paper-only experiment. WAIT, NO_STRUCTURE and CONFLICT rows remain blocked from entry.

## Next patch if locally validated

`29.4.4d — calibrated paper-only unlock experiment design`, still with live/testnet blocked.
