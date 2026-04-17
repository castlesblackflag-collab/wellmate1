# Wellmate Practitioner Finder — API Porting Guide

Everything you need to call the Wellmate Practitioner Finder API from a no-code tool
(Zapier, Make, n8n, Pipedream, Bubble, Retool, Airtable, etc.) or from custom code.

---

## 1. Deploy the API (one time)

The API lives at `app/` in this repo and needs to be deployed to Cloud Run before
you can call it. See `app/deploy.sh` for a one-command deploy, or the manual steps:

```bash
# In Google Cloud Shell (https://shell.cloud.google.com):
git clone https://github.com/castlesblackflag-collab/wellmate1.git
cd wellmate1
git checkout claude/practitioner-finder-poc-UZg3a
bash app/deploy.sh
# When prompted, paste your Google Places API key.
# After ~3 min, it prints your live URL. Paste it into section 2 below.
```

---

## 2. Endpoint info

Paste your live URL from the deploy step above:

| Field | Value |
|---|---|
| **Base URL** | `https://wellmate-practitioner-finder-XXXXX-uc.a.run.app` *(replace with your real URL)* |
| **Endpoint path** | `/search_practitioners` |
| **Method** | `POST` |
| **Auth** | **None** — endpoint is public (`--allow-unauthenticated`). No API key, no bearer token, no header auth. |
| **Required header** | `Content-Type: application/json` |
| **Health check** | `GET /` returns `{"status": "ok", "service": "wellmate-practitioner-finder", "version": "0.1.0"}` |
| **Error behavior** | Always returns HTTP 200 with an `error` field if something failed. Never returns stack traces or non-200 codes for application errors. |

---

## 3. Request body

### Minimal request (only the 3 required fields)

```json
{
  "location_text": "80202",
  "care_style": "mixed",
  "goal_outcomes": ["walking without pain"]
}
```

### Full request (all fields, with defaults shown)

```json
{
  "location_text": "80202",
  "care_style": "mixed",
  "goal_outcomes": ["walking without pain", "avoiding long-term opioids"],
  "main_issue": "chronic lower back pain",
  "diagnoses": [],
  "preferences": ["non-pharmacologic"],
  "avoidances": ["opioids"],
  "visit_mode": "either",
  "insurance_hint": null,
  "radius_km": 20,
  "max_results": 5
}
```

### Field reference — request

| Field | Type | Required? | Allowed values / notes |
|---|---|---|---|
| `location_text` | string | **yes** | ZIP code or city, e.g. `"80202"` or `"Denver, CO"` |
| `care_style` | string | **yes** | One of: `"medical"`, `"whole_health"`, `"mixed"` |
| `goal_outcomes` | array of strings | **yes** | 1–5 short outcome strings, e.g. `["walking without pain"]` |
| `main_issue` | string \| null | no | Primary symptom, e.g. `"chronic lower back pain"` |
| `diagnoses` | array of strings | no | Known diagnoses, e.g. `["type 2 diabetes"]` |
| `preferences` | array of strings | no | Care preferences, e.g. `["non-pharmacologic", "mind-body"]` |
| `avoidances` | array of strings | no | Things to avoid, e.g. `["opioids", "surgery"]` |
| `visit_mode` | string | no | One of: `"in_person"`, `"telehealth"`, `"either"` (default: `"either"`) |
| `insurance_hint` | string \| null | no | Informational only, e.g. `"Kaiser"` |
| `radius_km` | integer | no | 1–100, default 20 |
| `max_results` | integer | no | 1–20, default 5 |

Source of truth: `app/schema.py:22-77`.

---

## 4. Response body

### Response shape (ALWAYS these 4 keys, even on error)

```json
{
  "results": [],
  "meta": {},
  "warnings": [],
  "error": null
}
```

### Sample response

*Paste the real JSON returned from your first live curl here. See the "get a sample"
instructions at the bottom of this file.*

