# Viome Document Intelligence — Design

Date: 2026-09-10
Status: Approved for planning

## Purpose

A FastAPI service that ingests lab/diagnostic report files (PDF, JPEG, PNG),
sends them to Gemini to extract structured data, validates and converts that
data into a FHIR-compliant resource, and returns it to the caller. The
service is scoped to Viome-internal callers and one user (patient) per
request, identified via a required header.

## Non-goals (v1)

- No persistence of uploaded files or results beyond the life of the job
  (no DB, no object storage).
- No authentication/authorization (trusted internal network only).
- No durable job queue (no Redis/Celery) — in-memory job store via FastAPI
  `BackgroundTasks`. Explicitly flagged as a follow-up once volume or
  multi-worker deployment requires it (in-memory state doesn't survive
  restarts and doesn't work across multiple app instances/workers).
- No terminology-server validation (LOINC/SNOMED code binding checks) —
  the HL7 validator runs in offline/structural mode for v1.
- Only one FHIR resource type is produced (`Observation`); multi-resource
  output (e.g. `DiagnosticReport` bundles) is future work.

## High-level flow

```
Client                     FastAPI app                    Gemini          HL7 Validator
  |  POST /extractions        |                               |                 |
  |  (file, schema_id,        |                               |                 |
  |   X-Viome-User-Id)        |                               |                 |
  |--------------------------->|                               |                 |
  |                            | validate file type/size,     |                 |
  |                            | schema_id, header             |                 |
  |                            | create job (pending)          |                 |
  |  202 {job_id}              | enqueue background task       |                 |
  |<---------------------------|                               |                 |
  |                            |----(1) send file + prompt---->|                 |
  |                            |<---(2) minimal JSON------------|                 |
  |                            | validate vs extraction schema |                 |
  |                            | (retry w/ feedback, up to N)  |                 |
  |                            | map minimal JSON -> Observation                |
  |                            |----(3) validate resource------------------------>|
  |                            |<---(4) issues / OK--------------------------------|
  |                            | store result (succeeded/failed)               |
  |  GET /extractions/{id}     |                               |                 |
  |--------------------------->|                               |                 |
  |  200 {status, result?}     |                               |                 |
  |<---------------------------|                               |                 |
```

## API

### `POST /extractions`

- Multipart form: `file` (PDF/JPEG/PNG, size-limited via config), `schema_id`
  (string, must match a registered extraction schema).
- Header: `X-Viome-User-Id` (required, non-empty). Missing/empty → `400`.
- Validates file content-type/extension and size before enqueueing.
- Unknown `schema_id` → `400`.
- On success: `202 Accepted`, body `{"job_id": "<uuid>"}`.

### `GET /extractions/{job_id}`

- Unknown `job_id` → `404`.
- Body: `{"job_id", "status": "pending"|"processing"|"succeeded"|"failed", "result": <FHIR Observation JSON> | null, "error": {"reason": str, "detail": ...} | null}`.

## Two-schema pipeline

Gemini is not asked to produce FHIR directly. Two schemas are involved:

1. **Extraction schema** — a plain JSON Schema file per report type
   (`app/schemas/*.extract.schema.json`), describing the minimal, flat data
   Gemini should return (e.g. `{code, display, value, unit, effective_date}`
   for a single lab observation). `schema_id` in the request selects this
   schema. Kept intentionally simple/cheap to validate so the retry loop
   below is fast and Gemini's job is easy.
2. **FHIR profile** — authored in FHIR Shorthand (FSH) under `fhir-ig/`,
   compiled by SUSHI into an Implementation Guide package (StructureDefinitions).
   For v1, everything maps to a single custom `Observation` profile. This is
   the authoritative output shape, validated by the official HL7 FHIR
   validator (`validator_cli.jar`), not by application code.

A **mapper** (`app/fhir/mapper.py`) converts a validated minimal JSON object
into a FHIR `Observation` resource dict, one mapper function per extraction
schema. The mapper sets `Observation.subject = {"reference": "Patient/<X-Viome-User-Id>"}`
so every produced resource is traceable to the user the request was made for,
even though no `Patient` resource is persisted or created.

### Why split extraction from FHIR validation

Gemini is asked to produce the smallest, least ambiguous JSON possible —
this keeps the retry-with-feedback loop (below) fast and the failure modes
easy to explain back to the model. FHIR structural rigor (cardinality,
invariants, custom profile constraints) is enforced deterministically afterward
by the mapper + HL7 validator, not by hoping Gemini emits valid FHIR directly.

## Gemini integration & retry-with-feedback

`app/ai/gemini/client.py` wraps the Gemini SDK:

- `extract(file_bytes, mime_type, schema: dict, prompt_context) -> dict`
- Uses Gemini's structured/JSON output mode, passing the extraction schema
  so the model is constrained toward the right shape.
- Transport-level errors (timeout, 5xx) are retried with backoff
  (separate, small retry budget) before failing the job.

Retry-with-feedback loop (`app/jobs/worker.py`):

1. Call Gemini with the base prompt for `schema_id`.
2. Validate the returned JSON against the extraction schema
   (`jsonschema` library).
3. If invalid, re-prompt Gemini with the original file plus the validation
   errors appended, asking it to correct its output.
4. Repeat up to `MAX_EXTRACTION_RETRIES` (config, default 3). If still
   invalid, job fails with reason `extraction_validation_failed` and the
   last validation errors attached.

## FHIR validation service

The HL7 FHIR validator has meaningful JVM cold-start cost, so it runs as a
**persistent sidecar service** (`validator_cli.jar -server` mode, wired up in
`docker-compose.yml`, loaded with the IG package built from `fhir-ig/`),
called by `app/fhir/validator.py` over HTTP per request. This avoids
per-request JVM startup.

Build-time step: `fhir-ig/` (FSH source + `sushi-config.yaml`) is compiled by
SUSHI into the IG package the validator service loads at startup. This is a
Docker build step, not a per-request cost — SUSHI (Node.js) is only needed
in the image build, not at runtime.

## Job store

`app/jobs/store.py` — an in-memory store (dict guarded by an `asyncio.Lock`)
holding job state: `job_id`, `status`, `user_id`, `schema_id`, `result`,
`error`, timestamps. `app/jobs/worker.py` is the function passed to FastAPI's
`BackgroundTasks`, driving a job through Gemini → validate/retry → map →
FHIR-validate → finalize.

This is explicitly a v1 simplification (see Non-goals) — swapping in a
durable queue later means replacing `JobStore`'s implementation behind the
same interface (`create`, `update`, `get`), not rewriting callers.

## Error handling

| Condition | HTTP / Job outcome | Reason code |
|---|---|---|
| Unsupported file type / oversized file | `400` at upload | — |
| Unknown `schema_id` | `400` at upload | — |
| Missing/empty `X-Viome-User-Id` | `400` at upload | — |
| Unknown `job_id` on GET | `404` | — |
| Gemini transport error (after retries) | job `failed` | `gemini_unavailable` |
| Extraction schema validation fails after `MAX_EXTRACTION_RETRIES` | job `failed` | `extraction_validation_failed` |
| Mapper cannot build a resource from valid minimal JSON | job `failed` | `mapping_failed` |
| HL7 validator rejects the mapped resource | job `failed` | `fhir_validation_failed` |
| HL7 validator service unreachable | job `failed` | `validator_unavailable` |

FHIR profile validation failures are **terminal**, not retried through
Gemini — they indicate a mapper bug or a real edge case in already-valid
extracted data, not something re-prompting the model fixes.

## Project structure

```
.
├── app/
│   ├── main.py
│   ├── api/
│   │   └── extractions.py        # POST/GET, reads X-Viome-User-Id
│   ├── ai/
│   │   └── gemini/
│   │       ├── client.py
│   │       └── prompts.py
│   ├── schemas/
│   │   ├── registry.py            # loads *.extract.schema.json at startup
│   │   └── *.extract.schema.json
│   ├── fhir/
│   │   ├── mapper.py               # minimal JSON -> FHIR Observation dict
│   │   └── validator.py            # calls HL7 validator service over HTTP
│   ├── jobs/
│   │   ├── store.py                # in-memory job state
│   │   └── worker.py               # orchestrates the pipeline
│   ├── models/
│   │   └── api.py                  # Pydantic request/response models
│   └── core/
│       └── config.py               # settings: Gemini key, retry counts,
│                                    # allowed file types/size, validator URL
├── fhir-ig/                         # FSH source + sushi-config.yaml
│   ├── sushi-config.yaml
│   └── input/fsh/observation.fsh
├── tests/
├── Dockerfile                       # app image
├── docker-compose.yml               # app + validator sidecar
├── requirements.txt
├── pyproject.toml                   # project metadata, tool config (ruff/pytest)
├── .env.example
├── .gitignore
└── README.md
```

Dependency management: plain `pip` + `requirements.txt` (no Poetry/uv).
`pyproject.toml` holds project metadata and tool configuration only.

## Testing

- **Unit tests**: schema registry loading, Gemini client (mocked SDK), mapper
  (minimal JSON → FHIR dict) with fixtures per extraction schema, and the
  retry-with-feedback loop logic in isolation.
- **Integration tests**: `docker-compose` brings up the app + HL7 validator
  sidecar; a fixture file is driven through `POST /extractions` → poll
  `GET /extractions/{id}` → assert on the final FHIR `Observation`, using a
  mocked/fake Gemini response (no live Gemini calls in CI).
- A separate manual/smoke script (not part of CI) exercises the real Gemini
  API for sanity-checking prompts against live behavior.

## Open items for follow-up (explicitly deferred)

- Durable job queue (Redis/Celery or Postgres-backed) once restart-survival
  or multi-worker deployment is needed.
- Persistence of files/results (DB and/or object storage) if audit trail or
  history is required.
- Authentication (API key or similar) before any non-trusted-network exposure.
- Terminology-server-backed validation (LOINC/SNOMED code binding).
- Support for additional FHIR resource types beyond `Observation`.
