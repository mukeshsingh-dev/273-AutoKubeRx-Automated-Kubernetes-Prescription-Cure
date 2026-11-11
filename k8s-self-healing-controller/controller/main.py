"""Kubernetes entrypoint for the Phase 2 controller.

This intentionally uses a polling loop for the first implementation.  It is
simple to run locally and keeps reconciliation idempotent; a watch-based
queue can replace the polling loop in a later hardening phase.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .reconciler import reconcile_snapshot, service_needs_update


GROUP = "ops.example.com"
VERSION = "v1alpha1"
PLURAL = "selfhealingworkloads"
LOGGER = logging.getLogger("self-healing-controller")


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler.
        if self.path in ("/healthz", "/readyz"):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"ok\n")
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, format: str, *args: Any) -> None:
        LOGGER.info("health %s", format % args)


def start_health_server() -> ThreadingHTTPServer:
    port = int(os.getenv("HEALTH_PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), HealthHandler)
    threading.Thread(target=server.serve_forever, name="health-server", daemon=True).start()
    return server


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


def reconcile_loop(custom_api: Any, apps_api: Any, core_api: Any, namespace: str, interval: float) -> None:
    while True:
        try:
            resources = custom_api.list_namespaced_custom_object(GROUP, VERSION, namespace, PLURAL)
            for workload in resources.get("items", []):
                try:
                    reconcile_one(custom_api, apps_api, core_api, workload)
                except Exception:
                    LOGGER.exception("reconcile failed for %s/%s", namespace, workload.get("metadata", {}).get("name"))
        except Exception:
            # A temporary API outage should not terminate the controller pod;
            # the next loop retries the read and reconciliation.
            LOGGER.exception("controller poll failed for namespace %s", namespace)
        time.sleep(interval)


def run() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    try:
        from kubernetes import client, config
    except ImportError as exc:
        raise SystemExit("Install dependencies with: python3 -m pip install -r requirements.txt") from exc

    try:
        config.load_incluster_config()
        LOGGER.info("loaded in-cluster Kubernetes configuration")
    except config.ConfigException:
        config.load_kube_config()
        LOGGER.info("loaded local Kubernetes configuration")
    custom_api = client.CustomObjectsApi()
    apps_api = client.AppsV1Api()
    core_api = client.CoreV1Api()
    namespace = os.getenv("WATCH_NAMESPACE", "self-healing-demo")
    interval = float(os.getenv("RECONCILE_INTERVAL_SECONDS", "5"))

    start_health_server()
    LOGGER.info("watching namespace=%s interval=%ss", namespace, interval)
    reconcile_loop(custom_api, apps_api, core_api, namespace, interval)


if __name__ == "__main__":
    run()

