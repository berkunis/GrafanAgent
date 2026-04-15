#!/usr/bin/env bash
# Apply Terraform (idempotent — BQ seed is a DELETE+INSERT job) and ingest the
# RAG corpus into the deployed pgvector instance. Run once after the first
# successful deploy.

set -euo pipefail

: "${GCP_PROJECT_ID:?GCP_PROJECT_ID is required}"
: "${GCP_REGION:=us-central1}"

echo "==> terraform apply (BQ dataset + seed + pgvector)"
terraform -chdir=infra/terraform apply \
  -auto-approve \
  -var "project_id=${GCP_PROJECT_ID}" \
  -var "region=${GCP_REGION}" \
  -var "enable_cloudsql=true" \
  -var "enable_deploy=${ENABLE_DEPLOY:-false}"

echo "==> reading Cloud SQL DSN from Secret Manager"
DSN_SECRET="$(terraform -chdir=infra/terraform output -raw cloudsql_dsn_secret_id)"
export PGVECTOR_DSN="$(gcloud secrets versions access latest --secret="${DSN_SECRET}")"

echo "==> ingesting RAG corpus into pgvector"
RAG_EMBEDDER=vertex RAG_BACKEND=pgvector \
  python -m rag.ingest

echo "==> done"
