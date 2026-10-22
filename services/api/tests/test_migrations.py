"""Opt-in migration check against a real PostgreSQL database.

Set TEST_DATABASE_URL to a disposable database whose name contains "test", for example
postgresql+psycopg://user:password@localhost:5432/fixify_migration_test. The test applies the
migrations, checks the model has no drift, and downgrades back to an empty schema.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy.engine import make_url

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
API_ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL, reason="TEST_DATABASE_URL is not set (PostgreSQL migration check)"
)


def _alembic(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=API_ROOT,
        env={**os.environ, "DATABASE_URL": TEST_DATABASE_URL or ""},
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_migrations_apply_match_models_and_downgrade():
    database = make_url(TEST_DATABASE_URL or "").database or ""
    assert "test" in database.lower(), "Refusing to migrate a database not named *test*."

    upgrade = _alembic("upgrade", "head")
    assert upgrade.returncode == 0, upgrade.stderr[-500:]
    try:
        drift = _alembic("check")
        assert drift.returncode == 0, drift.stderr[-500:]
    finally:
        downgrade = _alembic("downgrade", "base")
    assert downgrade.returncode == 0, downgrade.stderr[-500:]