```json
{
  "results": [
    {
      "provider_id": "ChIJ...",
      "name": "Example Physical Therapy",
      "provider_category": "physical_therapy",
      "is_physician": false,
      "npi_verified": true,
      "credentials": ["DPT"],
      "specialties": ["Physical Therapist"],
      "address": "1234 Main St, Denver, CO 80202, USA",
      "distance_km": 0.8,
      "rating": 4.9,
      "review_count": 142,
      "visit_modes": ["in_person"],
      "contact": {
        "phone": "(303) 555-0100",
        "website": "https://example.com"
      },
      "score": 87,
      "fit_reasons": [
        "Matches your goal: walking without pain",
        "Non-pharmacologic approach",
        "High patient rating (4.9/5)"
      ],
      "data_sources": ["google_places", "npi_registry"]
    }
  ],
  "meta": {
    "location_resolved": "80202, Denver, CO, USA",
    "lat": 39.7541,
    "lng": -105.0002,
    "radius_km": 16,
    "result_count": 5,
    "care_style": "mixed",
    "goal_outcomes": ["walking without pain"]
  },
  "warnings": [],
  "error": null
}
```

### Field reference — response

**Top-level:**

| Field | Type | Notes |
|---|---|---|
| `results` | array of ProviderResult | Ranked list (may be empty). Highest `score` first. |
| `meta` | ResponseMeta | Metadata about this search |
| `warnings` | array of strings | Non-fatal warnings (degraded data, safety alerts) |
| `error` | string \| null | Error message if search failed, otherwise `null` |

**ProviderResult (each item in `results`):**

| Field | Type | Notes |
|---|---|---|
| `provider_id` | string | Stable identifier (Google `place_id`) |
| `name` | string | Provider/clinic name |
| `provider_category` | string | One of: `physician`, `clinic`, `acupuncture`, `yoga`, `meditation`, `massage`, `nutrition`, `counseling`, `chiropractic`, `physical_therapy`, `other` |
| `is_physician` | boolean | |
| `npi_verified` | boolean | `true` if matched against NPPES NPI Registry |
| `credentials` | array of strings | e.g. `["MD", "DPT"]` |
| `specialties` | array of strings | e.g. `["Physical Therapist"]` |
| `address` | string \| null | Formatted address |
| `distance_km` | number \| null | Kilometers from search center |
| `rating` | number \| null | Google rating (0–5) |
| `review_count` | integer \| null | Google review count |
| `visit_modes` | array of strings | e.g. `["in_person"]` |
| `contact.phone` | string \| null | |
| `contact.website` | string \| null | |
| `score` | integer | **0–100**. Higher = better fit. |
| `fit_reasons` | array of strings | 2–5 short reason strings tied to user inputs |
| `data_sources` | array of strings | e.g. `["google_places", "npi_registry"]` |

**ResponseMeta:**

| Field | Type |
|---|---|
| `location_resolved` | string \| null |
| `lat` | number \| null |
| `lng` | number \| null |
| `radius_km` | integer |
| `result_count` | integer |
| `care_style` | string |
| `goal_outcomes` | array of strings |

Source of truth: `app/schema.py:84-133`.

---

## 5. No-code tool quick-start

### Zapier

1. Add a **Webhooks by Zapier** step
2. Choose **POST**
3. URL: `https://<your-url>/search_practitioners`
4. Payload Type: **JSON**
5. Data: map your fields to the request JSON shape above
6. Headers: `Content-Type: application/json`
7. Click "Test step" — you'll see the full response JSON

### Make (formerly Integromat)

1. Add an **HTTP** module → **Make a request**
2. Method: **POST**
3. URL: `https://<your-url>/search_practitioners`
4. Headers: add `Content-Type` = `application/json`
5. Body type: **Raw**
6. Content type: **JSON (application/json)**
7. Request content: paste the request JSON
8. Parse response: **Yes**

### n8n

1. Add an **HTTP Request** node
2. Method: **POST**
3. URL: `https://<your-url>/search_practitioners`
4. Authentication: **None**
5. Send Headers: yes → `Content-Type: application/json`
6. Send Body: yes → Body Content Type: **JSON** → paste request JSON
7. Response Format: **JSON**

### Pipedream / Retool / Bubble / Airtable

Use whatever their generic "HTTP POST" block is called. The URL, method, headers,
and body are all the same as above.

---

## 6. Get a real sample response

After you deploy, run this curl in Cloud Shell or any terminal and paste the
response into section 4 above:

