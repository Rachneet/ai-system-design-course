#!/usr/bin/env bash
# One-time Google Cloud setup for Relay. Read it before running: it creates billable resources.
#   PROJECT=my-project REGION=europe-west1 GITHUB_REPO=owner/ai-system-design-course bash relay/infra/setup_gcp.sh
set -euo pipefail
: "${PROJECT:?}" "${REGION:?}" "${GITHUB_REPO:?}"
gcloud config set project "$PROJECT"
gcloud services enable run.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com \
  iamcredentials.googleapis.com sts.googleapis.com

gcloud artifacts repositories create relay --repository-format=docker --location="$REGION" || true

# Least-privilege identities: the API and the worker read only the secrets they need; the deployer deploys.
for sa in relay-api relay-worker relay-deployer; do
  gcloud iam service-accounts create "$sa" || true
done
API=relay-api@$PROJECT.iam.gserviceaccount.com
WORKER=relay-worker@$PROJECT.iam.gserviceaccount.com
DEPLOYER=relay-deployer@$PROJECT.iam.gserviceaccount.com

echo "Create these secrets with: printf '%s' VALUE | gcloud secrets create NAME --data-file=-"
echo "  model-api-key, model-api-key-staging, database-url, database-url-staging, jwks-url, jwt-issuer"
for s in model-api-key database-url jwks-url jwt-issuer model-api-key-staging database-url-staging; do
  gcloud secrets add-iam-policy-binding "$s" --member="serviceAccount:$API" --role=roles/secretmanager.secretAccessor || true
done
for s in model-api-key database-url; do
  gcloud secrets add-iam-policy-binding "$s" --member="serviceAccount:$WORKER" --role=roles/secretmanager.secretAccessor || true
done

for role in roles/run.admin roles/artifactregistry.writer roles/iam.serviceAccountUser; do
  gcloud projects add-iam-policy-binding "$PROJECT" --member="serviceAccount:$DEPLOYER" --role="$role"
done

# Keyless GitHub Actions auth (Workload Identity Federation), limited to this repository.
gcloud iam workload-identity-pools create github --location=global || true
gcloud iam workload-identity-pools providers create-oidc github --location=global --workload-identity-pool=github \
  --issuer-uri=https://token.actions.githubusercontent.com \
  --attribute-mapping=google.subject=assertion.sub,attribute.repository=assertion.repository \
  --attribute-condition="assertion.repository == '$GITHUB_REPO'" || true
POOL=$(gcloud iam workload-identity-pools describe github --location=global --format='value(name)')
gcloud iam service-accounts add-iam-policy-binding "$DEPLOYER" --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/$POOL/attribute.repository/$GITHUB_REPO"

echo "Set these GitHub repository variables:"
echo "  GCP_PROJECT_ID=$PROJECT  GCP_REGION=$REGION  GCP_DEPLOY_SA=$DEPLOYER"
echo "  GCP_WIF_PROVIDER=$POOL/providers/github"
echo "Database: Cloud SQL for PostgreSQL 16 with the vector extension, or a Neon/Supabase free tier."
echo "Rollback: gcloud run services update-traffic relay-api --region $REGION --to-revisions=PREVIOUS_REVISION=100"
