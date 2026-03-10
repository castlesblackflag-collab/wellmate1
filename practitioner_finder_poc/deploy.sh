#!/usr/bin/env bash
# ============================================================
# Wellmate Practitioner Finder POC - Deploy to Google Cloud Run
# ============================================================
#
# HOW TO USE:
#   1. Go to https://shell.cloud.google.com  (free, runs in your browser)
#   2. Clone this repo:
#        git clone https://github.com/castlesblackflag-collab/wellmate1.git
#        cd wellmate1
#   3. Run this script:
#        bash practitioner_finder_poc/deploy.sh
#   4. When it finishes, it prints a public URL you can open in any browser.
#
# PREREQUISITES:
#   - A Google Cloud project with billing enabled
#   - The API key for Google Places (you'll be prompted)
# ============================================================

set -euo pipefail

SERVICE_NAME="wellmate-finder-poc"
REGION="us-central1"

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

# --- Build and deploy ---
echo ""
echo "Building and deploying to Cloud Run (this takes 2-3 minutes)..."
cd "$(dirname "$0")"

gcloud run deploy "$SERVICE_NAME" \
    --source . \
    --region "$REGION" \
    --platform managed \
    --allow-unauthenticated \
    --set-env-vars "PLACES_API_KEY=$PLACES_API_KEY" \
    --port 8080 \
    --memory 512Mi \
    --timeout 60 \
    --min-instances 0 \
    --max-instances 2

# --- Get the URL ---
echo ""
echo "============================================================"
URL=$(gcloud run services describe "$SERVICE_NAME" --region "$REGION" --format 'value(status.url)')
echo "DEPLOYED SUCCESSFULLY!"
echo ""
echo "Open this link in your browser to demo:"
echo "  $URL"
echo ""
echo "To delete later:"
echo "  gcloud run services delete $SERVICE_NAME --region $REGION"
echo "============================================================"
