"""Test that skill1_text2sql enforces read-only constraints."""
import sqlite3
import tempfile
from pathlib import Path

import pytest

from alphasonar.capabilities import skill1_text2sql


def test_rejects_insert():
    """Direct INSERT should be rejected before database connection."""
    with pytest.raises(sqlite3.OperationalError, match="REJECTED.*INSERT"):
        skill1_text2sql._exec("INSERT INTO financial_reports VALUES (1, 2, 3)")


def test_rejects_update():
    with pytest.raises(sqlite3.OperationalError, match="REJECTED.*UPDATE"):
        skill1_text2sql._exec("UPDATE financial_reports SET revenue=999 WHERE ticker='AMD.US'")


def test_rejects_delete():
    with pytest.raises(sqlite3.OperationalError, match="REJECTED.*DELETE"):
        skill1_text2sql._exec("DELETE FROM financial_reports WHERE ticker='AMD.US'")


def test_rejects_drop():
    with pytest.raises(sqlite3.OperationalError, match="REJECTED.*DROP"):
        skill1_text2sql._exec("DROP TABLE financial_reports")


def test_rejects_create():
    with pytest.raises(sqlite3.OperationalError, match="REJECTED.*CREATE"):
        skill1_text2sql._exec("CREATE TABLE evil (id INT)")


def test_rejects_alter():
    with pytest.raises(sqlite3.OperationalError, match="REJECTED.*ALTER"):
        skill1_text2sql._exec("ALTER TABLE financial_reports ADD COLUMN evil TEXT")


def test_rejects_multiple_statements():
    """Semicolon-separated statements should be rejected."""
    with pytest.raises(sqlite3.OperationalError, match="Multiple statements"):
        skill1_text2sql._exec("SELECT 1; DROP TABLE financial_reports;")


def test_allows_select():
    """Valid SELECT should execute (will fail if DB doesn't exist, but not due to readonly check)."""
    try:
        result = skill1_text2sql._exec("SELECT 1 AS test")
        assert result == [{"test": 1}]
    except sqlite3.OperationalError as e:
        # If DB doesn't exist, that's fine for this unit test
        if "unable to open" not in str(e):
            raise


def test_allows_with_clause():
    """WITH (CTE) should be allowed."""
    try:
        result = skill1_text2sql._exec("WITH cte AS (SELECT 1 AS x) SELECT * FROM cte")
        assert result == [{"x": 1}]
    except sqlite3.OperationalError as e:
        if "unable to open" not in str(e):
            raise


def test_readonly_mode_prevents_writes_at_sqlite_level():
    """Even if our parser failed, SQLite's read-only mode should block writes."""
    # Create a temporary database and verify URI mode=ro works
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        # Create a test table
        conn = sqlite3.connect(tmp_path)
        conn.execute("CREATE TABLE test (id INTEGER)")
        conn.execute("INSERT INTO test VALUES (1)")
        conn.commit()
        conn.close()

        # Open read-only and try to write
        ro_conn = sqlite3.connect(f"file:{tmp_path}?mode=ro", uri=True)
        ro_conn.execute("PRAGMA query_only = ON")

        # Read should work
        result = ro_conn.execute("SELECT * FROM test").fetchall()
        assert result == [(1,)]

        # Write should fail at SQLite level
        with pytest.raises(sqlite3.OperationalError, match="readonly|attempt to write"):
            ro_conn.execute("INSERT INTO test VALUES (2)")

        ro_conn.close()
    finally:
        tmp_path.unlink(missing_ok=True)
