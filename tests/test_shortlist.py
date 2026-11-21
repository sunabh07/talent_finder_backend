"""Story 3.4 and 3.5 - shortlisting and the Submission List."""

from fastapi.testclient import TestClient

JOBS = "/api/v1/job-orders"
CANDIDATES = "/api/v1/candidates"
SUBMISSIONS = "/api/v1/submissions"


def _job(client: TestClient, headers: dict, title="Senior Backend Engineer") -> dict:
    return client.post(
        JOBS,
        json={
            "job_title": title,
            "client_name": "Northwind",
            "location": "Bengaluru",
            "min_experience_years": "5",
            "number_of_openings": 2,
            "required_skills": ["Python", "FastAPI"],
        },
        headers=headers,
    ).json()


def _candidate(client: TestClient, headers: dict, name="Asha Rao") -> dict:
    return client.post(
        CANDIDATES,
        json={
            "full_name": name,
            "location": "Bengaluru",
            "total_experience_years": "6",
            "skills": ["Python"],
        },
        headers=headers,
    ).json()


def _shortlist(client: TestClient, headers: dict, job_id: int, candidate_id: int):
    return client.post(
        f"{JOBS}/{job_id}/shortlist", json={"candidate_id": candidate_id}, headers=headers
    )


# --- Shortlisting ----------------------------------------------------------


def test_shortlist_creates_one_submission_with_status_shortlisted(
    client: TestClient, tenant_a
) -> None:
    job = _job(client, tenant_a)
    candidate = _candidate(client, tenant_a)

    response = _shortlist(client, tenant_a, job["id"], candidate["id"])
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "Shortlisted"
    assert body["already_shortlisted"] is False
    assert client.get(SUBMISSIONS, headers=tenant_a).json()["total"] == 1


def test_shortlisting_twice_is_idempotent(client: TestClient, tenant_a) -> None:
    """ "Repeating shortlist does not create duplicates."

    Handled by ON CONFLICT DO NOTHING against the unique constraint, so a
    double click cannot race into an IntegrityError.
    """
    job = _job(client, tenant_a)
    candidate = _candidate(client, tenant_a)

    first = _shortlist(client, tenant_a, job["id"], candidate["id"]).json()
    second = _shortlist(client, tenant_a, job["id"], candidate["id"]).json()

    assert second["already_shortlisted"] is True
    assert second["submission_id"] == first["submission_id"]
    assert client.get(SUBMISSIONS, headers=tenant_a).json()["total"] == 1


def test_shortlisting_appears_in_the_job_orders_shortlisted_section(
    client: TestClient, tenant_a
) -> None:
    job = _job(client, tenant_a)
    candidate = _candidate(client, tenant_a)
    _shortlist(client, tenant_a, job["id"], candidate["id"])

    detail = client.get(f"{JOBS}/{job['id']}", headers=tenant_a).json()
    assert [row["full_name"] for row in detail["shortlisted"]] == ["Asha Rao"]
    assert detail["shortlisted"][0]["status"] == "Shortlisted"


def test_match_rows_report_shortlisted_state(client: TestClient, tenant_a) -> None:
    """The Shortlist button needs to render as 'Shortlisted' after the click."""
    job = _job(client, tenant_a)
    candidate = _candidate(client, tenant_a)

    before = client.get(f"{JOBS}/{job['id']}/matches", headers=tenant_a).json()
    assert before["items"][0]["is_shortlisted"] is False

    _shortlist(client, tenant_a, job["id"], candidate["id"])

    after = client.get(f"{JOBS}/{job['id']}/matches", headers=tenant_a).json()
    assert after["items"][0]["is_shortlisted"] is True


def test_shortlisting_appears_on_the_candidate_details_page(client: TestClient, tenant_a) -> None:
    job = _job(client, tenant_a)
    candidate = _candidate(client, tenant_a)
    _shortlist(client, tenant_a, job["id"], candidate["id"])

    detail = client.get(f"{CANDIDATES}/{candidate['id']}", headers=tenant_a).json()
    assert len(detail["submissions"]) == 1
    assert detail["submissions"][0]["job_title"] == "Senior Backend Engineer"
    assert detail["submissions"][0]["job_order_id"] == job["id"]
    assert detail["submissions"][0]["status"] == "Shortlisted"


# --- Cross-tenant rejection -------------------------------------------------


def test_shortlisting_a_foreign_candidate_is_rejected(client: TestClient, two_tenants) -> None:
    a, b = two_tenants
    job = _job(client, a)
    foreign = _candidate(client, b, "Foreign Person")

    response = _shortlist(client, a, job["id"], foreign["id"])
    assert response.status_code == 404
    # No submission was created in either tenant.
    assert client.get(SUBMISSIONS, headers=a).json()["total"] == 0
    assert client.get(SUBMISSIONS, headers=b).json()["total"] == 0


