import asyncio
import subprocess
import time
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request

IG_PATH = Path("/ig/output")
VALIDATOR_JAR = Path("/opt/validator_cli.jar")

# The validator runs as a persistent in-process HTTP server instead of a
# fresh `java -jar validator_cli.jar <file>` subprocess per request - the
# per-request JVM boot + IG reload cost ~10s each, which made validating a
# multi-observation document (one call per Observation) take minutes.
INTERNAL_PORT = 8092
INTERNAL_BASE_URL = f"http://127.0.0.1:{INTERNAL_PORT}"
STARTUP_TIMEOUT_SECONDS = 120
STARTUP_POLL_INTERVAL_SECONDS = 2.0
PROBE_RESOURCE = {"resourceType": "Observation", "status": "final"}

_validator_process: subprocess.Popen | None = None


def _start_validator_server() -> subprocess.Popen:
    return subprocess.Popen(
        [
            "java",
            "-jar",
            str(VALIDATOR_JAR),
            "server",
            str(INTERNAL_PORT),
            # Our IG (fhir-ig/sushi-config.yaml) declares fhirVersion 4.0.1;
            # without this the validator silently defaults to R5 and
            # validates against the wrong base spec entirely.
            "-version",
            "4.0",
            "-ig",
            str(IG_PATH),
            # No terminology-server validation for v1 (see spec non-goals).
            "-tx",
            "n/a",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


async def _wait_until_ready(client: httpx.AsyncClient) -> None:
    deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        try:
            response = await client.post(
                f"{INTERNAL_BASE_URL}/validateResource", json=PROBE_RESOURCE, timeout=5.0
            )
            if response.status_code == 200:
                return
        except httpx.HTTPError:
            pass
        await asyncio.sleep(STARTUP_POLL_INTERVAL_SECONDS)
    raise RuntimeError(
        f"validator server did not become ready within {STARTUP_TIMEOUT_SECONDS}s"
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _validator_process
    _validator_process = _start_validator_server()
    async with httpx.AsyncClient() as startup_client:
        await _wait_until_ready(startup_client)
    yield
    if _validator_process is not None:
        _validator_process.terminate()
        try:
            _validator_process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            _validator_process.kill()


app = FastAPI(title="HL7 FHIR Validator Sidecar", lifespan=lifespan)
_http_client = httpx.AsyncClient(timeout=30.0)


@app.post("/validate")
async def validate(request: Request) -> dict:
    resource = await request.json()

    try:
        response = await _http_client.post(
            f"{INTERNAL_BASE_URL}/validateResource", json=resource
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"validator server error: {exc}") from exc

    outcome = response.json()

    issues: list[str] = []
    # The validator's OperationOutcome carries findings under "issue"
    # (singular) - each with the human-readable message under
    # issue.details.text, not a top-level "message" field.
    for issue in outcome.get("issue", []):
        if issue.get("severity") in ("error", "fatal"):
            text = issue.get("details", {}).get("text", "unknown validation error")
            issues.append(text)

    return {"valid": not issues, "issues": issues}
