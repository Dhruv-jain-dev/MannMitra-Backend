# Anonymous student-to-counselor support

The anonymous-support feature is a separate persistence boundary from ordinary
student/counselor conversations. `anonymous_support_conversations` stores the
server-side mapping from the authenticated student to a random `Mitra-...`
alias. The student identity and counselor assignment are never returned by the
anonymous-support response serializers.

## API surface

Student endpoints:

- `POST /api/anonymous-support/conversations` (requires explicit consent)
- `GET /api/anonymous-support/conversations`
- `GET /api/anonymous-support/conversations/{id}`
- `POST /api/anonymous-support/conversations/{id}/messages`
- `POST /api/anonymous-support/conversations/{id}/close`

Counselor endpoints:

- `GET /api/counselor/anonymous-support`
- `POST /api/counselor/anonymous-support/{id}/accept`
- `GET /api/counselor/anonymous-support/{id}`
- `POST /api/counselor/anonymous-support/{id}/messages`
- `PATCH /api/counselor/anonymous-support/{id}`
- `POST /api/counselor/anonymous-support/{id}/notes`
- `POST /api/counselor/anonymous-support/{id}/followups`

Every endpoint uses the verified backend role and the server-side owner or
assignment predicate. The counselor response contains an alias, category,
urgency, messages, private notes and follow-ups; it does not contain the
student UUID, email, department or profile.

## Migration and RLS

The new independent PostgreSQL graph adds revision
`20261115_pg_02_anonymous_support` after the existing PostgreSQL head. It does
not edit the six legacy migrations or the old adoption migration. The migration
creates the five support tables, indexes, constraints, foreign keys, and
PostgreSQL RLS policies. SQLite compatibility tests execute the table DDL and
skip PostgreSQL-only RLS statements.

The policies use Supabase/PostgREST's `request.jwt.claim.sub` setting. The
backend currently uses direct SQLAlchemy access with a custom verified JWT and
does not set PostgreSQL request claims on each transaction. Therefore browser
or PostgREST access to these tables must remain disabled; backend authorization
is authoritative and the custom token is not treated as `auth.uid()`
automatically. The approved future strategy is to use Supabase Auth JWTs
through PostgREST, verify that `request.jwt.claim.sub` is populated, and test
student/counselor role and assignment policies with real identities before
enabling any direct client access.

Raw audit events intentionally have no participant SELECT policy. They are
default-deny under RLS and are available only to the authorized backend audit
workflow. Notes and follow-ups require both the counselor subject and an
assigned conversation; sender-message policies separately bind `student` and
`counselor` sender roles to the corresponding database role.

## Safety limitations

Pseudonymity is not a promise of absolute anonymity. Safety or legal escalation
must follow the institution's reviewed safeguarding procedure. This change
records counselor acceptance, status, private-note and follow-up audit events,
but does not itself decide whether a message is a crisis or disclose a mapped
identity. Retention and deletion periods still need an approved policy before
production rollout.

## Local verification

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_anonymous_support tests.test_postgresql_initialization -v
.\.venv\Scripts\python.exe -m py_compile backend\models.py backend\main.py migrations_pg\versions\20261115_pg_02_anonymous_support.py
Set-Location campuspulse-frontend
npm run lint
npm run build
```

## Isolated PostgreSQL RLS test

The real PostgreSQL suite is opt-in and rejects non-loopback hosts, Supabase
hostnames and pooler hostnames. It never reads the application's `DATABASE_URL`.
Docker Desktop is required:

```powershell
docker compose -f docker-compose.anonymous-postgres.yml up -d
$env:LOCAL_ANONYMOUS_SUPPORT_POSTGRES_URL = "postgresql+psycopg://rls_test_admin:local-only-test-password@127.0.0.1:55432/mannmitra_rls_test"
.\.venv\Scripts\python.exe -m unittest tests.test_anonymous_support_postgres -v
docker compose -f docker-compose.anonymous-postgres.yml down -v
```

The suite uses PostgreSQL 16.4, creates a temporary non-owner role, applies the
independent PostgreSQL graph, runs real RLS queries with transaction-local
`request.jwt.claim.sub` values, and downgrades the isolated database during
cleanup. It tests ownership, assignment, forged sender roles, raw audit
access, unauthorized writes, and pooled-connection claim leakage. The test
URL is deliberately loopback-only and must never be replaced with a Supabase
URL.

Deployment is intentionally not included here. Apply the PostgreSQL graph only
to the approved target after review and backup, then perform authenticated
student/counselor end-to-end tests with approved test identities.
