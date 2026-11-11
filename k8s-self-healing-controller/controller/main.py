"""Minimal Kubernetes entrypoint for the Phase 2 controller.

This intentionally uses a polling loop for the first implementation.  It is
simple to run locally and keeps reconciliation idempotent; a watch-based
queue can replace the polling loop in a later hardening phase.
"""

from __future__ import annotations

import os
import time
from typing import Any

from .reconciler import reconcile_snapshot, service_needs_update


GROUP = "ops.example.com"
VERSION = "v1alpha1"
PLURAL = "selfhealingworkloads"


def reconcile_one(custom_api: Any, apps_api: Any, core_api: Any, workload: dict[str, Any]) -> None:
    metadata = workload["metadata"]
    namespace = metadata.get("namespace", "default")
    name = metadata["name"]
    existing = None
    try:
        # Convert the client model to Kubernetes JSON field names before
        # comparing it with the desired manifest.
        from kubernetes import client

        existing_object = apps_api.read_namespaced_deployment(name, namespace)
        existing = client.ApiClient().sanitize_for_serialization(existing_object)
    except Exception as exc:  # Kubernetes client exceptions vary by version.
        if getattr(exc, "status", None) != 404:
            raise

    try:
        deployment = existing
        ready = getattr(
            apps_api.read_namespaced_deployment_status(name, namespace),
            "status",
            None,
        )
        ready_replicas = int(getattr(ready, "ready_replicas", 0) or 0)
    except Exception:
        ready_replicas = 0

    snapshot = reconcile_snapshot(workload, deployment, ready_replicas)
    desired_deployment = snapshot["deployment"]
    if snapshot["deploymentChanged"]:
        if existing is None:
            apps_api.create_namespaced_deployment(namespace, desired_deployment)
        else:
            apps_api.patch_namespaced_deployment(name, namespace, {"spec": desired_deployment["spec"]})

    existing_service = None
    try:
        from kubernetes import client

        existing_service_object = core_api.read_namespaced_service(name, namespace)
        existing_service = client.ApiClient().sanitize_for_serialization(existing_service_object)
    except Exception as exc:
        if getattr(exc, "status", None) != 404:
            raise
    if service_needs_update(existing_service, snapshot["service"]):
        if existing_service is None:
            core_api.create_namespaced_service(namespace, snapshot["service"])
        else:
            core_api.patch_namespaced_service(name, namespace, {"spec": snapshot["service"]["spec"]})

    custom_api.patch_namespaced_custom_object_status(
        GROUP,
        VERSION,
        namespace,
        PLURAL,
        name,
        {"status": snapshot["status"]},
    )


def run() -> None:
    try:
        from kubernetes import client, config
    except ImportError as exc:
        raise SystemExit("Install dependencies with: python3 -m pip install -r requirements.txt") from exc

    config.load_kube_config()
    custom_api = client.CustomObjectsApi()
    apps_api = client.AppsV1Api()
    core_api = client.CoreV1Api()
    namespace = os.getenv("WATCH_NAMESPACE", "self-healing-demo")
    interval = float(os.getenv("RECONCILE_INTERVAL_SECONDS", "5"))

    while True:
        resources = custom_api.list_namespaced_custom_object(GROUP, VERSION, namespace, PLURAL)
        for workload in resources.get("items", []):
            reconcile_one(custom_api, apps_api, core_api, workload)
        time.sleep(interval)


if __name__ == "__main__":
    run()

