# Supabase schema adoption procedure

This procedure is intentionally separate from application startup. It must not
be run until the live-schema audit, backup, role policy, and maintenance window
have been approved.

The six existing migrations remain unchanged. The adoption revision is:

```text
20261112_06_supabase_adoption
down_revision = 20261110_05
```

## Safety properties

- The adoption revision never creates, recreates, drops, or copies application tables.
- Existing columns, constraints, and indexes are definition-checked before they are accepted.
- PostgreSQL catalog metadata is checked for index uniqueness, access method,
  key ordering, predicates, expressions, included columns, constraint type,
  referenced columns, delete action, validation, and deferrability.
- Missing objects are added only when absent.
- Existing `messages.reply_to_message_id` uniqueness is preserved.
- PostgreSQL transactional DDL is used.
- Baseline stamping and adoption run on one caller-owned SQLAlchemy connection and transaction.
- The runner requires explicit confirmation and is never called by FastAPI startup.
- Direct Python calls require the same exact confirmation token as the CLI.
- Adoption refuses to run if `public.alembic_version` already exists.

## Deployment sequence

1. Take a Supabase backup/snapshot and stop application writes.
2. Verify `DATABASE_URL` points to the intended Supabase project.
3. Run the previously approved read-only preflight checks. The preflight must
   validate every object from the six original migrations. Only the five known
   adoption gaps are allowed to be absent; any other missing or incompatible
   object aborts adoption.
4. Confirm the six existing users are to receive the default `student` role.
5. Review the new migration and runner locally.
6. From the project root, after explicit approval only, run:

   ```powershell
   .\.venv\Scripts\python.exe -m migrations.adopt_supabase --confirm ADOPT-SUPABASE-20261112
   ```

   The runner rejects missing or incorrect confirmation before creating an
   engine. It refuses any existing `alembic_version` table, validates the
   baseline, stamps `20261110_05`, executes only `20261112_06`, validates the
   complete resulting schema, and commits only if every step succeeds. Any
   exception rolls the transaction back. A repeated run therefore refuses
   rather than restamping or rerunning adoption.

7. Verify `alembic current`, the final schema, constraints, indexes, role
   default, and unchanged record counts.
8. Resume application writes.

Do not run independent `alembic stamp`, `alembic upgrade`, or downgrade commands
for this adoption process.
