"""Bounded operational evidence collection for a workload."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from .reconciler import APP_LABEL, _name, _namespace, build_status


def _safe_call(function: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    try:
        return function(*args, **kwargs)
    except Exception as exc:  # Evidence is best-effort; diagnosis must retain the failure.
        return {"error": str(exc)}


def collect_evidence(
    core_api: Any,
    apps_api: Any,
    workload: dict[str, Any],
    log_tail_lines: int = 100,
) -> dict[str, Any]:
    """Collect a bounded, workload-scoped evidence snapshot.

    Metrics and traces are represented explicitly as unavailable until those
    integrations are configured. This prevents the agent from treating absent
    evidence as proof that the system is healthy.
    """

    namespace = _namespace(workload)
    name = _name(workload)
    selector = f"{APP_LABEL}={name}"
    deployment = _safe_call(apps_api.read_namespaced_deployment, name, namespace)
    pods = _safe_call(core_api.list_namespaced_pod, namespace, label_selector=selector)
    events = _safe_call(core_api.list_namespaced_event, namespace)

    pod_items = getattr(pods, "items", []) if not isinstance(pods, dict) else []
    logs: dict[str, Any] = {}
    for pod in pod_items:
        pod_name = getattr(getattr(pod, "metadata", None), "name", "unknown")
        logs[pod_name] = _safe_call(
            core_api.read_namespaced_pod_log,
            pod_name,
            namespace,
            tail_lines=log_tail_lines,
        )

    desired = int(workload.get("spec", {}).get("replicas", 0))
    ready = int(getattr(getattr(deployment, "status", None), "ready_replicas", 0) or 0)
    status = build_status(workload, ready) if desired else {}
    return {
        "collectedAt": datetime.now(timezone.utc).isoformat(),
        "workload": {"name": name, "namespace": namespace},
        "deployment": deployment,
        "pods": pod_items,
        "events": events,
        "logs": logs,
        "health": {"desiredReplicas": desired, "readyReplicas": ready, "status": status},
        "metrics": {"available": False, "reason": "metrics adapter not configured"},
        "traces": {"available": False, "reason": "tracing adapter not configured"},
    }
