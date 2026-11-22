"""Regression coverage for the CV draft, evidence, and replacement flow."""

import json
from io import BytesIO
from zipfile import ZipFile

from pydantic import SecretStr

from app.schemas.cv_parse import CvParseResult
from app.services import cv_parse_service, job_cv_evidence_service
from app.services.job_cv_evidence_service import EvidenceSelections

JOBS = "/api/v1/job-orders"
CANDIDATES = "/api/v1/candidates"
EXCERPT = "Built a FastAPI inventory service and deployed it with Docker."
JOB_REQUIREMENT = "Deploy FastAPI services with Docker"


def test_cv_draft_evidence_and_replacement(client, two_tenants, monkeypatch):
    tenant, other_tenant = two_tenants
    word_namespace = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    buffer = BytesIO()
    with ZipFile(buffer, "w") as document:
        document.writestr("[Content_Types].xml", "<Types/>")
        document.writestr(
            "word/document.xml",
            f'<w:document xmlns:w="{word_namespace}"><w:body>'
            f"<w:p><w:r><w:t>{EXCERPT}</w:t></w:r></w:p></w:body></w:document>",
        )
    upload = {"file": ("demo.docx", buffer.getvalue())}
    monkeypatch.setattr(cv_parse_service.settings, "gemini_api_key", None)
    assert client.post(f"{CANDIDATES}/cv/parse", headers=tenant, files=upload).status_code == 503

    monkeypatch.setattr(cv_parse_service.settings, "gemini_api_key", SecretStr("test-key"))

    def parse(schema, prompt, document, failure_message):
        assert schema is CvParseResult
        if "text" in document:
            assert EXCERPT in document["text"]
        else:
            assert document["inlineData"]["mimeType"] == "application/pdf"
        return CvParseResult(
            full_name="Demo Candidate", location="Pune", total_experience_years=3,
            skills=["FastAPI"], email=None, phone=None, current_role=None,
            professional_summary=None, evidence=[EXCERPT, "Invented excerpt"],
        )

    monkeypatch.setattr(cv_parse_service, "generate_json", parse)
    rejected = client.post(
        f"{CANDIDATES}/cv/parse", headers=tenant, files={"file": ("demo.txt", b"resume")}
    )
    assert rejected.status_code == 422
    parsed_pdf = client.post(
        f"{CANDIDATES}/cv/parse", headers=tenant,
        files={"file": ("demo.pdf", b"%PDF-1.4\n%%EOF\n")},
    )
    assert parsed_pdf.status_code == 200, parsed_pdf.text
    parsed = client.post(f"{CANDIDATES}/cv/parse", headers=tenant, files=upload)
    assert parsed.status_code == 200, parsed.text
    form = parsed.json()
    excerpts = form.pop("evidence")
    assert excerpts == [EXCERPT]

    created = client.post(CANDIDATES, headers=tenant, json=form)
    assert created.status_code == 201, created.text
    candidate_id = created.json()["id"]
    cv_url = f"{CANDIDATES}/{candidate_id}/cv"
    attached = client.post(cv_url, headers=tenant, files=upload, data={
        "evidence": json.dumps(excerpts),
    })
    assert attached.status_code == 200, attached.text

    form["full_name"] = "Other Demo Candidate"
    assert client.post(CANDIDATES, headers=tenant, json=form).status_code == 201
    job = client.post(JOBS, headers=tenant, json={
        "job_title": "FastAPI Developer", "location": "Pune", "min_experience_years": 1,
        "number_of_openings": 1, "required_skills": ["FastAPI"],
        "job_description": f"{JOB_REQUIREMENT}. Maintain API documentation.",
    })
    assert job.status_code == 201, job.text
    job_url = f"{JOBS}/{job.json()['id']}"

    def select_evidence(schema, prompt, document, failure_message):
        assert schema is EvidenceSelections
        request = json.loads(document["text"])
        assert JOB_REQUIREMENT in request["job_description"]
        assert request["candidates"] == [{"candidate_id": candidate_id, "excerpts": [EXCERPT]}]
        return EvidenceSelections.model_validate({"selections": [
            {"candidate_id": candidate_id, "excerpt_index": 3, "job_requirement": "FastAPI"},
            {"candidate_id": candidate_id, "excerpt_index": 0, "job_requirement": "Kubernetes"},
            {
                "candidate_id": candidate_id,
                "excerpt_index": 0,
                "job_requirement": JOB_REQUIREMENT.lower(),
            },
        ]})

    monkeypatch.setattr(job_cv_evidence_service, "generate_json", select_evidence)
    notes = client.post(f"{job_url}/cv-evidence", headers=tenant)
    assert notes.status_code == 200, notes.text
    assert notes.json() == [{
        "candidate_id": candidate_id,
        "excerpt": EXCERPT,
        "job_requirement": JOB_REQUIREMENT,
    }]
    assert client.post(f"{job_url}/cv-evidence", headers=other_tenant).status_code == 404
    assert client.get(f"{job_url}/matches", headers=tenant).json()["total"] == 2

    assert client.post(cv_url, headers=tenant, files=upload).status_code == 200
    assert client.post(f"{job_url}/cv-evidence", headers=tenant).json() == []
