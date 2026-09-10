# Viome Document Intelligence

FastAPI service that extracts structured lab-result data from uploaded
reports (PDF/JPEG/PNG) via Gemini, maps it into a FHIR `Observation`, and
validates it against a custom FHIR profile.

## Local development

    pip install -r requirements.txt
    cp .env.example .env  # fill in GEMINI_API_KEY
    uvicorn app.main:app --reload

## Running with Docker (app + FHIR validator sidecar)

    docker compose up --build

## Tests

    pytest -v

## API

- `POST /extractions` — multipart `file` + `schema_id` fields, headers
  `X-Viome-User-Id` (required) and `X-AI-Model` (optional, defaults to
  `gemini`). Returns `202 {"job_id": "..."}`.
- `GET /extractions/{job_id}` — returns job status and, once `succeeded`,
  the FHIR `Observation` result.

See `docs/superpowers/specs/2026-09-10-document-intelligence-design.md`
for the full design.
