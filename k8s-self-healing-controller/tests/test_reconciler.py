import unittest

from controller.reconciler import (
    build_deployment,
    build_service,
    build_status,
    deployment_needs_update,
    reconcile_snapshot,
    service_needs_update,
)


def workload(replicas=3, image="nginx:1.27", port=80):
    return {
        "apiVersion": "ops.example.com/v1alpha1",
        "kind": "SelfHealingWorkload",
        "metadata": {
            "name": "worker-demo",
            "namespace": "self-healing-demo",
            "uid": "demo-uid",
        },
        "spec": {"replicas": replicas, "image": image, "port": port},
    }


class ReconcilerTests(unittest.TestCase):
    def test_create_builds_owned_deployment_and_service(self):
        desired = build_deployment(workload())
        service = build_service(workload())

        self.assertEqual(desired["spec"]["replicas"], 3)
        self.assertEqual(desired["spec"]["template"]["spec"]["containers"][0]["image"], "nginx:1.27")
        self.assertEqual(desired["metadata"]["ownerReferences"][0]["uid"], "demo-uid")
        self.assertEqual(service["spec"]["selector"]["app.kubernetes.io/name"], "worker-demo")

    def test_scale_changes_replica_count(self):
        old = build_deployment(workload(replicas=3))
        new = build_deployment(workload(replicas=5))

        self.assertTrue(deployment_needs_update(old, new))
        self.assertEqual(new["spec"]["replicas"], 5)

    def test_pod_loss_is_reported_as_degraded_until_replacement_is_ready(self):
        degraded = build_status(workload(replicas=3), ready_replicas=2)
        recovered = build_status(workload(replicas=3), ready_replicas=3)

        self.assertEqual(degraded["conditions"][0]["type"], "Degraded")
        self.assertEqual(recovered["conditions"][0]["type"], "Available")

    def test_unhealthy_workers_do_not_change_desired_replicas(self):
        snapshot = reconcile_snapshot(workload(replicas=3), None, ready_replicas=0)

        self.assertEqual(snapshot["deployment"]["spec"]["replicas"], 3)
        self.assertEqual(snapshot["status"]["conditions"][0]["reason"], "NoReadyReplicas")

    def test_reconcile_is_idempotent(self):
        first = reconcile_snapshot(workload(), None, ready_replicas=3)
        second = reconcile_snapshot(workload(), first["deployment"], ready_replicas=3)

        self.assertTrue(first["deploymentChanged"])
        self.assertFalse(second["deploymentChanged"])
        self.assertEqual(first["status"], second["status"])

    def test_service_changes_when_worker_port_changes(self):
        old = build_service(workload(port=80))
        new = build_service(workload(port=8080))

        self.assertTrue(service_needs_update(old, new))


if __name__ == "__main__":
    unittest.main()

