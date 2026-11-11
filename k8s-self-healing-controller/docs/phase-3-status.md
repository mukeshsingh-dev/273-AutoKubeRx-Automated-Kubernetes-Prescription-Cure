# Phase 3 evidence, agent, and guardrail status

Status: implemented locally

## Completed

- Added bounded workload-scoped collection for Deployment state, pods, events, and tail-limited logs.
- Represented missing metrics and traces explicitly as unavailable instead of silently treating them as healthy.
- Added evidence-linked conservative diagnosis with confidence and uncertainty fields.
- Added a deterministic action gate for read-only actions, approval-required recovery actions, unknown actions, and cross-namespace access.
- Added tests covering diagnosis and each guardrail decision path.

The agent recommends actions only. A separate deterministic gate must authorize
any recovery tool call, and Phase 4 does not enable autonomous destructive
actions.
