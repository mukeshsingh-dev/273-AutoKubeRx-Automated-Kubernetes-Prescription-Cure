import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from controller.operations import OperationsService
from controller.retry import TaskRetryTracker


WORKLOAD = {
    "metadata": {"name": "worker-demo", "namespace": "self-healing-demo"},
    "spec": {
        "replicas": 1,
        "image": "nginx:1.27",
        "agentPolicy": {"requireApprovalForRecovery": True},
    },
}


class FakeCore:
    def __init__(self):
        self.deleted = []

    def list_namespaced_pod(self, namespace, label_selector):
        return SimpleNamespace(items=[SimpleNamespace(metadata=SimpleNamespace(name="worker-pod"))])

    def read_namespaced_pod_log(self, *args, **kwargs):
        return "worker healthy"

    def list_namespaced_event(self, namespace):
        return SimpleNamespace(items=[])

    def delete_namespaced_pod(self, name, namespace):
        self.deleted.append((name, namespace))


class FakeApps:
    def read_namespaced_deployment(self, name, namespace):
        return SimpleNamespace(status=SimpleNamespace(ready_replicas=1))

    def read_namespaced_deployment_status(self, name, namespace):
        return SimpleNamespace(status=SimpleNamespace(ready_replicas=1))


class OperationsTests(unittest.TestCase):
    def test_recovery_is_blocked_without_approval(self):
        service = OperationsService(object(), FakeCore(), FakeApps())

        result = service.request_action(WORKLOAD, "restart_worker")

        self.assertFalse(result["decision"].allowed)
        self.assertTrue(result["decision"].requires_approval)

    def test_approved_restart_deletes_one_worker_pod(self):
        core = FakeCore()
        service = OperationsService(object(), core, FakeApps())

        result = service.request_action(WORKLOAD, "restart_worker", approval=True)

        self.assertTrue(result["decision"].allowed)
        self.assertEqual(core.deleted, [("worker-pod", "self-healing-demo")])

    def test_retry_tracker_schedules_and_exhausts_failures(self):
        tracker = TaskRetryTracker()
        now = datetime(2026, 1, 1, tzinfo=timezone.utc)
        record = tracker.record_failure("task-1", "timeout", max_retries=2, backoff_seconds=10, now=now)

        self.assertEqual(record.attempts, 1)
        self.assertFalse(tracker.ready_for_retry("task-1", now))
        self.assertTrue(tracker.ready_for_retry("task-1", now + timedelta(seconds=10)))
        tracker.record_failure("task-1", "timeout", 2, 10, now=now)
        exhausted = tracker.record_failure("task-1", "timeout", 2, 10, now=now)
        self.assertEqual(exhausted.state, "exhausted")


if __name__ == "__main__":
    unittest.main()
