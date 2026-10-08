#!/usr/bin/env bash
# Deploy di GarAI su Google Cloud Run. Idempotente: crea solo cio' che manca, poi build e deploy.
#
#   GCP_ACCOUNT=me@example.com bash deploy/gcp.sh            # tutto
#   GEMINI_API_KEY=... bash deploy/gcp.sh                     # crea anche il secret con la chiave Gemini (se manca)
#   SKIP_SETUP=1 bash deploy/gcp.sh                           # solo build + deploy
#
# Risorse dedicate (prefisso garai, etichetta app=garai), isolate dagli altri prodotti del progetto:
#   Artifact Registry  garai                       immagini del container
#   Cloud Storage      <progetto>-garai-data       cartella dati dell'app (pratiche, utenti, impostazioni, costi)
#                      <progetto>-garai-build      sorgenti per Cloud Build
#   Service account    garai-run                   identita' del servizio: accede solo al proprio bucket e ai propri secret
#                      garai-build                 identita' della build: scrive solo nel proprio repository
#   Secret Manager     garai-session-secret        firma dei cookie di sessione
#                      garai-gemini-key            chiave Gemini (facoltativa: si puo' inserire anche dall'app)
#   Cloud Run          garai                       il servizio (scala a zero, al massimo un'istanza: l'unica a scrivere i dati)
set -euo pipefail

PROJECT="${GCP_PROJECT:-tutoral-498710}"
REGION="${GCP_REGION:-europe-west1}"
SERVICE="garai"
REPO="garai"
DATA_BUCKET="${PROJECT}-garai-data"
BUILD_BUCKET="${PROJECT}-garai-build"
SA_RUN="garai-run@${PROJECT}.iam.gserviceaccount.com"
SA_BUILD="garai-build@${PROJECT}.iam.gserviceaccount.com"
LABELS="app=garai"
TAG="$(git rev-parse --short HEAD 2>/dev/null || echo manual)-$(date +%Y%m%d%H%M%S)"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT}/${REPO}/garai:${TAG}"

export CLOUDSDK_CORE_PROJECT="$PROJECT"
[ -n "${GCP_ACCOUNT:-}" ] && export CLOUDSDK_CORE_ACCOUNT="$GCP_ACCOUNT"
cd "$(dirname "$0")/.."

exists() { "$@" >/dev/null 2>&1; }

if [ -z "${SKIP_SETUP:-}" ]; then
  echo "== API"
  gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
    secretmanager.googleapis.com storage.googleapis.com iam.googleapis.com

  echo "== Artifact Registry"
  exists gcloud artifacts repositories describe "$REPO" --location="$REGION" ||
    gcloud artifacts repositories create "$REPO" --repository-format=docker --location="$REGION" \
      --description="GarAI: immagini del container" --labels="$LABELS"

  echo "== Bucket"
  for b in "$DATA_BUCKET" "$BUILD_BUCKET"; do
    exists gcloud storage buckets describe "gs://$b" ||
      gcloud storage buckets create "gs://$b" --location="$REGION" --uniform-bucket-level-access \
        --public-access-prevention --default-storage-class=STANDARD
    gcloud storage buckets update "gs://$b" --update-labels="$LABELS" >/dev/null
  done

  echo "== Service account"
  exists gcloud iam service-accounts describe "$SA_RUN" ||
    gcloud iam service-accounts create garai-run --display-name="GarAI - servizio Cloud Run"
  exists gcloud iam service-accounts describe "$SA_BUILD" ||
    gcloud iam service-accounts create garai-build --display-name="GarAI - Cloud Build"

  echo "== Permessi (solo sulle risorse garai)"
  gcloud storage buckets add-iam-policy-binding "gs://$DATA_BUCKET" \
    --member="serviceAccount:$SA_RUN" --role=roles/storage.objectAdmin >/dev/null
  gcloud storage buckets add-iam-policy-binding "gs://$BUILD_BUCKET" \
    --member="serviceAccount:$SA_BUILD" --role=roles/storage.objectAdmin >/dev/null
  gcloud artifacts repositories add-iam-policy-binding "$REPO" --location="$REGION" \
    --member="serviceAccount:$SA_BUILD" --role=roles/artifactregistry.writer >/dev/null
  # scrittura dei log di build: ruolo solo a livello di progetto
  gcloud projects add-iam-policy-binding "$PROJECT" --member="serviceAccount:$SA_BUILD" \
    --role=roles/logging.logWriter --condition=None >/dev/null

  echo "== Secret"
  if ! exists gcloud secrets describe garai-session-secret; then
    python -c "import secrets; print(secrets.token_urlsafe(48), end='')" |
      gcloud secrets create garai-session-secret --data-file=- --replication-policy=automatic --labels="$LABELS"
  fi
  if ! exists gcloud secrets describe garai-gemini-key && [ -n "${GEMINI_API_KEY:-}" ]; then
    printf '%s' "$GEMINI_API_KEY" |
      gcloud secrets create garai-gemini-key --data-file=- --replication-policy=automatic --labels="$LABELS"
  fi
  for s in garai-session-secret garai-gemini-key; do
    exists gcloud secrets describe "$s" &&
      gcloud secrets add-iam-policy-binding "$s" --member="serviceAccount:$SA_RUN" \
        --role=roles/secretmanager.secretAccessor >/dev/null
  done
fi

echo "== Build $IMAGE"
gcloud builds submit --config=deploy/cloudbuild.yaml --substitutions="_IMAGE=$IMAGE" --region="$REGION" \
  --service-account="projects/$PROJECT/serviceAccounts/$SA_BUILD" \
  --gcs-source-staging-dir="gs://$BUILD_BUCKET/source" .

echo "== Deploy"
SECRETS="GARAI_SECRET_KEY=garai-session-secret:latest"
exists gcloud secrets describe garai-gemini-key && SECRETS="$SECRETS,GEMINI_API_KEY=garai-gemini-key:latest"
# Scala a zero; al massimo un'istanza, perche' e' l'unica a scrivere i dati. CPU allocata per tutta la vita dell'istanza
# (anche tra una richiesta e l'altra): le elaborazioni in background proseguono finche' l'istanza e' attiva.
gcloud run deploy "$SERVICE" --image="$IMAGE" --region="$REGION" --service-account="$SA_RUN" \
  --allow-unauthenticated --execution-environment=gen2 --cpu=2 --memory=2Gi --no-cpu-throttling --cpu-boost \
  --min-instances=0 --max-instances=1 --concurrency=40 --timeout=3600 \
  --set-env-vars="GCS_BUCKET=$DATA_BUCKET,MONTHLY_BUDGET_USD=${MONTHLY_BUDGET_USD:-20}" \
  --set-secrets="$SECRETS" --labels="$LABELS"

gcloud run services describe "$SERVICE" --region="$REGION" --format="value(status.url)"