```bash
curl -X POST https://<your-url>/search_practitioners \
  -H "Content-Type: application/json" \
  -d '{
    "location_text": "80202",
    "care_style": "mixed",
    "goal_outcomes": ["walking without pain"],
    "preferences": ["non-pharmacologic"],
    "radius_km": 16
  }'
```

---

## Appendix: decision logic (only if you want to replicate or tune the ranking)

You don't need this to call the API — the API already applies all this logic
internally. But if someone wants to understand *why* a provider got its score,
this is the complete, open logic.

### Scoring weights (`app/config/weights.yaml`)

```yaml
scoring_weights:
  outcome_alignment:    0.30    # How well the provider matches your goal_outcomes
  symptom_alignment:    0.15    # Match against main_issue / diagnoses
  care_style_alignment: 0.15    # Does their category match medical / whole_health / mixed
  preference_alignment: 0.15    # Boost for preference keywords (e.g. non-pharmacologic)
  review_quality:       0.10    # Google rating × log(review_count)
  accessibility:        0.15    # Distance, website/phone available, visit_mode match
# Sums to 1.0. Final score = round(100 * sum(weight_i * subscore_i)) clamped 0–100.
```

### Outcome → specialties/modalities (`app/config/mappings.yaml:10-82`)

23 outcome keywords mapped to medical specialties and whole-health modalities.
Examples:

```yaml
pain:
  medical: ["Pain Medicine", "Physical Medicine & Rehab", "Orthopedics"]
  whole_health: ["acupuncture", "massage", "chiropractic", "physical_therapy", "yoga"]
stress:
  medical: ["Psychiatry", "Psychology", "Family Medicine"]
  whole_health: ["meditation", "yoga", "counseling", "massage", "acupuncture"]
digestion:
  medical: ["Gastroenterology", "Internal Medicine"]
  whole_health: ["nutrition", "acupuncture", "yoga"]
```

Full list (all 23): pain, mobility, stress, anxiety, depression, sleep, weight,
nutrition, energy, flexibility, strength, balance, headache, medication, fertility,
heart, breathing, digestion, skin, aging, focus, trauma, recovery, posture.

### Symptom → specialties (`app/config/mappings.yaml:89-110`)

21 symptom keywords mapped to medical specialties. Used when `main_issue` is set.
Examples:

```yaml
back pain:     ["Orthopedics", "Pain Medicine", "Physical Medicine & Rehab"]
migraine:      ["Neurology", "Pain Medicine"]
insomnia:      ["Sleep Medicine", "Psychiatry"]
ibs:           ["Gastroenterology"]
```

### Preference signals (`app/config/mappings.yaml:118-136`)

```yaml
non-pharmacologic:
  boosts: ["acupuncture", "yoga", "massage", "chiropractic",
           "meditation", "physical_therapy", "nutrition", "counseling"]
mind-body:
  boosts: ["yoga", "meditation", "counseling"]
holistic:
  boosts: ["acupuncture", "yoga", "massage", "meditation",
           "nutrition", "chiropractic"]
evidence-based:
  boosts: ["physician", "clinic", "physical_therapy"]
natural:
  boosts: ["acupuncture", "nutrition", "yoga", "meditation"]
```

### Category buckets (`app/scoring.py:28-34`)

```python
_MEDICAL_CATEGORIES = {"physician", "clinic", "physical_therapy"}
_WHOLE_HEALTH_CATEGORIES = {
    "acupuncture", "yoga", "meditation", "massage",
    "nutrition", "counseling", "chiropractic",
}
```

### Urgent safety keywords (`app/config/mappings.yaml:188-199`)

If any of these appear in `goal_outcomes` or `main_issue`, the response includes
a SAFETY warning directing the user to 911/emergency care:

```yaml
- chest pain
- difficulty breathing
- suicidal
- self-harm
- overdose
- stroke
- seizure
- severe bleeding
- loss of consciousness
- anaphylaxis
- allergic reaction severe
```

### To tune the ranking

Edit `app/config/weights.yaml` or `app/config/mappings.yaml`, commit, and
redeploy with `bash app/deploy.sh`. No code changes needed.
