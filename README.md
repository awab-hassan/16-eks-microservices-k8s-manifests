# MS Platform — Kubernetes Manifests + MySQL RDS + ECR Audit

The consolidated deployment monorepo for the **MS platform** — a Spring-Boot / Actuator-based microservice stack running on **Kubernetes** in **eu-west-2 (London)** and pulling container images from a private **ECR registry**. This folder is the centre of gravity for the MS platform: six microservice deployments, their services, a Horizontal Pod Autoscaler, a Redis cache and the Python helper that inventories ECR so engineers know which image tag to pin.

## Highlights

- **Six microservices, consistent shape** — each microservice ships with a `Deployment` + `Service` YAML (and HPA where traffic warrants). All run in the `backend` namespace with the same `app` / `release` label convention.
- **Rolling updates everywhere** — every deployment uses `RollingUpdate` (`maxSurge 25%` / `maxUnavailable 25%`, except `accounting`'s aggressive 100%/100%), plus `/actuator/health` liveness + readiness probes — standard Spring Boot health endpoints wired through.
- **Graceful shutdown** — every pod has a `preStop: sleep 20–60s` + `terminationGracePeriodSeconds` so in-flight requests drain before SIGTERM.
- **Dual-registry reality** — most images come from ECR (`975050035051.dkr.ecr.eu-west-2.amazonaws.com/backend/*:latest`); the legacy websocket service still pulls from GCR (`gcr.io/in-app-1278/...`). Captured as-is to match what's actually running.
- **HPA on `ms-live`** — CPU-driven autoscaler (min 4, max 6, `targetAverageUtilization: 350%`) for the main user-facing server.
- **ECR audit helper** — `python-scripts-for-automation/ecr.py` paginates every ECR repo in the region and prints a copy-pasteable `<repo>.dkr.ecr.eu-west-2.amazonaws.com/<repo>:<tag>` line for each image, so the image reference you put in the next deployment is always correct.

## Services overview

| Folder | Deployment | Image source | Port | Namespace | Notes |
|---|---|---|---|---|---|
| `ms-live/` | `ms-live` | ECR `backend/main-server:latest` | 8080 (HTTP) | `backend` | Main API server; HPA 4–6 replicas at 350% CPU |
| `ms-server_websocket-master/` | `ms-livewebsocket` | GCR `ms-server_websocket:latest` | 443 (HTTPS) | `backend` | WebSocket server; `Service` + `servicehttp.yaml` LoadBalancer |
| `accounting-master/` | `ms-integration` | ECR `backend/integrations:latest` | 443 (HTTPS) | `backend` | Accounting / integrations; 2 vCPU, 4 GB |
| `ms-smsemail-master/kubernetes-sandbox/` | `ms-sandbox-smsemail` | ECR `backend/sms-email-notifications-server:latest` | 8585 (HTTP) | `backend` | SMS + email notifications (sandbox env) |
| `kubernetes-data-migration-sandbox/` | `ms-data-migration` | ECR `backend/data-migration:latest` | 443 (HTTPS) | `backend` | Heavy job: 16 vCPU, 32 GB requested |
| `redis-deployments/` | `redis-deployment` | `redis:latest` | 6379 | `redis` | ClusterIP, single replica — cache, not primary store |

Plus the infra sidecars:

| Folder | What it is |
|---|---|
| `python-scripts-for-automation/` | `ecr.py` — boto3 ECR image inventory helper |

## Architecture

```
                 ┌─────────────────────── EKS / k8s cluster (eu-west-2) ────────────────────────┐
                 │                                                                              │
 ALB/NLB  ───►   │  ms-live (HPA 4–6)   ms-livewebsocket   ms-integration   ms-sandbox-smsemail │
                 │       │                     │                  │                  │          │
                 │   main-server          websocket :443      integrations         sms/email    │
                 │       │                                                                      │
                 │       ▼                                                                      │
                 │   redis-service (redis:latest, ns=redis)                                     │
                 │                                                                              │
                 │   ms-data-migration (16 vCPU / 32 GB, batch)                                │
                 └──────┬───────────────────────────────────────────────────────────────────────┘
                        │
                        ▼
                 ECR repos in eu-west-2:  (inventoried by ecr.py)
                   backend/main-server            backend/integrations
                   backend/sms-email-notifications-server   backend/data-migration
                   ...
```

## Tech stack

- **Orchestration:** Kubernetes (`apps/v1`, `autoscaling/v2beta1`)
- **Application:** Spring Boot (Actuator `/actuator/health`), Java runtime (inferred from image names / health endpoints)
- **Image registry:** AWS ECR + one legacy GCR image
- **Cloud:** AWS `eu-west-2` (London)
- **Tooling:** boto3

## Repository layout

```
AC-DEPLOYMENTS/
├── README.md
├── .gitignore
├── accounting-master/
│   ├── kubernetes.yaml              # ms-integration Deployment (2 CPU / 4G)
│   └── service.yaml                 # LoadBalancer :443
├── ms-live/
│   ├── kubernetes.yaml              # ms-live Deployment (main API server)
│   ├── service.yaml
│   └── hpa.yaml                     # HPA min 4 / max 6 / CPU 350%
├── ms-server_websocket-master/
│   ├── kubernetes.yaml              # ms-livewebsocket Deployment (GCR image)
│   ├── service.yaml
│   └── servicehttp.yaml             # LoadBalancer + nodePort 32265
├── ms-smsemail-master/
│   └── kubernetes-sandbox/
│       └── kubernetes.yaml          # Deployment + Service; Slack token via secretKeyRef
├── kubernetes-data-migration-sandbox/
│   ├── kubernetes.yaml              # 16 vCPU / 32 GB data-migration Deployment
│   └── service.yaml
├── redis-deployments/
│   ├── deployment.yaml              # redis:latest, ClusterIP
│   └── service.yaml
└── python-scripts-for-automation/
    └── ecr.py                       # inventory every ECR repo+tag in the region
```

## How it works

### A microservice deploys like this

1. `kubectl apply -f <svc>/kubernetes.yaml` — creates the `Deployment` with rolling update strategy, resource requests, liveness/readiness probes on `/actuator/health`, and a `preStop` sleep for graceful drain.
2. `kubectl apply -f <svc>/service.yaml` — exposes the pods via a `LoadBalancer` (external services) or `ClusterIP` (internal).
3. For `ms-live`, `kubectl apply -f ms-live/hpa.yaml` — wires up the HPA.

### The ECR inventory (`ecr.py`)

```
describe_repositories() → for each repo:
    paginate list_images(repositoryName=repo)
        print "<repo>.dkr.ecr.<region>.amazonaws.com/<repo>:<tag>"
```

Copy-paste the line for the tag you want into the `image:` field of a Deployment YAML and `kubectl apply`.

## Prerequisites

- `kubectl` pointed at the target cluster with RBAC to the `backend` and `redis` namespaces
- Python 3 with `boto3` (for `ecr.py`)
- A Kubernetes Secret `slack-secrets` in namespace `backend` with key `bot-token` (referenced by `ms-smsemail` Deployment); create with:

  ```bash
  kubectl -n backend create secret generic slack-secrets \
    --from-literal=bot-token="$SLACK_BOT_TOKEN"
  ```

## Notes

- `accounting-master` uses an aggressive rolling strategy (`maxSurge: 100% / maxUnavailable: 100%`) — equivalent to a recreate. Fine for stateless background processors, dangerous for anything handling live traffic.
- The websocket service's HPA is absent (replicas not explicitly set); production should add one before traffic growth outpaces the single pod.
- `ms-data-migration` requests 16 vCPU + 32 GB — size your node group accordingly or it will stay `Pending`.
- Demonstrates: production-style Kubernetes microservice layout, Spring Boot Actuator health probe discipline, HPA tuning,boto3 ECR inventory scripting, secret-leak cleanup workflow.
