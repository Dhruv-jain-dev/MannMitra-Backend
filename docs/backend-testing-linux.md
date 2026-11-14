# Backend testing on Linux/WSL2

Use Linux or WSL2 for HTTP integration tests. The Windows host currently
cannot initialize the asyncio socketpair used by Starlette, Trio, or Uvicorn;
this is a test-environment limitation, not an application configuration.

## One-time setup

From an Ubuntu/WSL2 shell:

```bash
sudo apt update
sudo apt install -y python3 python3-venv build-essential libsndfile1 ffmpeg
cd /mnt/c/Users/hp/MannMitra-Nandita
python3 -m venv .venv-linux
source .venv-linux/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

`requirements.txt` contains the application and test-runtime dependencies:
FastAPI, Uvicorn, SQLAlchemy, Alembic, psycopg, and the MannMitra runtime
packages. The tests use Python's standard `unittest` and `urllib` modules, so
no separate test framework is required.

## Isolated test configuration

Do not point tests at the shared Supabase database. Use a disposable SQLite
database and a test-only JWT secret:

```bash
export MANNMITRA_ENV=test
export MANNMITRA_DATABASE_URL="sqlite:////tmp/campuspulse-test.db"
export MANNMITRA_AUTH_JWT_SECRET="local-only-test-secret"
unset DATABASE_URL
```

`tests/test_http_api.py` creates its own temporary SQLite database and secret,
starts `tests/http_test_app.py` in a subprocess, and exercises the real API
over loopback HTTP. It does not require `GEMINI_API_KEY` because these tests do
not invoke MannMitra generation.

## Commands

Focused pure/unit tests:

```bash
python -m unittest \
  tests.test_rag_grounding \
  tests.test_memory_retrieval \
  tests.test_admin_analytics.AdminAggregationTests -v
```

HTTP integration tests:

```bash
python -m unittest tests.test_http_api -v
```

Complete backend test suite:

```bash
python -m unittest discover -s tests -v
```

Migration check against a disposable database:

```bash
tmp_db="$(mktemp -u /tmp/campuspulse-migrations.XXXXXX.db)"
export MANNMITRA_DATABASE_URL="sqlite:///$tmp_db"
alembic upgrade head
alembic current
alembic downgrade base
rm -f "$tmp_db"
```

The HTTP suite must report executed tests and `OK` before those tests are
considered validated. A Windows timeout or a test process that never reaches
the first request is a blocked result, not a pass.
