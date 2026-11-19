import uuid

import pandas as pd
import psycopg
import pytest

from nexuspulse_analytics import daily_kpis, run_reconciliation
from nexuspulse_analytics.db import PIPELINE_DSN, read_tables
from nexuspulse_eval import EVAL_DSN, read_labels, write_labels
from nexuspulse_generator import MAIN_FASHION, Scenario, generate_store
from nexuspulse_ingest import DEFAULT_ADMIN_DSN, load_tables

try:
    psycopg.connect(DEFAULT_ADMIN_DSN, connect_timeout=3).close()
    DB_UP = True
except Exception:  # pragma: no cover
    DB_UP = False

pytestmark = pytest.mark.skipif(not DB_UP, reason="Postgres is not running (docker compose up -d)")

TABLES = ["order_items", "refunds", "orders", "sessions", "products", "marketing_spend", "change_events"]


@pytest.fixture(scope="module")
def loaded():
    ws, batch, run = f"test_{uuid.uuid4().hex[:8]}", "batch_1", f"run_{uuid.uuid4().hex[:8]}"
    sc = Scenario("tracking_breakage", start="2025-02-10", days=7, params={"lost_share": 0.6})
    store = generate_store(MAIN_FASHION, seed=21, days=60, scenarios=(sc,))
    counts = load_tables(store.tables(), ws, batch)
    yield store, ws, batch, run, counts
    with psycopg.connect(DEFAULT_ADMIN_DSN) as conn, conn.cursor() as cur:
        for t in TABLES:
            cur.execute(f"DELETE FROM np.{t} WHERE workspace_id = %s", (ws,))
        cur.execute("DELETE FROM eval.scenario_labels WHERE run_id = %s", (run,))
        conn.commit()


def test_row_counts_match(loaded):
    store, ws, batch, _, counts = loaded
    for name, df in store.tables().items():
        assert counts[name] == len(df), name


def test_round_trip_kpis_identical_and_reconcile(loaded):
    store, ws, batch, _, _ = loaded
    tz = store.profile.timezone
    from_db = read_tables(ws, batch)
    mem = daily_kpis(store.tables(), tz)
    db = daily_kpis(from_db, tz)
    pd.testing.assert_frame_equal(mem, db)
    assert [c for c in run_reconciliation(from_db, tz) if not c.passed] == []


def test_duplicate_batch_is_refused(loaded):
    store, ws, batch, _, _ = loaded
    with pytest.raises(ValueError):
        load_tables(store.tables(), ws, batch)


def test_pipeline_role_cannot_read_labels(loaded):
    store, ws, batch, run, _ = loaded
    write_labels(run, "dev", store.labels)
    with psycopg.connect(PIPELINE_DSN) as conn, conn.cursor() as cur:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute("SELECT * FROM eval.scenario_labels")
    with psycopg.connect(PIPELINE_DSN) as conn, conn.cursor() as cur:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cur.execute("SELECT count(*) FROM pg_catalog.pg_class c JOIN eval.scenario_labels l ON true")
    assert read_labels(run)[0]["kind"] == "tracking_breakage"  # eval role can


def test_pipeline_role_is_append_only(loaded):
    _, ws, _, _, _ = loaded
    for stmt in ("UPDATE np.orders SET discount = 0 WHERE workspace_id = %s", "DELETE FROM np.orders WHERE workspace_id = %s"):
        with psycopg.connect(PIPELINE_DSN) as conn, conn.cursor() as cur:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cur.execute(stmt, (ws,))


def test_pipeline_output_unchanged_by_presence_of_labels(loaded):
    store, ws, batch, run, _ = loaded
    tz = store.profile.timezone
    with_labels = daily_kpis(read_tables(ws, batch), tz)
    with psycopg.connect(DEFAULT_ADMIN_DSN) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM eval.scenario_labels WHERE run_id = %s", (run,))
        conn.commit()
    without_labels = daily_kpis(read_tables(ws, batch), tz)
    pd.testing.assert_frame_equal(with_labels, without_labels)
