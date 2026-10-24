#!/usr/bin/env bash
# Build the images, push them to ECR, and roll them out on the k3s node.
# Kubernetes is reached through an SSM port-forwarding tunnel: the API server isn't public.
set -euo pipefail

INFRA="$(cd "$(dirname "$0")/.." && pwd)"
REPO="$(dirname "$INFRA")"
# Its own variable, not AWS_PROFILE: a shell's AWS_PROFILE for another account would
# otherwise win and push to (and log in against) the wrong account.
export AWS_PROFILE="${CHEIRON_AWS_PROFILE:-personal}"
LOCAL_PORT="${KUBE_LOCAL_PORT:-16443}"
KUBECONFIG_FILE="$INFRA/.kubeconfig"

tf() { terraform -chdir="$INFRA/terraform" output -raw "$1"; }
REGION="$(tf region)"
REGISTRY="$(tf registry)"
INSTANCE="$(tf instance_id)"
TAG="$(git -C "$REPO" rev-parse --short HEAD)"
if [ -n "$(git -C "$REPO" status --porcelain -- backend frontend)" ]; then
  TAG="$TAG-dirty-$(date +%s)" # tags are immutable; never reuse a commit tag for other code
fi

echo "==> Building and pushing images ($TAG)"
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$REGISTRY" >/dev/null
for app in api web; do
  src=backend; [ "$app" = web ] && src=frontend
  image="$REGISTRY/cheiron-$app:$TAG"
  if aws ecr describe-images --region "$REGION" --repository-name "cheiron-$app" \
    --image-ids imageTag="$TAG" >/dev/null 2>&1; then
    echo "$image is already in ECR"
    continue
  fi
  docker buildx build --platform linux/amd64 --load -t "$image" "$REPO/$src"
  docker push "$image"
done

echo "==> Syncing cluster secrets and fetching the kubeconfig (via SSM)"
CMD_ID="$(aws ssm send-command --region "$REGION" --instance-ids "$INSTANCE" \
  --document-name AWS-RunShellScript \
  --parameters 'commands=["/usr/local/bin/cheiron-sync-secrets 1>&2","cat /etc/rancher/k3s/k3s.yaml"]' \
  --query Command.CommandId --output text)"
aws ssm wait command-executed --region "$REGION" --command-id "$CMD_ID" --instance-id "$INSTANCE" || true
umask 077
aws ssm get-command-invocation --region "$REGION" --command-id "$CMD_ID" --instance-id "$INSTANCE" \
  --query StandardOutputContent --output text \
  | sed "s#https://127.0.0.1:6443#https://127.0.0.1:$LOCAL_PORT#" > "$KUBECONFIG_FILE"
aws ssm get-command-invocation --region "$REGION" --command-id "$CMD_ID" --instance-id "$INSTANCE" \
  --query StandardErrorContent --output text
grep -q "certificate-authority-data" "$KUBECONFIG_FILE" || { echo "could not read the kubeconfig" >&2; exit 1; }
export KUBECONFIG="$KUBECONFIG_FILE"

echo "==> Opening a tunnel to the Kubernetes API on localhost:$LOCAL_PORT"
aws ssm start-session --region "$REGION" --target "$INSTANCE" \
  --document-name AWS-StartPortForwardingSession \
  --parameters "{\"portNumber\":[\"6443\"],\"localPortNumber\":[\"$LOCAL_PORT\"]}" >/dev/null &
TUNNEL=$!
# The plugin outlives the aws process, so stop both.
trap 'kill $TUNNEL 2>/dev/null || true; pkill -f "session-manager-plugin.*$INSTANCE" 2>/dev/null || true' EXIT
for _ in $(seq 1 30); do kubectl get --raw /readyz >/dev/null 2>&1 && break; sleep 1; done
kubectl get --raw /readyz >/dev/null

echo "==> Waiting for cert-manager"
for _ in $(seq 1 60); do kubectl get crd clusterissuers.cert-manager.io >/dev/null 2>&1 && break; sleep 5; done
kubectl wait --for=condition=Established crd/clusterissuers.cert-manager.io --timeout=120s
kubectl -n cert-manager rollout status deploy/cert-manager-webhook --timeout=180s

echo "==> Applying manifests"
DEPLOY_DIR="$INFRA/k8s/.deploy" # outside the overlay: Kustomize rejects a root inside its own base
mkdir -p "$DEPLOY_DIR"
cat > "$DEPLOY_DIR/kustomization.yaml" <<YAML
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - ../overlays/k3s
images:
  - name: cheiron-api
    newName: $REGISTRY/cheiron-api
    newTag: "$TAG"
  - name: cheiron-web
    newName: $REGISTRY/cheiron-web
    newTag: "$TAG"
YAML
kubectl apply -k "$DEPLOY_DIR"
kubectl -n cheiron rollout status statefulset/postgres --timeout=180s
kubectl -n cheiron rollout status deploy/api --timeout=300s
kubectl -n cheiron rollout status deploy/web --timeout=300s
kubectl -n cheiron get pods,ingress,certificate

echo "==> Deployed $TAG: $(tf app_url) and $(tf api_url)"
