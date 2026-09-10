import json
import subprocess
import tempfile
from pathlib import Path

from fastapi import FastAPI, Request

app = FastAPI(title="HL7 FHIR Validator Sidecar")

IG_PATH = Path("/ig/output")
VALIDATOR_JAR = Path("/opt/validator_cli.jar")


@app.post("/validate")
async def validate(request: Request) -> dict:
    resource = await request.json()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
        json.dump(resource, tmp)
        tmp_path = tmp.name

    result = subprocess.run(
        [
            "java",
            "-jar",
            str(VALIDATOR_JAR),
            tmp_path,
            "-ig",
            str(IG_PATH),
            "-output",
            f"{tmp_path}.out.json",
            "-output-style",
            "json",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )

    issues: list[str] = []
    output_path = Path(f"{tmp_path}.out.json")
    if output_path.exists():
        outcome = json.loads(output_path.read_text())
        for issue in outcome.get("issues", []):
            if issue.get("severity") in ("error", "fatal"):
                issues.append(issue.get("message", "unknown validation error"))
    elif result.returncode != 0:
        issues.append(result.stderr.strip() or "validator_cli failed with no output")

    return {"valid": not issues, "issues": issues}
