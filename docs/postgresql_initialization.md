# Fresh PostgreSQL initialization

Fresh Supabase PostgreSQL databases use the independent `migrations_pg` graph.
The legacy `migrations` graph and its `20261112_06_supabase_adoption` revision
are not used for a fresh project.

## Graphs

The PostgreSQL graph has one root and one head:

```text
20261114_pg_00_initial
```

The legacy graph remains unchanged for historical environments. Never merge the
graphs or run the legacy adoption runner against a fresh project.

## Commands

After a separate read-only target preflight and explicit deployment approval:

```powershell
.\.venv\Scripts\python.exe -m alembic -c alembic-pg.ini upgrade head
.\.venv\Scripts\python.exe -m alembic -c alembic-pg.ini current
```

The backend selects `alembic-pg.ini` for PostgreSQL and does not call
`create_all()` for shared PostgreSQL databases. SQLite test fixtures retain
their isolated setup and do not use this graph.

The PostgreSQL initializer creates all eight application tables with native
Alembic operations, including role defaults/checks, foreign keys and delete
actions, indexes, unique constraints, and application check constraints.
`messages.reply_to_message_id` is unique but nullable, so PostgreSQL permits
multiple NULL values while rejecting duplicate non-NULL reply targets.

The PostgreSQL graph is intentionally independent. Its future revisions must
use `20261114_pg_00_initial` as their ancestry; they must not descend from the
legacy graph.
