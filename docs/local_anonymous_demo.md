# Local anonymous counselor chat demo

This is a test-only flow. It does not use Supabase, the root `.env`, or the
normal backend database.

## Start the isolated backend

From the repository root:

```powershell
$env:CAMPUSPULSE_TEST_DATABASE_URL = "sqlite:///C:/Users/hp/MannMitra-Nandita/tmp/anonymous_support_local.db"
$env:CAMPUSPULSE_TEST_JWT_SECRET = "local-test-secret"
.\.venv\Scripts\python.exe -m uvicorn tests.http_test_app:app --host 127.0.0.1 --port 8001
```

The test app seeds these profiles on first login and never overwrites an
existing incompatible role:

| Role | Email | Local-only password |
|---|---|---|
| Student | `student.test@mannmitra.local` | `StudentTest!2026` |
| Counselor | `counselor.test@mannmitra.local` | `CounselorTest!2026` |
| Admin | `admin.test@mannmitra.local` | `AdminTest!2026` |

The test-only login endpoint accepts only these three exact accounts. The shared
development-token endpoint is removed from this browser-facing test app.

## Start the frontend

In a second terminal:

```powershell
Set-Location campuspulse-frontend
npm run dev -- --host 127.0.0.1 --port 5318
```

Open <http://127.0.0.1:5318/login>. `.env.local` points Axios to port 8001 and
enables the local test-auth branch. Production Supabase login remains selected
when `VITE_LOCAL_TEST_AUTH` is not `true`.

## Demonstration flow

1. Sign in as the student.
2. Open **Counselor Support**.
3. Accept the privacy notice and create a request.
4. Sign out.
5. Sign in as the counselor.
6. Open **Anonymous Inbox**, open the pending alias, accept it, and reply.
7. Sign out and sign in again as the student.
8. Open **Counselor Support** and select the same alias to verify the reply and persistence.

The SQLite demo validates backend ownership and role authorization. It does not
validate PostgreSQL RLS. Use the isolated PostgreSQL suite for that purpose.
