"""Ground-truth label storage. Only this package may touch the eval schema,
and only through the np_eval role. Inference code must never import it.
"""
from __future__ import annotations

import json

import psycopg

EVAL_DSN = "postgresql://np_eval:np_eval_dev@localhost:5433/nexuspulse"


def write_labels(run_id: str, split: str, labels: list[dict], dsn: str = EVAL_DSN) -> int:
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        for lab in labels:
            cur.execute(
                "INSERT INTO eval.scenario_labels (run_id, scenario_id, split, ground_truth) VALUES (%s, %s, %s, %s)",
                (run_id, lab["scenario_id"], split, json.dumps(lab)),
            )
        conn.commit()
    return len(labels)


def read_labels(run_id: str, dsn: str = EVAL_DSN) -> list[dict]:
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT ground_truth FROM eval.scenario_labels WHERE run_id = %s", (run_id,))
        return [r[0] for r in cur.fetchall()]
