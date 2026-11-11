import unittest

from controller.agent import diagnose
from controller.guardrails import authorize


class AgentAndGuardrailTests(unittest.TestCase):
    def test_diagnosis_links_replica_deficit_to_recovery_recommendation(self):
        result = diagnose({"health": {"desiredReplicas": 3, "readyReplicas": 2}})

        self.assertEqual(result["recommendedAction"], "restart_worker")
        self.assertIn("health.readyReplicas", result["evidence"])
        self.assertGreater(result["confidence"], 0.0)

    def test_read_only_action_is_allowed_without_approval(self):
        decision = authorize("get_status", "worker-demo", "worker-demo", "self-healing-demo", "self-healing-demo")

        self.assertTrue(decision.allowed)
        self.assertFalse(decision.requires_approval)

    def test_recovery_action_waits_for_approval(self):
        decision = authorize("restart_worker", "worker-demo", "worker-demo", "self-healing-demo", "self-healing-demo")

        self.assertFalse(decision.allowed)
        self.assertTrue(decision.requires_approval)

    def test_cross_namespace_action_is_denied_even_with_approval(self):
        decision = authorize("restart_worker", "worker-demo", "worker-demo", "other", "self-healing-demo", approval=True)

        self.assertFalse(decision.allowed)
        self.assertFalse(decision.requires_approval)


if __name__ == "__main__":
    unittest.main()
