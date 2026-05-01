# EKS-Microservices-k8s-manifests

This project is a microservices-based architecture deployed on Amazon EKS, where external traffic is routed through an Application Load Balancer to Kubernetes Ingress and internal services. Each service is exposed via a ClusterIP service and runs on scalable deployments, with HPA applied to ms-live to handle dynamic user traffic efficiently. A dedicated batch job handles data migration tasks asynchronously without impacting live services. Redis is deployed separately (ideally as a StatefulSet with persistent storage) to support caching and fast data access. The system is designed for scalability, isolation, and high availability within a cloud-native environment.

## Services

| Service | Image Source | Port | Namespace | Notes |
|---|---|---|---|---|
| `ms-live` | ECR `backend/main-server:latest` | 8080 | `backend` | Main API server. HPA: min 4, max 6 replicas |
| `ms-livewebsocket` | GCR `ms-server_websocket:latest` | 443 | `backend` | WebSocket server. Legacy GCR image |
| `ms-integration` | ECR `backend/integrations:latest` | 443 | `backend` | Accounting/integrations. 2 vCPU, 4 GB |
| `ms-sandbox-smsemail` | ECR `backend/sms-email-notifications-server:latest` | 8585 | `backend` | SMS and email notifications (sandbox) |
| `ms-data-migration` | ECR `backend/data-migration:latest` | 443 | `backend` | Batch job. 16 vCPU, 32 GB requested |
| `redis-deployment` | `redis:latest` | 6379 | `redis` | 

## Architecture

```
ALB/NLB
   |
   +---> ms-live (HPA 4-6)
   +---> ms-livewebsocket
   +---> ms-integration
   +---> ms-sandbox-smsemail
         |
         +---> redis (ClusterIP, ns=redis)

ms-data-migration (batch, isolated)

ECR (eu-west-2) <--- ecr.py inventory helper
```

## Stack

Kubernetes (apps/v1) · Spring Boot Actuator · AWS ECR · EKS (eu-west-2) · Redis · Python 3 · boto3

## Repository Layout

```
eks-microservices-k8s-manifests/
├── ms-live/
│   ├── kubernetes.yaml         # Deployment
│   ├── service.yaml
│   └── hpa.yaml                # HPA min 4 / max 6
├── ms-server_websocket-master/
│   ├── kubernetes.yaml
│   ├── service.yaml
│   └── servicehttp.yaml        # LoadBalancer + nodePort 32265
├── accounting-master/
│   ├── kubernetes.yaml         # 2 vCPU / 4 GB
│   └── service.yaml
├── ms-smsemail-master/
│   └── kubernetes-sandbox/
│       └── kubernetes.yaml     # Slack token via secretKeyRef
├── kubernetes-data-migration-sandbox/
│   ├── kubernetes.yaml         # 16 vCPU / 32 GB
│   └── service.yaml
├── redis-deployments/
│   ├── deployment.yaml
│   └── service.yaml
├── python-scripts-for-automation/
│   └── ecr.py                  # Paginates all ECR repos and prints image references
├── .gitignore
└── README.md
```

## Deployment

Apply a service:

```bash
kubectl apply -f <service-folder>/kubernetes.yaml
kubectl apply -f <service-folder>/service.yaml
```

For `ms-live`, also apply the HPA:

```bash
kubectl apply -f ms-live/hpa.yaml
```

Create the Slack secret required by `ms-sandbox-smsemail` before applying that deployment:

```bash
kubectl -n backend create secret generic slack-secrets \
  --from-literal=bot-token="$SLACK_BOT_TOKEN"
```

## ECR Inventory (`ecr.py`)

Paginates all ECR repositories in the region and prints a ready-to-use image reference for each tag:

```
<repo>.dkr.ecr.eu-west-2.amazonaws.com/<repo>:<tag>
```

Copy the output line directly into the `image:` field of a Deployment manifest.

## Prerequisites

- `kubectl` pointed at the target cluster with RBAC access to `backend` and `redis` namespaces
- Python 3 with `boto3` installed (for `ecr.py`)
- Node group with sufficient capacity for `ms-data-migration` (16 vCPU / 32 GB) or the pod will remain `Pending`

## Notes

- All deployments use `RollingUpdate` with `/actuator/health` liveness and readiness probes, and a `preStop` sleep (20-60s) for graceful connection drain.
- `accounting-master` uses `maxSurge: 100% / maxUnavailable: 100%`, which behaves as a recreate strategy. Acceptable for stateless background processors, not suitable for live-traffic services.
- `ms-livewebsocket` still pulls from GCR. Migration to ECR is recommended for registry consolidation.
- HPA on `ms-live` uses `targetAverageUtilization: 350%`, which reflects underprovisioned CPU requests relative to actual usage. Requests should be rebaselined before adjusting the HPA threshold.
- `autoscaling/v2beta1` is removed in Kubernetes 1.26. Migrate the HPA manifest to `autoscaling/v2` before upgrading the cluster.