def test_shortlisting_against_a_foreign_job_order_is_rejected(
    client: TestClient, two_tenants
) -> None:
    a, b = two_tenants
    foreign_job = _job(client, b)
    candidate = _candidate(client, a)

    assert _shortlist(client, a, foreign_job["id"], candidate["id"]).status_code == 404
    assert client.get(SUBMISSIONS, headers=a).json()["total"] == 0


def test_shortlisting_an_unknown_candidate_is_404(client: TestClient, tenant_a) -> None:
    job = _job(client, tenant_a)
    assert _shortlist(client, tenant_a, job["id"], 999999).status_code == 404


# --- Submission List --------------------------------------------------------


def test_submission_list_shows_job_candidate_and_status(client: TestClient, tenant_a) -> None:
    job = _job(client, tenant_a)
    candidate = _candidate(client, tenant_a)
    _shortlist(client, tenant_a, job["id"], candidate["id"])

    row = client.get(SUBMISSIONS, headers=tenant_a).json()["items"][0]
    assert row["job_title"] == "Senior Backend Engineer"
    assert row["candidate_name"] == "Asha Rao"
    assert row["status"] == "Shortlisted"
    assert row["job_order_id"] == job["id"]
    assert row["candidate_id"] == candidate["id"]


def test_submission_list_is_tenant_scoped(client: TestClient, two_tenants) -> None:
    a, b = two_tenants
    job = _job(client, a)
    candidate = _candidate(client, a)
    _shortlist(client, a, job["id"], candidate["id"])

    assert client.get(SUBMISSIONS, headers=a).json()["total"] == 1
    assert client.get(SUBMISSIONS, headers=b).json()["total"] == 0


def test_submission_search_sort_and_pagination(client: TestClient, tenant_a) -> None:
    job_one = _job(client, tenant_a, title="Backend Engineer")
    job_two = _job(client, tenant_a, title="Frontend Engineer")
    for index in range(3):
        candidate = _candidate(client, tenant_a, f"Person {index}")
        _shortlist(client, tenant_a, job_one["id"], candidate["id"])
    extra = _candidate(client, tenant_a, "Zara Khan")
    _shortlist(client, tenant_a, job_two["id"], extra["id"])

    assert client.get(SUBMISSIONS, params={"q": "frontend"}, headers=tenant_a).json()["total"] == 1
    assert client.get(SUBMISSIONS, params={"q": "Zara"}, headers=tenant_a).json()["total"] == 1

    names = [
        row["candidate_name"]
        for row in client.get(
            SUBMISSIONS,
            params={"sort_by": "candidate_name", "sort_dir": "asc"},
            headers=tenant_a,
        ).json()["items"]
    ]
    assert names == sorted(names)

    page = client.get(SUBMISSIONS, params={"page": 2, "page_size": 3}, headers=tenant_a).json()
    assert page["total"] == 4 and len(page["items"]) == 1


def test_submission_stats(client: TestClient, tenant_a) -> None:
    job = _job(client, tenant_a)
    for index in range(2):
        candidate = _candidate(client, tenant_a, f"Person {index}")
        _shortlist(client, tenant_a, job["id"], candidate["id"])

    stats = client.get(f"{SUBMISSIONS}/stats", headers=tenant_a).json()
    assert stats == {"total": 2, "added_this_week": 2, "job_orders_with_submissions": 1}


# --- Cascades ----------------------------------------------------------------


def test_deleting_a_job_order_removes_its_submissions(client: TestClient, tenant_a) -> None:
    job = _job(client, tenant_a)
    candidate = _candidate(client, tenant_a)
    _shortlist(client, tenant_a, job["id"], candidate["id"])

    client.delete(f"{JOBS}/{job['id']}", headers=tenant_a)
    assert client.get(SUBMISSIONS, headers=tenant_a).json()["total"] == 0
    # The candidate survives; only the submission went.
    assert client.get(f"{CANDIDATES}/{candidate['id']}", headers=tenant_a).status_code == 200


def test_deleting_a_candidate_removes_their_submissions(client: TestClient, tenant_a) -> None:
    job = _job(client, tenant_a)
    candidate = _candidate(client, tenant_a)
    _shortlist(client, tenant_a, job["id"], candidate["id"])

    client.delete(f"{CANDIDATES}/{candidate['id']}", headers=tenant_a)
    assert client.get(SUBMISSIONS, headers=tenant_a).json()["total"] == 0
    assert client.get(f"{JOBS}/{job['id']}", headers=tenant_a).json()["shortlisted"] == []
