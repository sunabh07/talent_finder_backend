# Talent Finder — Backend API

Multi-tenant recruiter portal API. A recruiter maintains candidates and job orders within a
tenant, and opens a job order to see same-tenant candidates **ranked by how many required skills
they match**.

Frontend: [`talent_finder_frontend`](https://github.com/sunabh07/talent_finder_frontend)

---

## Stack

FastAPI · Python 3.11 · SQLAlchemy 2.x (sync) · Alembic · Pydantic v2 · PostgreSQL 18 (`psycopg` 3)

The assignment names Node/Express as preferred while allowing "your expertise tech stack".
FastAPI was chosen because Pydantic, SQLAlchemy and Alembic map almost one-to-one onto the
`routes → controllers → services → repositories` separation the assignment grades.

---

## Setup

### 1. Database

```powershell
psql -U postgres -c "CREATE ROLE talentfinder WITH LOGIN PASSWORD 'talentfinder_dev';"
```

```powershell
psql -U postgres -c "CREATE DATABASE talentfinder OWNER talentfinder; CREATE DATABASE talentfinder_test OWNER talentfinder;"
```

### 2. Install

```powershell
python -m venv .venv; .\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

### 3. Configure

```powershell
Copy-Item .env.example .env
```

**`.env` is gitignored and must never be committed.**

### 4. Migrate and seed

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
```

```powershell
.\.venv\Scripts\python.exe -m scripts.seed --reset
```

Seeds 3 tenants, 53 skills, 31 aliases, 6 candidates, 4 job orders, 3 submissions. The demo job
requires four skills and its tenant's candidates match exactly 3, 2, 1 and 0 of them, so the
ranked list is visibly correct on first run. Idempotent — running it twice creates nothing new.

### 5. Run

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Interactive API docs at <http://127.0.0.1:8000/docs>.

### 6. Test

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

139 tests. The suite drops and re-migrates `talentfinder_test` every run, so it also proves the
migrations work on a clean database.

---

## Architecture

```
app/
  main.py          application factory
  core/            config · database · deps (tenant scope) · errors
                   pagination · normalization · files
  models/          SQLAlchemy models, one module per aggregate
  schemas/         Pydantic request/response models
  repositories/    all SQL lives here
  services/        business rules, transaction boundary
  controllers/     entity ↔ schema mapping
  api/v1/routes/   thin HTTP layer
alembic/versions/  migrations
scripts/seed.py    idempotent demo data
tests/             pytest, against real PostgreSQL
```

| Layer | May do | Must not do |
|---|---|---|
| Route | Path, status codes, `response_model`, dependencies | Contain logic or build queries |
| Controller | Unpack requests, call the service, map to response schemas | Build queries, enforce rules |
| Service | Business rules, raise domain errors, **own the transaction** | Import FastAPI, build SQL |
| Repository | Build and execute SQL | Commit, enforce business rules |

Because services never import FastAPI, the seed script and the tests drive the same rules with no
web server. Because only repositories build SQL, an unscoped query has one place it could be
written.

---

## Multi-tenancy

Tenant scope arrives as an **`X-Tenant-ID` header**, resolved by a single dependency
(`app/core/deps.py:get_tenant_scope`). Every tenant-owned repository method takes that tenant as
a **required argument**, so an unscoped query is a missing-parameter error, not a silent leak.

Underneath, `submissions` uses **composite foreign keys**:

```sql
candidates   UNIQUE (tenant_id, id)
job_orders   UNIQUE (tenant_id, id)

submissions  FOREIGN KEY (tenant_id, candidate_id) REFERENCES candidates(tenant_id, id)
             FOREIGN KEY (tenant_id, job_order_id) REFERENCES job_orders(tenant_id, id)
             UNIQUE (candidate_id, job_order_id)
```

Both keys read the same `tenant_id` column, so a submission can only exist when the candidate
*and* the job order live in that one tenant. Cross-tenant shortlisting is rejected by PostgreSQL,
not by an `if` statement. The `UNIQUE` makes a repeat Shortlist click idempotent at the database
level via `ON CONFLICT DO NOTHING`.

**Limitation to state plainly:** the assignment specifies no authentication, so the client
chooses its own `X-Tenant-ID`. This is *logical* isolation — no endpoint leaks another tenant's
rows and no mutation crosses tenants — but it is not protection against a caller who sends a
different id. Production would derive the tenant from an authenticated session; only
`get_tenant_scope` would change.

---

## Skill matching

The graded feature. For a job order, in one SQL statement:

1. Query **only candidates in the same tenant**.
2. `INNER JOIN` the link table filtered to the required skill ids — a candidate with no required
   skill produces no row at all, so zero-match exclusion is a property of the join, not a filter.
3. `COUNT(DISTINCT skill_id)` — duplicates can never inflate a ranking.
4. `ORDER BY match_count DESC, full_name, id` — count is the only ranking key; the rest make ties
   deterministic.

Minimum experience is returned as a **display flag** and appears nowhere in `WHERE` or
`ORDER BY`. `/matches` deliberately exposes no `sort_by`: the ranking is specified, not a client
choice.

Skills are normalized (casefold, trim, collapse whitespace, **preserving `+` and `#`** so `C++`
and `C#` survive) and synonyms resolve through an explicit `skill_aliases` table on write — so
matching itself is an exact integer join. Candidates and job orders go through the *same*
`SkillService`, which is what guarantees the two sides of a match can never disagree about what a
skill is.

---

## API

Base `/api/v1`. 🔒 = requires `X-Tenant-ID`.

| Method | Route |
|---|---|
| GET | `/health` |
| GET, POST | `/tenants` · GET `/tenants/stats` · GET `/tenants/{id}` |
| GET | `/skills` |
| GET, POST | `/candidates` 🔒 · GET `/candidates/stats` 🔒 |
| GET, PATCH, DELETE | `/candidates/{id}` 🔒 |
| POST, GET, DELETE | `/candidates/{id}/cv` 🔒 |
| GET, POST | `/job-orders` 🔒 · GET `/job-orders/stats` 🔒 |
| GET, PATCH, DELETE | `/job-orders/{id}` 🔒 |
| GET | `/job-orders/{id}/matches` 🔒 |
| POST | `/job-orders/{id}/shortlist` 🔒 |
| GET | `/submissions` 🔒 · GET `/submissions/stats` 🔒 |

Every list accepts `q`, `sort_by`, `sort_dir`, `page`, `page_size` and returns
`{items, total, page, page_size, total_pages}`. `sort_by` maps to a whitelisted column object, so
the raw string never reaches SQL.

Every error is `{"error": {"code", "message", "details"}}` — `VALIDATION_ERROR` (422),
`NOT_FOUND` (404), `CONFLICT` (409), `MISSING_TENANT` (400), `CONSTRAINT_VIOLATION` (409).

### Search

No minimum character count — one character searches, after a 300 ms debounce client-side.
`q` becomes `ILIKE '%term%'` OR'd across the columns visible on that screen, always AND'ed with
the tenant scope. Skill names match via `EXISTS`, never `JOIN` (a join would multiply rows and
corrupt the count — there is a test for it).

Honest caveat: the leading wildcard means no B-tree index applies, so PostgreSQL scans the
tenant's rows. Irrelevant at demo scale; the fix at scale is `pg_trgm` + a GIN index.

---

## Environment variables

Documented in [`.env.example`](.env.example).

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | SQLAlchemy/psycopg connection string |
| `TEST_DATABASE_URL` | Separate database for pytest — never point at the dev database |
| `CORS_ORIGINS` | Comma-separated origins allowed to call the API |
| `DEFAULT_PAGE_SIZE` / `MAX_PAGE_SIZE` | Pagination bounds |
| `MAX_CV_SIZE_MB` | CV upload limit |
| `AI_PROVIDER` / `AI_API_KEY` | Optional AI features. Blank = disabled, and everything still works |

---

## Known limitations

- **No authentication**, as specified. Consequences described under Multi-tenancy.
- **CV files are stored in PostgreSQL** as `BYTEA`, mapped `deferred` so the bytes are never
  fetched unless explicitly requested. Deliberate, to keep the project to one stateful
  dependency; production would use object storage.
- **No CV parsing or AI.** Optional in the brief, which states twice that manual entry scores the
  same. Adapters are designed for it but not implemented.
- **Duplicate candidates are allowed** — two people can share a name and email is optional, so
  there is no reliable natural key.
