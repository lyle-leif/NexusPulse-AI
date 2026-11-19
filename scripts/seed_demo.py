"""Load the demo store into Postgres (idempotent). Run: uv run python scripts/seed_demo.py"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
for pkg in ("generator", "ingest", "eval"):
    sys.path.insert(0, str(ROOT / "packages" / pkg / "src"))

import psycopg  # noqa: E402

from nexuspulse_eval import write_labels  # noqa: E402
from nexuspulse_generator import MAIN_FASHION, Scenario, generate_store  # noqa: E402
from nexuspulse_ingest import DEFAULT_ADMIN_DSN, load_tables  # noqa: E402

WORKSPACE, BATCH, RUN = "demo", "v1", "demo_v1"
TABLES = ["order_items", "refunds", "orders", "sessions", "products", "marketing_spend", "change_events"]

SEED = 2026
SCENARIOS = (Scenario("tracking_breakage", start="2026-04-06", days=14, params={"lost_share": 0.6}),)


def main() -> None:
    store = generate_store(MAIN_FASHION, seed=SEED, scenarios=SCENARIOS)
    print(f"generated {len(store.sessions):,} sessions, {len(store.orders):,} orders; hash {store.content_hash()[:12]}")
    with psycopg.connect(DEFAULT_ADMIN_DSN) as conn, conn.cursor() as cur:
        for t in TABLES:
            cur.execute(f"DELETE FROM np.{t} WHERE workspace_id = %s", (WORKSPACE,))
        cur.execute("DELETE FROM eval.scenario_labels WHERE run_id = %s", (RUN,))
        conn.commit()
    counts = load_tables(store.tables(), WORKSPACE, BATCH)
    write_labels(RUN, "dev", store.labels)
    print("loaded:", counts)


if __name__ == "__main__":
    main()
