import io

from app.ai.registry import get_ai_client_registry
from app.fhir.validator import FhirValidator
from app.main import app
from app.schemas.registry import get_schema_registry


def _install_fake_ai_client(monkeypatch, response):
    def fake_client(file_bytes, mime_type, schema, prompt_context):
        return response

    app.dependency_overrides[get_ai_client_registry] = lambda: {"gemini": fake_client}


def _install_fake_validator(monkeypatch):
    class _FakeValidator:
        def validate(self, resource):
            return None

    app.dependency_overrides.setdefault  # no-op to keep monkeypatch import used
    import app.api.extractions as extractions_module

    monkeypatch.setattr(extractions_module, "_build_fhir_validator", lambda: _FakeValidator())


def test_missing_user_id_header_returns_400(client):
    files = {"file": ("report.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")}
    response = client.post("/extractions", files=files, data={"schema_id": "lab_observation"})
    assert response.status_code == 400


def test_empty_user_id_header_returns_400(client):
    files = {"file": ("report.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")}
    response = client.post(
        "/extractions",
        files=files,
        data={"schema_id": "lab_observation"},
        headers={"X-Viome-User-Id": ""},
    )
    assert response.status_code == 400


def test_unknown_schema_id_returns_400(client):
    files = {"file": ("report.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")}
    response = client.post(
        "/extractions",
        files=files,
        data={"schema_id": "nope"},
        headers={"X-Viome-User-Id": "user-1"},
    )
    assert response.status_code == 400


def test_unsupported_file_type_returns_400(client):
    files = {"file": ("report.txt", io.BytesIO(b"hello"), "text/plain")}
    response = client.post(
        "/extractions",
        files=files,
        data={"schema_id": "lab_observation"},
        headers={"X-Viome-User-Id": "user-1"},
    )
    assert response.status_code == 400


def test_unknown_ai_model_header_returns_400(client):
    files = {"file": ("report.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")}
    response = client.post(
        "/extractions",
        files=files,
        data={"schema_id": "lab_observation"},
        headers={"X-Viome-User-Id": "user-1", "X-AI-Model": "not-a-model"},
    )
    assert response.status_code == 400


def test_get_unknown_job_returns_404(client):
    response = client.get("/extractions/does-not-exist")
    assert response.status_code == 404


def test_full_flow_returns_succeeded_job(client, monkeypatch):
    _install_fake_ai_client(
        monkeypatch,
        {
            "code": "2093-3",
            "display": "Cholesterol",
            "value": 180,
            "unit": "mg/dL",
            "effective_date": "2026-01-15",
        },
    )
    _install_fake_validator(monkeypatch)

    try:
        files = {"file": ("report.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")}
        create_response = client.post(
            "/extractions",
            files=files,
            data={"schema_id": "lab_observation"},
            headers={"X-Viome-User-Id": "user-1"},
        )
        assert create_response.status_code == 202
        job_id = create_response.json()["job_id"]

        status_response = client.get(f"/extractions/{job_id}")
        assert status_response.status_code == 200
        body = status_response.json()
        assert body["status"] == "succeeded"
        assert body["result"]["resourceType"] == "Observation"
        assert body["result"]["subject"] == {"reference": "Patient/user-1"}
    finally:
        app.dependency_overrides.clear()
