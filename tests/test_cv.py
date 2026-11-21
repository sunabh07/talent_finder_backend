"""Story 2 - CV upload, validation, download and removal.

Minimal but genuinely well-formed fixtures: a real one-page PDF and a real
(empty) ZIP container for the DOCX. Validation reads magic bytes, so the
headers have to be honest.
"""

import io
import zipfile

from fastapi.testclient import TestClient

BASE = "/api/v1/candidates"

PDF_BYTES = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[]/Count 0>>endobj\n"
    b"trailer<</Root 1 0 R>>\n%%EOF\n"
)


def _docx_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", "<document/>")
    return buffer.getvalue()


DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _candidate(client: TestClient, headers: dict) -> int:
    response = client.post(
        BASE,
        json={
            "full_name": "Asha Rao",
            "location": "Bengaluru",
            "total_experience_years": "6",
            "skills": ["Python"],
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


# --- Happy path ------------------------------------------------------------


def test_upload_and_download_a_pdf(client: TestClient, tenant_a) -> None:
    candidate_id = _candidate(client, tenant_a)

    upload = client.post(
        f"{BASE}/{candidate_id}/cv",
        files={"file": ("asha-rao.pdf", PDF_BYTES, "application/pdf")},
        headers=tenant_a,
    )
    assert upload.status_code == 200, upload.text
    assert upload.json()["cv_mime_type"] == "application/pdf"
    assert upload.json()["cv_size_bytes"] == len(PDF_BYTES)

    download = client.get(f"{BASE}/{candidate_id}/cv", headers=tenant_a)
    assert download.status_code == 200
    assert download.content == PDF_BYTES
    assert download.headers["content-type"].startswith("application/pdf")
    assert "asha-rao.pdf" in download.headers["content-disposition"]


def test_upload_a_docx(client: TestClient, tenant_a) -> None:
    candidate_id = _candidate(client, tenant_a)
    response = client.post(
        f"{BASE}/{candidate_id}/cv",
        files={"file": ("cv.docx", _docx_bytes(), DOCX_MIME)},
        headers=tenant_a,
    )
    assert response.status_code == 200
    assert response.json()["cv_mime_type"] == DOCX_MIME


def test_details_and_stats_reflect_the_cv(client: TestClient, tenant_a) -> None:
    candidate_id = _candidate(client, tenant_a)
    client.post(
        f"{BASE}/{candidate_id}/cv",
        files={"file": ("cv.pdf", PDF_BYTES, "application/pdf")},
        headers=tenant_a,
    )

    detail = client.get(f"{BASE}/{candidate_id}", headers=tenant_a).json()
    assert detail["has_cv"] is True
    assert detail["cv_filename"] == "cv.pdf"
    assert "cv_data" not in detail

    assert client.get(f"{BASE}/stats", headers=tenant_a).json()["with_cv"] == 1


def test_uploading_again_replaces_the_previous_cv(client: TestClient, tenant_a) -> None:
    candidate_id = _candidate(client, tenant_a)
    client.post(
        f"{BASE}/{candidate_id}/cv",
        files={"file": ("first.pdf", PDF_BYTES, "application/pdf")},
        headers=tenant_a,
    )
    client.post(
        f"{BASE}/{candidate_id}/cv",
        files={"file": ("second.docx", _docx_bytes(), DOCX_MIME)},
        headers=tenant_a,
    )
    detail = client.get(f"{BASE}/{candidate_id}", headers=tenant_a).json()
    assert detail["cv_filename"] == "second.docx"
    assert detail["cv_mime_type"] == DOCX_MIME


def test_remove_a_cv(client: TestClient, tenant_a) -> None:
    candidate_id = _candidate(client, tenant_a)
    client.post(
        f"{BASE}/{candidate_id}/cv",
        files={"file": ("cv.pdf", PDF_BYTES, "application/pdf")},
        headers=tenant_a,
    )
    assert client.delete(f"{BASE}/{candidate_id}/cv", headers=tenant_a).status_code == 204

    detail = client.get(f"{BASE}/{candidate_id}", headers=tenant_a).json()
    assert detail["has_cv"] is False
    assert detail["cv_size_bytes"] is None
    assert client.get(f"{BASE}/{candidate_id}/cv", headers=tenant_a).status_code == 404


# --- Validation ------------------------------------------------------------


def test_disallowed_extension_is_rejected(client: TestClient, tenant_a) -> None:
    candidate_id = _candidate(client, tenant_a)
    response = client.post(
        f"{BASE}/{candidate_id}/cv",
        files={"file": ("resume.txt", b"plain text", "text/plain")},
        headers=tenant_a,
    )
    assert response.status_code == 422
    assert response.json()["error"]["details"]["received_extension"] == ".txt"


def test_a_renamed_file_is_caught_by_its_magic_bytes(client: TestClient, tenant_a) -> None:
    """A .pdf extension on something that is not a PDF must not be stored."""
    candidate_id = _candidate(client, tenant_a)
    response = client.post(
        f"{BASE}/{candidate_id}/cv",
        files={"file": ("malware.pdf", b"MZ\x90\x00 not a pdf", "application/pdf")},
        headers=tenant_a,
    )
    assert response.status_code == 422
    assert "not a readable PDF or DOCX" in response.json()["error"]["message"]


def test_extension_and_content_must_agree(client: TestClient, tenant_a) -> None:
    candidate_id = _candidate(client, tenant_a)
    response = client.post(
        f"{BASE}/{candidate_id}/cv",
        files={"file": ("actually-a-pdf.docx", PDF_BYTES, DOCX_MIME)},
        headers=tenant_a,
    )
    assert response.status_code == 422
    assert response.json()["error"]["details"]["detected"] == ".pdf"


def test_empty_file_is_rejected(client: TestClient, tenant_a) -> None:
    candidate_id = _candidate(client, tenant_a)
    response = client.post(
        f"{BASE}/{candidate_id}/cv",
        files={"file": ("empty.pdf", b"", "application/pdf")},
        headers=tenant_a,
    )
    assert response.status_code == 422


def test_oversized_file_is_rejected(client: TestClient, tenant_a, monkeypatch) -> None:
    from app.core import files as files_module

    monkeypatch.setattr(files_module.settings, "max_cv_size_mb", 0.0001, raising=False)
    candidate_id = _candidate(client, tenant_a)
    response = client.post(
        f"{BASE}/{candidate_id}/cv",
        files={"file": ("big.pdf", PDF_BYTES, "application/pdf")},
        headers=tenant_a,
    )
    assert response.status_code == 422
    assert "max_bytes" in response.json()["error"]["details"]


def test_path_components_are_stripped_from_the_filename(client: TestClient, tenant_a) -> None:
    candidate_id = _candidate(client, tenant_a)
    response = client.post(
        f"{BASE}/{candidate_id}/cv",
        files={"file": (r"C:\Users\someone\secret\cv.pdf", PDF_BYTES, "application/pdf")},
        headers=tenant_a,
    )
    assert response.status_code == 200
    assert response.json()["cv_filename"] == "cv.pdf"


# --- Tenant isolation ------------------------------------------------------


def test_another_tenant_cannot_upload_a_cv(client: TestClient, two_tenants) -> None:
    a, b = two_tenants
    candidate_id = _candidate(client, a)
    response = client.post(
        f"{BASE}/{candidate_id}/cv",
        files={"file": ("cv.pdf", PDF_BYTES, "application/pdf")},
        headers=b,
    )
    assert response.status_code == 404


def test_another_tenant_cannot_download_a_cv(client: TestClient, two_tenants) -> None:
    a, b = two_tenants
    candidate_id = _candidate(client, a)
    client.post(
        f"{BASE}/{candidate_id}/cv",
        files={"file": ("cv.pdf", PDF_BYTES, "application/pdf")},
        headers=a,
    )
    assert client.get(f"{BASE}/{candidate_id}/cv", headers=b).status_code == 404


def test_downloading_when_no_cv_exists_returns_404(client: TestClient, tenant_a) -> None:
    candidate_id = _candidate(client, tenant_a)
    assert client.get(f"{BASE}/{candidate_id}/cv", headers=tenant_a).status_code == 404
