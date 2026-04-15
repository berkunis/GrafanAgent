#!/usr/bin/env bash
# Build + push every GrafanAgent service image, then let Terraform roll Cloud
# Run to the new tag. Designed to run from a clean workstation or GitHub
# Actions runner.
#
# Required env:
#   GCP_PROJECT_ID       target project
#   GCP_REGION           default: us-central1
#
# Optional env:
#   IMAGE_TAG            defaults to the short git SHA
#   SKIP_PUSH=1          build only (useful for smoke tests)
#   SKIP_TERRAFORM=1     push only (useful when re-uploading a rebuild)

set -euo pipefail

: "${GCP_PROJECT_ID:?GCP_PROJECT_ID is required}"
: "${GCP_REGION:=us-central1}"
IMAGE_TAG="${IMAGE_TAG:-$(git rev-parse --short HEAD)}"
REPO_URL="${GCP_REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/grafanagent"

declare -A PY_SERVICES=(
  [router]=agents.router.main
  [lifecycle]=agents.lifecycle.main
  [lead-scoring]=agents.lead_scoring.main
  [attribution]=agents.attribution.main
  [mcp-bigquery]=mcp_servers.bigquery.server
  [mcp-customer-io]=mcp_servers.customer_io.server
  [mcp-slack]=mcp_servers.slack.server
)

echo "==> image tag: ${IMAGE_TAG}"
echo "==> registry: ${REPO_URL}"

# Python services share one Dockerfile; Docker's layer cache makes rebuilds
# cheap across services since only SERVICE_MODULE and the CMD differ.
for svc in "${!PY_SERVICES[@]}"; do
  module="${PY_SERVICES[$svc]}"
  image="${REPO_URL}/${svc}:${IMAGE_TAG}"
  echo "==> building ${svc} (SERVICE_MODULE=${module})"
  docker build \
    --platform linux/amd64 \
    --build-arg "SERVICE_MODULE=${module}" \
    -t "${image}" .
done

# TS Slack approver lives in its own subtree and has its own multi-stage build.
TS_IMAGE="${REPO_URL}/slack-approver:${IMAGE_TAG}"
echo "==> building slack-approver (TypeScript)"
docker build --platform linux/amd64 -t "${TS_IMAGE}" apps/slack-approver

if [[ "${SKIP_PUSH:-0}" != "1" ]]; then
  echo "==> pushing images"
  for svc in "${!PY_SERVICES[@]}"; do
    docker push "${REPO_URL}/${svc}:${IMAGE_TAG}"
  done
  docker push "${TS_IMAGE}"
fi

if [[ "${SKIP_TERRAFORM:-0}" != "1" ]]; then
  echo "==> rolling Cloud Run via terraform"
  terraform -chdir=infra/terraform apply \
    -auto-approve \
    -var "project_id=${GCP_PROJECT_ID}" \
    -var "region=${GCP_REGION}" \
    -var "image_tag=${IMAGE_TAG}" \
    -var "enable_deploy=true" \
    -var "enable_cloudsql=true"
fi

echo "==> done"
terraform -chdir=infra/terraform output -json 2>/dev/null | \
  python -c 'import json,sys;d=json.load(sys.stdin);print("router_url=",d.get("router_url",{}).get("value")); print("slack_approver_url=",d.get("slack_approver_url",{}).get("value"))' \
  || true
