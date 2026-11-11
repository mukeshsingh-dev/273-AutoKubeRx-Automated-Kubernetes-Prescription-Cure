"""Evidence-linked diagnosis and recovery recommendation layer."""

from __future__ import annotations

from typing import Any


def diagnose(evidence: dict[str, Any]) -> dict[str, Any]:
    """Return a conservative diagnosis; execution is delegated to guardrails."""

    health = evidence.get("health", {})
    desired = int(health.get("desiredReplicas", 0))
    ready = int(health.get("readyReplicas", 0))
    if desired and ready < desired:
        return {
            "summary": f"{desired - ready} worker replica(s) are unavailable",
            "likelyCause": "worker readiness or pod availability failure",
            "confidence": 0.85,
            "evidence": ["health.desiredReplicas", "health.readyReplicas", "events", "logs"],
            "recommendedAction": "restart_worker",
            "uncertainty": "Metrics and traces were not configured for this snapshot.",
        }
    return {
        "summary": "No replica deficit detected",
        "likelyCause": "no actionable failure observed in the bounded snapshot",
        "confidence": 0.60,
        "evidence": ["health.desiredReplicas", "health.readyReplicas"],
        "recommendedAction": "get_status",
        "uncertainty": "A healthy snapshot does not rule out intermittent or task-level failures.",
    }
