# Supabase PostgreSQL setup

The MannMitra API uses SQLAlchemy models to create the `users`,
`conversations`, `messages`, and `message_analyses` tables. No Supabase Auth
or browser-facing Supabase key is required; API JWT authentication remains in
the MannMitra backend.

1. In Supabase, create a project and obtain its PostgreSQL connection string
   from **Project Settings → Database → Connection string**. Use the pooled
   connection string for normal application traffic.
2. In the repository root `.env`, set `DATABASE_URL` to that value. A standard
   `postgresql://...` URL is accepted and converted to SQLAlchemy's `psycopg`
   driver URL at startup.
3. Install dependencies with `pip install -r requirements.txt` so `psycopg`
   is available.
4. Apply the existing Alembic migrations during the deployment process, then
   start the API. The application uses the same URL resolver as Alembic and
   requires PostgreSQL.

Example (use your own values locally; never commit them):

```env
DATABASE_URL=postgresql://postgres.PROJECT_REF:YOUR_PASSWORD@aws-0-REGION.pooler.supabase.com:5432/postgres
MANNMITRA_ENV=development
MANNMITRA_AUTH_JWT_SECRET=your-local-secret
```

The existing `mannmitra_dev.db` SQLite file is not migrated, removed, or used
by the application configuration. Moving any SQLite records to Supabase
requires a separate, reviewed data migration.
