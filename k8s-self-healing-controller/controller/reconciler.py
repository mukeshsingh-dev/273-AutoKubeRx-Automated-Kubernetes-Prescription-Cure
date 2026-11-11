"""Pure reconciliation logic for SelfHealingWorkload resources.

The functions in this module do not require a Kubernetes connection.  They
turn a custom resource and observed Deployment state into deterministic
Kubernetes objects and a status document, which makes the controller behavior
easy to test before it is connected to a cluster.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


API_VERSION = "ops.example.com/v1alpha1"
KIND = "SelfHealingWorkload"
APP_LABEL = "app.kubernetes.io/name"
PART_OF_LABEL = "app.kubernetes.io/part-of"
CONTROLLER_NAME = "self-healing-controller"


def _metadata(workload: dict[str, Any]) -> dict[str, Any]:
    return workload.get("metadata", {})


def _spec(workload: dict[str, Any]) -> dict[str, Any]:
    return workload.get("spec", {})


def _name(workload: dict[str, Any]) -> str:
    return _metadata(workload).get("name", "")


def _namespace(workload: dict[str, Any]) -> str:
    return _metadata(workload).get("namespace", "default")


def labels_for(workload: dict[str, Any]) -> dict[str, str]:
    name = _name(workload)
    return {
        APP_LABEL: name,
        PART_OF_LABEL: CONTROLLER_NAME,
    }


def selector_labels_for(workload: dict[str, Any]) -> dict[str, str]:
    """Return immutable, minimal selector labels for Deployment and Service."""

    return {APP_LABEL: _name(workload)}


def owner_reference(workload: dict[str, Any]) -> dict[str, Any] | None:
    metadata = _metadata(workload)
    uid = metadata.get("uid")
    if not uid:
        return None
    return {
        "apiVersion": API_VERSION,
        "kind": KIND,
        "name": _name(workload),
        "uid": uid,
        "controller": True,
        "blockOwnerDeletion": True,
    }


def build_deployment(workload: dict[str, Any]) -> dict[str, Any]:
    """Build the desired worker Deployment from the custom resource."""

    spec = _spec(workload)
    labels = labels_for(workload)
    selector_labels = selector_labels_for(workload)
    owner = owner_reference(workload)
    deployment_metadata: dict[str, Any] = {
        "name": _name(workload),
        "namespace": _namespace(workload),
        "labels": labels,
        "annotations": {"ops.example.com/managed-by": CONTROLLER_NAME},
    }
    if owner:
        deployment_metadata["ownerReferences"] = [owner]

    port = int(spec.get("port", 80))
    image = spec["image"]
    template_labels = deepcopy(labels)
    container = {
        "name": "worker",
        "image": image,
        "ports": [{"name": "http", "containerPort": port}],
        "readinessProbe": {
            "httpGet": {"path": "/", "port": "http"},
            "initialDelaySeconds": 2,
            "periodSeconds": 5,
        },
        "livenessProbe": {
            "httpGet": {"path": "/", "port": "http"},
            "initialDelaySeconds": 5,
            "periodSeconds": 10,
        },
    }
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": deployment_metadata,
        "spec": {
            "replicas": int(spec["replicas"]),
            "selector": {"matchLabels": selector_labels},
            "template": {
                "metadata": {"labels": template_labels},
                "spec": {"containers": [container]},
            },
        },
    }


def build_service(workload: dict[str, Any]) -> dict[str, Any]:
    """Build the stable Service used to reach worker replicas."""

    spec = _spec(workload)
    labels = labels_for(workload)
    selector_labels = selector_labels_for(workload)
    owner = owner_reference(workload)
    metadata: dict[str, Any] = {
        "name": _name(workload),
        "namespace": _namespace(workload),
        "labels": labels,
    }
    if owner:
        metadata["ownerReferences"] = [owner]
    port = int(spec.get("port", 80))
    return {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": metadata,
        "spec": {
            "selector": selector_labels,
            "ports": [{"name": "http", "port": port, "targetPort": "http"}],
        },
    }


def _condition(condition_type: str, status: str, reason: str, message: str) -> dict[str, str]:
    return {
        "type": condition_type,
        "status": status,
        "reason": reason,
        "message": message,
    }


def build_status(workload: dict[str, Any], ready_replicas: int) -> dict[str, Any]:
    """Build status while preserving the controller's observable contract."""

    desired = int(_spec(workload)["replicas"])
    ready = max(0, int(ready_replicas))
    if ready >= desired:
        condition = _condition(
            "Available", "True", "ReadyReplicas", f"{ready}/{desired} replicas are ready"
        )
    elif ready == 0:
        condition = _condition(
            "Degraded", "True", "NoReadyReplicas", f"0/{desired} replicas are ready"
        )
    else:
        condition = _condition(
            "Degraded", "True", "InsufficientReadyReplicas", f"{ready}/{desired} replicas are ready"
        )
    return {
        "desiredReplicas": desired,
        "readyReplicas": ready,
        "conditions": [condition],
    }


def deployment_needs_update(existing: dict[str, Any] | None, desired: dict[str, Any]) -> bool:
    """Compare only fields controlled by this controller."""

    if not existing:
        return True
    existing_spec = existing.get("spec", {})
    desired_spec = desired["spec"]
    if existing_spec.get("replicas") != desired_spec["replicas"]:
        return True
    existing_container = existing_spec.get("template", {}).get("spec", {}).get("containers", [{}])[0]
    desired_container = desired_spec["template"]["spec"]["containers"][0]
    return any(
        existing_container.get(field) != desired_container.get(field)
        for field in ("image", "ports", "readinessProbe", "livenessProbe")
    )


def service_needs_update(existing: dict[str, Any] | None, desired: dict[str, Any]) -> bool:
    """Return whether the controller-owned Service spec is stale."""

    if not existing:
        return True
    return existing.get("spec", {}) != desired.get("spec", {})


def reconcile_snapshot(
    workload: dict[str, Any],
    existing_deployment: dict[str, Any] | None,
    ready_replicas: int,
) -> dict[str, Any]:
    """Return the desired objects and status for one idempotent reconcile."""

    desired_deployment = build_deployment(workload)
    desired_service = build_service(workload)
    return {
        "deployment": desired_deployment,
        "service": desired_service,
        "status": build_status(workload, ready_replicas),
        "deploymentChanged": deployment_needs_update(existing_deployment, desired_deployment),
    }

