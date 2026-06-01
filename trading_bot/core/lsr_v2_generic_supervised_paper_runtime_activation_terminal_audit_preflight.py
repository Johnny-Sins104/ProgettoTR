"""Compatibility wrapper for 29.4.4u-65 runtime activation terminal audit preflight."""

from __future__ import annotations

from core.lsr_v2_generic_supervised_paper_runtime_activation_terminal_audit_bundle import (
    PREFLIGHT_READY_DECISION as READY_DECISION,
    Settings,
    run_generic_supervised_paper_runtime_activation_terminal_audit_preflight,
)

__all__ = [
    "READY_DECISION",
    "Settings",
    "run_generic_supervised_paper_runtime_activation_terminal_audit_preflight",
]
