# Supabase Auth Phase 2

The frontend uses Supabase Auth with the public anon key. The service-role key,
database URL, and any legacy JWT secret remain backend-only.

FastAPI verifies Supabase access tokens using the configured JWKS endpoint. The
issuer defaults to `SUPABASE_URL/auth/v1`; the audience defaults to
`authenticated`. The verifier selects an allowed algorithm from the token and
matching JWKS metadata; it does not trust unsigned or unsupported tokens.

Application roles remain in PostgreSQL `users.role`. JWT metadata is not used
for authorization. Public signup can create only a `student` application
profile through `POST /api/auth/profile`. Unknown identities are rejected by
normal authenticated routes until that explicit synchronization path runs.

The current RLS strategy is backend-enforced authorization. SQLAlchemy uses the
server-side database connection, so PostgreSQL `auth.uid()` policies are not
being claimed or added by this change. RLS policies require a separately
reviewed identity-propagation design and migration.

Admin provisioning invites identities through the Supabase Auth admin API only
when `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` are configured on the
backend. The service-role key is never returned by an API response.
