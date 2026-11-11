# Architecture and recovery flow

## Reconciliation flow

```mermaid
sequenceDiagram
  participant API as Kubernetes API
  participant C as Self-healing controller
  participant D as Worker Deployment
  participant A as Audit/status
  API->>C: Watch SelfHealingWorkload or worker event
  C->>C: Read desired state and observed state
  C->>D: Create or patch Deployment when state differs
  D-->>API: Report pod readiness and replica status
  C->>A: Record condition, reason, and observed replicas
```

## Agent-assisted diagnosis flow

```mermaid
flowchart TD
  Trigger[Admin asks for diagnosis] --> Collect[Collect bounded evidence]
  Collect --> Normalize[Normalize by workload and time window]
  Normalize --> Analyze[Agent proposes likely root cause]
  Analyze --> Recommend[Produce evidence-linked recommendation]
  Recommend --> Gate{Deterministic tool gate}
  Gate -->|Read-only| Execute[Execute and audit]
  Gate -->|Needs approval| Approve[Ask admin for approval]
  Gate -->|Unsafe or out of scope| Deny[Deny and explain]
  Approve --> Execute
```

## Custom resource design

The resource separates desired state (`spec`) from observed state (`status`). The controller owns status conditions and observed replica counts. The operations agent never writes directly to the resource without passing through the action gate.

### Status conditions

- `Available`: desired replicas are ready.
- `Degraded`: one or more replicas are unavailable or tasks are retrying.
- `Recovering`: a remediation is in progress.
- `Blocked`: policy, missing evidence, or approval prevents remediation.

