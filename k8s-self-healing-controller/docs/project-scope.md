# Project scope and acceptance criteria

## Problem

Distributed worker workloads can lose replicas, stall unfinished work, or fail without enough context for an operator to recover them quickly. The project delivers a Kubernetes controller that maintains worker health and an operations agent that explains failures from collected evidence.

## MVP scope

### In scope

- A `SelfHealingWorkload` custom resource with desired replicas, worker image, health probes, retry policy, and agent policy.
- Idempotent reconciliation of a worker Deployment.
- Detection of unavailable or unhealthy workers.
- Retry tracking for unfinished tasks.
- Evidence collection from Kubernetes events, logs, metrics, traces, health checks, and deployment history.
- Root-cause hypotheses and recommended recovery actions from the agent.
- Deterministic action guardrails with read, approval, and deny decisions.
- Audit records for evidence snapshots, model requests, decisions, and executed actions.

### Out of scope for the first MVP

- Autonomous destructive actions without approval.
- Multi-cluster failover.
- Production-grade model fine-tuning.
- Automatic remediation of arbitrary third-party workloads.

## Success criteria

1. Scaling the custom resource updates the desired worker replica count.
2. Deleting a worker pod results in the desired replica count being restored.
3. A failed task remains retryable and is not silently lost.
4. A diagnosis includes evidence references and a confidence or uncertainty note.
5. Cross-workload actions, over-limit refunds/changes, and unapproved mutations are denied or held for approval.
6. A demo operator can see current health, evidence, diagnosis, and action history from one interface.

## Phase 1 risks and decisions

- The controller must be idempotent because reconciliation may run repeatedly.
- Evidence must be time-bounded and correlated by workload, pod, task, and deployment revision.
- The agent may recommend actions, but a separate deterministic gate decides whether a tool call is allowed.
- The first demo uses kind or Minikube and a single namespace to keep the setup reproducible.

