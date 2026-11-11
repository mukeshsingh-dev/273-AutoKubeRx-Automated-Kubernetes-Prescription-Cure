# Phase 4 integration and hardening status

Status: implemented locally; live-cluster validation requires Docker, kind, and kubectl.

## Completed

- Added a production-style controller image with a non-root runtime user.
- Added namespace-scoped RBAC for the custom resource, status, Deployments, and Services.
- Added a Kubernetes Deployment with readiness and liveness probes.
- Added `/healthz` and `/readyz` endpoints for cluster health checks.
- Added in-cluster configuration with local kubeconfig fallback.
- Added per-workload error isolation and retry-on-next-poll behavior so one bad resource or temporary API outage does not terminate the controller.
- Added a deterministic local validation path that runs all unit tests and parses every YAML manifest.

## Integration runbook

```bash
kind create cluster --name self-healing-demo
kubectl apply -f deploy/namespace.yaml
kubectl apply -f deploy/crd.yaml
docker build -t autokuberx/self-healing-controller:dev .
kind load docker-image autokuberx/self-healing-controller:dev --name self-healing-demo
kubectl apply -f deploy/controller-rbac.yaml
kubectl apply -f deploy/controller-deployment.yaml
kubectl apply -f deploy/sample-workload.yaml
kubectl -n self-healing-demo rollout status deploy/self-healing-controller
kubectl -n self-healing-demo get selfhealingworkload,deploy,pods
kubectl -n self-healing-demo get selfhealingworkload worker-demo -o yaml
```

## Acceptance checks

1. The controller pod becomes Ready and remains running after a temporary API error.
2. Applying `spec.replicas: 5` causes the worker Deployment to converge to five replicas.
3. Deleting a worker pod causes the Deployment to create a replacement.
4. The custom resource reports `Available=True` when all desired replicas are ready.
5. The controller has no cluster-wide permissions; its Role is limited to the demo namespace.
