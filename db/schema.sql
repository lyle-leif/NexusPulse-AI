-- NexusPulse schema, version 1
-- Raw tables are append-only. Corrections arrive as new rows (new ingest_batch_id).
-- Ground-truth labels live in a separate schema that the pipeline role cannot read.

CREATE SCHEMA IF NOT EXISTS np;
CREATE SCHEMA IF NOT EXISTS eval;

CREATE TABLE IF NOT EXISTS np.products (
    workspace_id    text NOT NULL,
    product_id      text NOT NULL,
    name            text NOT NULL,
    category        text NOT NULL,
    price           numeric(12,2) NOT NULL,
    cost            numeric(12,2) NOT NULL,
    ingest_batch_id text NOT NULL,
    PRIMARY KEY (workspace_id, product_id, ingest_batch_id)
);

CREATE TABLE IF NOT EXISTS np.sessions (
    workspace_id     text NOT NULL,
    session_id       text NOT NULL,
    started_at       timestamptz NOT NULL,
    channel          text NOT NULL,
    device           text NOT NULL,
    region           text NOT NULL,
    reached_cart     boolean NOT NULL,
    reached_checkout boolean NOT NULL,
    ingest_batch_id  text NOT NULL,
    PRIMARY KEY (workspace_id, session_id, ingest_batch_id),
    CHECK (NOT reached_checkout OR reached_cart)
);

CREATE TABLE IF NOT EXISTS np.orders (
    workspace_id    text NOT NULL,
    order_id        text NOT NULL,
    placed_at       timestamptz NOT NULL,
    session_id      text,                       -- NULL means unattributed
    currency        text NOT NULL,
    gross_sales     numeric(12,2) NOT NULL,
    discount        numeric(12,2) NOT NULL DEFAULT 0,
    status          text NOT NULL,              -- paid | cancelled
    is_test         boolean NOT NULL DEFAULT false,
    ingest_batch_id text NOT NULL,
    PRIMARY KEY (workspace_id, order_id, ingest_batch_id)
);

CREATE TABLE IF NOT EXISTS np.order_items (
    workspace_id    text NOT NULL,
    order_id        text NOT NULL,
    product_id      text NOT NULL,
    quantity        integer NOT NULL CHECK (quantity > 0),
    unit_price      numeric(12,2) NOT NULL,
    ingest_batch_id text NOT NULL
);

CREATE TABLE IF NOT EXISTS np.refunds (
    workspace_id    text NOT NULL,
    order_id        text NOT NULL,
    refunded_at     timestamptz NOT NULL,
    amount          numeric(12,2) NOT NULL CHECK (amount > 0),
    ingest_batch_id text NOT NULL
);

CREATE TABLE IF NOT EXISTS np.marketing_spend (
    workspace_id    text NOT NULL,
    spend_date      date NOT NULL,
    channel         text NOT NULL,
    campaign        text NOT NULL,
    spend           numeric(12,2) NOT NULL,
    impressions     bigint NOT NULL,
    clicks          bigint NOT NULL,
    ingest_batch_id text NOT NULL
);

CREATE TABLE IF NOT EXISTS np.change_events (
    workspace_id    text NOT NULL,
    event_id        text NOT NULL,
    occurred_at     timestamptz NOT NULL,
    event_type      text NOT NULL,
    description     text NOT NULL,
    scope           jsonb NOT NULL DEFAULT '{}'::jsonb,
    source          text NOT NULL,
    ingest_batch_id text NOT NULL,
    PRIMARY KEY (workspace_id, event_id, ingest_batch_id)
);

-- Ground-truth labels: readable only by the evaluation role.
CREATE TABLE IF NOT EXISTS eval.scenario_labels (
    run_id          text NOT NULL,
    scenario_id     text NOT NULL,
    split           text NOT NULL,              -- dev | heldout
    ground_truth    jsonb NOT NULL,
    PRIMARY KEY (run_id, scenario_id)
);

-- Roles (created by the setup script; pipeline role gets no grant on eval).
-- CREATE ROLE np_pipeline LOGIN PASSWORD '...';
-- CREATE ROLE np_eval LOGIN PASSWORD '...';
-- GRANT USAGE ON SCHEMA np TO np_pipeline, np_eval;
-- GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA np TO np_pipeline;
-- GRANT USAGE ON SCHEMA eval TO np_eval;
-- GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA eval TO np_eval;
