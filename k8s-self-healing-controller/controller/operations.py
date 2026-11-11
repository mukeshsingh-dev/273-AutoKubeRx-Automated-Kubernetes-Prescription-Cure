"""Operations facade connecting evidence, diagnosis, guardrails, and actions."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .agent import diagnose
from .evidence import collect_evidence
from .guardrails import Decision, authorize
from .retry import TaskRetryTracker


class OperationsService:
    """Single entry point for administrator and agent operations.

    The service records every decision in memory for the Phase 3/4 demo. The
    controller can later replace this audit sink with a Kubernetes Event or a
    durable database without changing the authorization boundary.
    """

    def __init__(self, custom_api: Any, core_api: Any, apps_api: Any, retry_tracker: TaskRetryTracker | None = None) -> None:
        self.custom_api = custom_api
        self.core_api = core_api
        self.apps_api = apps_api
        self.retry_tracker = retry_tracker or TaskRetryTracker()
        self.audit_log: list[dict[str, Any]] = []

    def diagnose_workload(self, workload: dict[str, Any]) -> dict[str, Any]:
        evidence = collect_evidence(self.core_api, self.apps_api, workload)
        result = diagnose(evidence)
        result["workload"] = {
            "name": workload["metadata"]["name"],
            "namespace": workload["metadata"].get("namespace", "default"),
        }
        result["collectedAt"] = evidence["collectedAt"]
        return {"evidence": evidence, "diagnosis": result}

    def request_action(
        self,
        workload: dict[str, Any],
        action: str,
        approval: bool = False,
        task_id: str | None = None,
        requested_namespace: str | None = None,
    ) -> dict[str, Any]:
        metadata = workload["metadata"]
        spec = workload.get("spec", {})
        namespace = metadata.get("namespace", "default")
        name = metadata["name"]
        decision: Decision = authorize(
            action,
            name,
            name,
            requested_namespace or namespace,
            namespace,
            require_approval=spec.get("agentPolicy", {}).get("requireApprovalForRecovery", True),
            approval=approval,
        )
        audit = {
            "at": datetime.now(timezone.utc).isoformat(),
            "workload": f"{namespace}/{name}",
            "action": action,
            "allowed": decision.allowed,
            "requiresApproval": decision.requires_approval,
            "reason": decision.reason,
        }
        self.audit_log.append(audit)
        result: dict[str, Any] = {"decision": decision, "audit": audit}
        if not decision.allowed:
            return result

        if action == "get_status":
            result["output"] = self.diagnose_workload(workload)
        elif action == "restart_worker":
            result["output"] = self._restart_one_worker(workload)
        elif action == "scale_workload":
            result["output"] = {"status": "approved; use the controller reconcile loop to apply the requested scale"}
        elif action == "retry_task":
            if not task_id:
                result["output"] = {"status": "rejected", "reason": "task_id is required"}
            else:
                result["output"] = {"task": self.retry_tracker.mark_success(task_id).__dict__}
        return result

    def _restart_one_worker(self, workload: dict[str, Any]) -> dict[str, Any]:
        namespace = workload["metadata"].get("namespace", "default")
        name = workload["metadata"]["name"]
        pods = self.core_api.list_namespaced_pod(namespace, label_selector=f"app.kubernetes.io/name={name}")
        items = getattr(pods, "items", [])
        if not items:
            return {"status": "no-op", "reason": "no worker pod found"}
        pod_name = getattr(getattr(items[0], "metadata", None), "name", None)
        if not pod_name:
            return {"status": "no-op", "reason": "worker pod had no name"}
        self.core_api.delete_namespaced_pod(pod_name, namespace)
        return {"status": "accepted", "deletedPod": pod_name}
