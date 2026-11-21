"""Story 3.3 - the ranked Matching Candidates list.

This is the graded core of the assignment, so these tests are written against
the acceptance criteria almost word for word.
"""

from fastapi.testclient import TestClient

JOBS = "/api/v1/job-orders"
CANDIDATES = "/api/v1/candidates"

# The job requires four skills. Each candidate below matches a known number of
# them, which is what makes the expected ordering unambiguous.
REQUIRED = ["Python", "FastAPI", "PostgreSQL", "Docker"]


def _job(client: TestClient, headers: dict, **overrides) -> dict:
    payload = {
        "job_title": "Senior Backend Engineer",
        "location": "Bengaluru",
        "min_experience_years": "5",
        "number_of_openings": 2,
        "required_skills": REQUIRED,
    }
    payload.update(overrides)
    response = client.post(JOBS, json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def _candidate(client: TestClient, headers: dict, name: str, skills: list[str], years="6"):
    response = client.post(
        CANDIDATES,
        json={
            "full_name": name,
            "location": "Bengaluru",
            "total_experience_years": years,
            "skills": skills,
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _matches(client: TestClient, headers: dict, job_id: int, **params) -> dict:
    response = client.get(f"{JOBS}/{job_id}/matches", params=params, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


# --- The headline acceptance criterion ------------------------------------


def test_ranking_is_three_two_one_and_excludes_zero(client: TestClient, tenant_a) -> None:
    """ "With a job requiring four skills and candidates matching 3, 2, 1 and 0,
    results are 3 -> 2 -> 1; the zero-match candidate is absent."
    """
    job = _job(client, tenant_a)
    _candidate(client, tenant_a, "Three Match", ["Python", "FastAPI", "PostgreSQL", "React"])
    _candidate(client, tenant_a, "Two Match", ["Python", "Docker", "AWS"])
    _candidate(client, tenant_a, "One Match", ["Python", "Java"])
    _candidate(client, tenant_a, "Zero Match", ["Angular", "PHP"])

    body = _matches(client, tenant_a, job["id"])

    assert [item["full_name"] for item in body["items"]] == [
        "Three Match",
        "Two Match",
        "One Match",
    ]
    assert [item["match_count"] for item in body["items"]] == [3, 2, 1]
    assert body["total"] == 3
    assert "Zero Match" not in [item["full_name"] for item in body["items"]]


def test_cross_tenant_candidates_never_appear(client: TestClient, two_tenants) -> None:
    """ "Candidates are matched only within the same tenant as the job order."

    The foreign-tenant candidate here matches *every* required skill, so if
    scoping were broken they would rank first and be impossible to miss.
    """
    a, b = two_tenants
    job = _job(client, a)
    _candidate(client, a, "Own Tenant", ["Python"])
    _candidate(client, b, "Other Tenant Perfect", REQUIRED)

    names = [item["full_name"] for item in _matches(client, a, job["id"])["items"]]
    assert names == ["Own Tenant"]


def test_matched_skill_names_are_returned(client: TestClient, tenant_a) -> None:
    job = _job(client, tenant_a)
    _candidate(client, tenant_a, "Asha Rao", ["Python", "Docker", "React"])

    row = _matches(client, tenant_a, job["id"])["items"][0]
    assert sorted(row["matched_skills"]) == ["Docker", "Python"]
    assert row["match_count"] == 2
    # The non-required skill must not be reported as a match.
    assert "React" not in row["matched_skills"]


def test_ties_are_broken_deterministically_by_name(client: TestClient, tenant_a) -> None:
    """Equal counts must produce a stable order, or pagination breaks."""
    job = _job(client, tenant_a)
    for name in ("Charlie", "Alice", "Bob"):
        _candidate(client, tenant_a, name, ["Python", "FastAPI"])

    first = [i["full_name"] for i in _matches(client, tenant_a, job["id"])["items"]]
    second = [i["full_name"] for i in _matches(client, tenant_a, job["id"])["items"]]
    assert first == ["Alice", "Bob", "Charlie"]
    assert first == second


def test_experience_does_not_affect_ranking(client: TestClient, tenant_a) -> None:
    """Minimum experience is an indicator, never a filter or a sort key."""
    job = _job(client, tenant_a, min_experience_years="5")
    # Fewer years but more matched skills must still rank first.
    _candidate(client, tenant_a, "Junior Strong", ["Python", "FastAPI", "Docker"], years="1")
    _candidate(client, tenant_a, "Senior Weak", ["Python"], years="20")

    items = _matches(client, tenant_a, job["id"])["items"]
    assert [i["full_name"] for i in items] == ["Junior Strong", "Senior Weak"]
    assert items[0]["meets_min_experience"] is False
    assert items[1]["meets_min_experience"] is True
    # Crucially, the ineligible candidate is still listed.
    assert len(items) == 2


def test_skill_aliases_count_as_matches(client: TestClient, tenant_a, seeded_skills) -> None:
    """Both sides resolve through the same vocabulary, so js == JavaScript."""
    job = _job(client, tenant_a, required_skills=["JavaScript", "React"])
    _candidate(client, tenant_a, "Alias User", ["js", "reactjs"])

    row = _matches(client, tenant_a, job["id"])["items"][0]
    assert row["match_count"] == 2


def test_duplicate_skill_input_cannot_inflate_the_count(
    client: TestClient, tenant_a, seeded_skills
) -> None:
    """COUNT(DISTINCT ...) guards against a candidate gaming the ranking."""
    job = _job(client, tenant_a)
    _candidate(client, tenant_a, "Repeater", ["Python", "python", "  PYTHON  "])

    row = _matches(client, tenant_a, job["id"])["items"][0]
    assert row["match_count"] == 1


def test_matches_include_the_required_skill_summary(client: TestClient, tenant_a) -> None:
    job = _job(client, tenant_a)
    body = _matches(client, tenant_a, job["id"])
    assert body["summary"]["required_skill_count"] == 4
    assert sorted(s["name"] for s in body["summary"]["required_skills"]) == sorted(REQUIRED)


def test_matches_are_paginated(client: TestClient, tenant_a) -> None:
    job = _job(client, tenant_a)
    for index in range(5):
        _candidate(client, tenant_a, f"Person {index}", ["Python"])

    page = _matches(client, tenant_a, job["id"], page=2, page_size=2)
    assert page["total"] == 5
    assert page["total_pages"] == 3
    assert len(page["items"]) == 2


def test_a_job_with_no_matching_candidates_returns_empty(client: TestClient, tenant_a) -> None:
    job = _job(client, tenant_a)
    _candidate(client, tenant_a, "Unrelated", ["Angular"])
    body = _matches(client, tenant_a, job["id"])
    assert body["total"] == 0
    assert body["items"] == []


def test_matching_another_tenants_job_order_is_404(client: TestClient, two_tenants) -> None:
    a, b = two_tenants
    job = _job(client, a)
    assert client.get(f"{JOBS}/{job['id']}/matches", headers=b).status_code == 404
