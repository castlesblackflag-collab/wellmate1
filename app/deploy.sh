#!/usr/bin/env bash
# ============================================================
# Wellmate Practitioner Finder API - Deploy to Google Cloud Run
# ============================================================
#
# This deploys the FastAPI backend at app/ to Cloud Run, giving you
# a public URL you can paste into Zapier / Make / n8n / any HTTP tool.
#
# HOW TO USE:
#   1. Go to https://shell.cloud.google.com  (free, runs in your browser)
#   2. Clone this repo:
#        git clone https://github.com/castlesblackflag-collab/wellmate1.git
#        cd wellmate1
#        git checkout claude/practitioner-finder-poc-UZg3a
#   3. Run this script:
#        bash app/deploy.sh
#   4. When it finishes, it prints a public URL. Paste that into PORTING.md.
#
# PREREQUISITES:
#   - A Google Cloud project with billing enabled
#   - Your Google Places API key (you'll be prompted)
# ============================================================

set -euo pipefail

SERVICE_NAME="wellmate-practitioner-finder"
REGION="us-central1"

# --- Locate repo root (this script is at app/deploy.sh) ---
cd "$(dirname "$0")/.."

# --- Check gcloud is available ---
if ! command -v gcloud &> /dev/null; then
    echo "ERROR: gcloud CLI not found. Run this in Google Cloud Shell:"
    echo "  https://shell.cloud.google.com"
    exit 1
fi

# --- Get or confirm project ---
PROJECT=$(gcloud config get-value project 2>/dev/null || true)
if [ -z "$PROJECT" ]; then
    echo "No Google Cloud project set."
    read -rp "Enter your Google Cloud project ID: " PROJECT
    gcloud config set project "$PROJECT"
fi
echo "Using project: $PROJECT"

# --- Get API key ---
if [ -z "${PLACES_API_KEY:-}" ]; then
    read -rp "Enter your Google Places API key: " PLACES_API_KEY
fi
echo "API key set: ${PLACES_API_KEY:0:8}...${PLACES_API_KEY: -4}"

# --- Enable required APIs ---
echo ""
echo "Enabling Cloud Run and Cloud Build APIs..."
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com 2>/dev/null || true

# --- Build and deploy (uses root Dockerfile, which runs app.main:app on port 8080) ---
echo ""
echo "Building and deploying to Cloud Run (2-3 minutes)..."

gcloud run deploy "$SERVICE_NAME" \
    --source . \
    --region "$REGION" \
    --platform managed \
    --allow-unauthenticated \
    --set-env-vars "GOOGLE_PLACES_API_KEY=$PLACES_API_KEY" \
    --port 8080 \
    --memory 512Mi \
    --cpu 1 \
    --timeout 30 \
    --concurrency 80 \
    --min-instances 0 \
    --max-instances 10

# --- Get the URL ---
URL=$(gcloud run services describe "$SERVICE_NAME" --region "$REGION" --format 'value(status.url)')

echo ""
echo "============================================================"
echo "DEPLOYED SUCCESSFULLY"
echo ""
echo "API base URL:"
echo "  $URL"
echo ""
echo "Endpoint (for Zapier / Make / n8n):"
echo "  POST $URL/search_practitioners"
echo ""
echo "Quick test (copy-paste this):"
cat <<EOF
  curl -X POST $URL/search_practitioners \\
    -H "Content-Type: application/json" \\
    -d '{
      "location_text": "80202",
      "care_style": "mixed",
      "goal_outcomes": ["walking without pain"],
      "preferences": ["non-pharmacologic"],
      "radius_km": 16
    }'
EOF
echo ""
echo "Paste the URL and the curl response into practitioner_finder_poc/PORTING.md"
echo "to share with whoever is wiring up the no-code tool."
echo ""
echo "To delete later:"
echo "  gcloud run services delete $SERVICE_NAME --region $REGION"
echo "============================================================"
