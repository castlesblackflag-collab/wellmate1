# Deployment and Integration Guide

## Prerequisites

- Google Cloud project with billing enabled
- `gcloud` CLI authenticated
- APIs enabled: Cloud Run, Cloud Build, Places API (new), Geocoding API, Secret Manager

## 1. Deploy to Cloud Run

### Option A: Deploy from source (recommended)

```bash
# Set your project
gcloud config set project YOUR_PROJECT_ID

# Store the Places API key in Secret Manager
gcloud secrets create places-api-key \
  --data-file=- <<< "YOUR_PLACES_API_KEY"

# Deploy from source (Cloud Build + Cloud Run)
gcloud run deploy wellmate-practitioner-finder \
  --source=. \
  --region=us-central1 \
  --allow-unauthenticated \
  --set-secrets=GOOGLE_PLACES_API_KEY=places-api-key:latest \
  --memory=512Mi \
  --cpu=1 \
  --timeout=30 \
  --concurrency=80 \
  --min-instances=0 \
  --max-instances=10
```

### Option B: Build and deploy container

```bash
# Build
docker build -t gcr.io/YOUR_PROJECT_ID/wellmate-practitioner-finder .

# Push
docker push gcr.io/YOUR_PROJECT_ID/wellmate-practitioner-finder

# Deploy
gcloud run deploy wellmate-practitioner-finder \
  --image=gcr.io/YOUR_PROJECT_ID/wellmate-practitioner-finder \
  --region=us-central1 \
  --allow-unauthenticated \
  --set-secrets=GOOGLE_PLACES_API_KEY=places-api-key:latest
```

### Verify deployment

```bash
# Get the service URL
SERVICE_URL=$(gcloud run services describe wellmate-practitioner-finder \
  --region=us-central1 --format='value(status.url)')

# Health check
curl $SERVICE_URL/

# Test search (requires live API keys)
curl -X POST "$SERVICE_URL/search_practitioners" \
  -H "Content-Type: application/json" \
  -d '{
    "location_text": "78701",
    "care_style": "mixed",
    "goal_outcomes": ["reduce chronic pain", "improve mobility"]
  }'
```

## 2. Register OpenAPI Tool in Agent Builder

1. Go to [Dialogflow CX Console](https://dialogflow.cloud.google.com/cx)
2. Open your Wellmate agent
3. Navigate to **Tools** in the left sidebar
4. Click **Create Tool**
5. Select **OpenAPI**
6. Upload or paste the contents of `search_practitioners.yaml`
7. Update the `servers[0].url` in the spec to your actual Cloud Run URL
8. Save the tool

## 3. Configure the Practitioner Finder Playbook

Create a new Playbook in your Wellmate agent with these settings:

### Goal
```
Help users find healthcare practitioners that match their specific health goals,
care style preferences, and location.
```

### Instructions
```
- You are the Practitioner Finder assistant within Wellmate.
- When the user wants to find a doctor, practitioner, therapist, or any
  healthcare provider, collect the following required information:
  1. Their location (ZIP code or city)
  2. Their care style preference (medical, whole health, or mixed)
  3. Their health goals or desired outcomes (1-3 short statements)
- Optionally collect: main health issue, preferences, avoidances, visit mode.
- Once you have the required fields, call the search_practitioners tool.
- Present the results using ONLY the data returned by the tool.
- For each provider, mention their name, category, distance, rating, and
  fit_reasons from the tool response.
- NEVER invent provider names, addresses, phone numbers, or credentials.
- NEVER add fit reasons beyond what the tool returned.
- If the tool returns warnings, communicate them to the user.
- If the tool returns an error, tell the user and suggest adjusting their search.
- Support refinement: the user can ask to expand radius, change care style,
  switch to telehealth, or adjust preferences. Make a new tool call with
  updated parameters.
```

### Tool binding
- Bind the `search_practitioners` tool created in step 2.

## 4. Test in Playbook Simulator

In the Dialogflow CX console, open the Playbook simulator and test these flows:

### Flow 1: Minimal required fields
```
User: I need help finding a doctor near Austin TX for back pain
-> Playbook collects: location=Austin TX, care_style=medical, goals=[reduce back pain]
-> Calls tool
-> Presents ranked results with fit_reasons
```

### Flow 2: Whole health mixed
```
User: I want to explore holistic options for stress and anxiety in 90210
-> Playbook collects: location=90210, care_style=whole_health, goals=[reduce stress, manage anxiety]
-> Calls tool
-> Presents yoga, meditation, acupuncture providers
```

### Flow 3: Refinement
```
User: Can you expand the search to 50km?
-> Playbook calls tool again with radius_km=50
-> Presents updated results
```

### Flow 4: Error handling
```
User: Find providers in ZZZZZ
-> Tool returns error: "Could not resolve location: ZZZZZ"
-> Playbook tells user the location was not recognized
```

## 5. Local Development

```bash
# Set API key for local testing
export GOOGLE_PLACES_API_KEY=your_key_here

# Run server
uvicorn app.main:app --reload --port 8080

# Run tests
pytest tests/ -v

# View auto-generated OpenAPI spec
# Navigate to http://localhost:8080/docs
```
