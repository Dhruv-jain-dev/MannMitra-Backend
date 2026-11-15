# First administrator bootstrap

This is a one-time, backend-only procedure. It is not an HTTP endpoint and is
never available to students, counselors, or the frontend.

## Configuration

Set these values only in the backend environment:

```text
ADMIN_BOOTSTRAP_ENABLED=true
ADMIN_BOOTSTRAP_TARGET_ID=<the approved Supabase Auth UUID>
```

The existing backend-only `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, and
`DATABASE_URL` must also be configured. The UUID must be copied from the
approved Supabase Auth identity; the CLI accepts no email or arbitrary target
argument.

## Preflight

Before execution, the owner must confirm that:

1. The target Auth identity is the intended administrator.
2. Its email is confirmed and the identity is not deleted or banned.
3. No administrator profile exists in `public.users`.
4. A current database backup/recovery plan exists.
5. The backend environment points to the intended project.

## Execution

From the repository root, run exactly:

```powershell
.\.venv\Scripts\python.exe -m backend.bootstrap_admin --confirm BOOTSTRAP-FIRST-ADMIN-20261115
```

The command verifies the Auth UUID through the server-only Supabase Auth Admin
API, checks the current PostgreSQL role state in one transaction, and creates
only the matching `users` row with `role='admin'`. It never creates or changes
a password and never returns credentials.

## Disable immediately

After a successful run, set:

```text
ADMIN_BOOTSTRAP_ENABLED=false
```

Then remove `ADMIN_BOOTSTRAP_TARGET_ID` from the backend environment and restart
the backend. A later run is also refused if any admin already exists.

## Safety and recovery

- Missing or incorrect confirmation is rejected before database setup.
- Unknown, unconfirmed, deleted, banned, or mismatched Auth identities are rejected.
- Existing administrators stop the operation.
- Existing target profiles with a non-admin role stop the operation.
- A repeated run stops rather than overwriting the profile.
- Database failure rolls back the profile transaction.
- No historical migration, table, password, or existing student record is changed.
- The safe recovery is to inspect the failed precondition and correct configuration;
  no automatic downgrade or role reversal is provided.
