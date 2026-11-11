"""Deterministic authorization gate for agent tool calls."""

from __future__ import annotations

from dataclasses import dataclass


READ_ONLY_ACTIONS = frozenset({"get_status", "list_events", "read_logs", "read_metrics", "read_traces"})
RECOVERY_ACTIONS = frozenset({"restart_worker", "scale_workload", "retry_task"})


@dataclass(frozen=True)
class Decision:
    allowed: bool
    requires_approval: bool
    reason: str


def authorize(
    action: str,
    target_workload: str,
    requested_workload: str,
    requested_namespace: str,
    workload_namespace: str,
    require_approval: bool = True,
    approval: bool = False,
) -> Decision:
    """Authorize one operation without trusting natural-language agent output."""

    if target_workload != requested_workload or requested_namespace != workload_namespace:
        return Decision(False, False, "cross-workload or cross-namespace access denied")
    if action in READ_ONLY_ACTIONS:
        return Decision(True, False, "read-only evidence action allowed")
    if action not in RECOVERY_ACTIONS:
        return Decision(False, False, "unknown action denied")
    if require_approval and not approval:
        return Decision(False, True, "recovery action requires explicit administrator approval")
    return Decision(True, False, "approved recovery action allowed")
