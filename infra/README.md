# Deployment: Terraform + Kubernetes (k3s) on one EC2 instance

The web app and the API run on Kubernetes. To keep the cost down, the cluster is **k3s on a single EC2 instance**: a CNCF-certified Kubernetes distribution with the same `kubectl`, manifests and Helm charts as EKS, but no $0.10/hour control-plane fee. The reasons, the alternatives and a production design are in [design Q19](../docs/design/19-deployment-ui.md#revision-2026-10-25-what-was-actually-deployed).

- Web app: https://trials.cheiron.engineeradriel.com
- API: https://api.cheiron.engineeradriel.com

## What's where

| Path | What it defines |
|---|---|
| `terraform/bootstrap/` | One-time: the S3 bucket for Terraform state (versioned, encrypted, private) |
| `terraform/` | VPC with one public subnet (no NAT gateway); security group (only 80 and 443 open); IAM role; the EC2 node (encrypted gp3 disk, IMDSv2 only); Elastic IP; ECR repositories; the Secrets Manager secret; the two DNS records |
| `terraform/node-setup.sh.tftpl` | First boot: installs a pinned k3s, cert-manager (through k3s's Helm controller), Traefik settings, and a timer that keeps cluster secrets in sync |
| `k8s/base/` | Kustomize base: namespace, Postgres StatefulSet, API and web Deployments + Services, the Ingress for both hostnames |
| `k8s/overlays/k3s/` | **Deployed.** Traefik ingress class + a Let's Encrypt ClusterIssuer |
| `k8s/overlays/eks/` | **Not deployed.** The same base on EKS: ALB ingress (AWS Load Balancer Controller, ACM certificate) and gp3 volumes |
| `scripts/deploy.sh` | Builds and pushes the images (tagged with the git commit), then rolls them out |

## Design choices

- **No SSH, no public Kubernetes API.** Admin access goes through SSM Session Manager. `deploy.sh` opens a port-forwarding tunnel to the API server only while it runs.
- **Secrets never touch git or Terraform state.**
  - The OpenAI key is set directly in Secrets Manager, and Terraform creates the secret without a value.
  - The Postgres password is generated on the node.
  - A systemd timer copies both into Kubernetes Secrets, and refreshes the ECR pull token, every 6 hours.
- **One API replica, on purpose.** The API's client keeps to 9 ClinicalTrials.gov requests per 10 s, just under the ~10 measured per IP, and each replica has its own limiter. More replicas would share that budget, not add to it.
- **The mirror sync runs in the API pod** (`MIRROR_SYNC_ENABLED`, design Q22): a copy of ClinicalTrials.gov in Postgres's `registry` schema, ~1.2 GB, loaded once in ~25 minutes and then updated after each daily data update. It shares the API's limiter, at half its budget, and an advisory lock keeps it to one sync while a rolling update runs two pods.
  - Rolling updates still have no downtime (`maxUnavailable: 0`).
  - Background jobs already work across replicas, thanks to the `SKIP LOCKED` queue and heartbeats.
- **t3.medium (4 GB) with an 8 GB swap file on a 50 GB disk.** The largest question (273k trials) peaks at about 2 GB in the API, and k3s, Postgres and the web app take about 1.2 GB.
  - Kubernetes keeps pods off swap by default, so the kubelet runs with `LimitedSwap`. A pod's swap share is proportional to its memory request: the API requests 1.5 GiB of 4, which gives it about 3 GB of swap.
  - A larger node (`instance_type = "t3.large"`) avoids swapping entirely.
- **Postgres in the cluster** keeps cost down. It holds caches, stored answers and the job queue, all of which can be rebuilt. In production it would be RDS.

## Cost (Seoul, on-demand)

About **$1.50/day**: t3.medium $0.052/h, EIP $0.005/h, 50 GB gp3 (~$0.15/day), ECR and Secrets Manager pennies. With `use_spot = true` it's about **$0.75/day**. `make infra-destroy` removes everything, images included.

## Deploying from scratch

Requires Terraform ≥ 1.10, the AWS CLI with the Session Manager plugin, Docker with buildx, and kubectl.

The AWS profile is `personal`. `make deploy` reads it from `CHEIRON_AWS_PROFILE` and ignores a shell `AWS_PROFILE` on purpose, so a shell set up for another account can't push images to the wrong one. Terraform takes it from the `aws_profile` variable and `backend.hcl`.

```bash
make infra-bootstrap   # once: the state bucket
make infra-plan        # review
make infra-apply       # node, registry, secret, DNS (k3s installs itself on first boot, ~2 min)

# Set the OpenAI key (read from your shell, never echoed):
aws secretsmanager put-secret-value --profile personal --region ap-northeast-2 \
  --secret-id cheiron/openai-api-key --secret-string "$OPENAI_API_KEY"

make deploy            # build, push, roll out; prints the URLs
```

After the first deploy, cert-manager gets the certificate within a minute or two (HTTP-01 challenge through Traefik).

### Deploying to your own account

The defaults point at this project's account and domain. To deploy elsewhere, change:

- `terraform/backend.hcl`: the state bucket name (`make infra-bootstrap` prints it), the region and the profile;
- the Terraform variables `aws_profile`, `region`, `zone_name` (an existing public Route 53 hosted zone), `app_host` and `api_host`;
- the hostnames in `k8s/base/`: the Ingress hosts (`ingress.yaml`), the API's CORS origin (`api.yaml`) and the web app's `PUBLIC_API_URL` (`web.yaml`).

## Moving to EKS

The same `k8s/base` deploys to EKS with `k8s/overlays/eks`. The Terraform would swap the EC2 node for an EKS cluster with a managed node group, plus the AWS Load Balancer Controller and the EBS CSI driver. The Kubernetes manifests don't change.
