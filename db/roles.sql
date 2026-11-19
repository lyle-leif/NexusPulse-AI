-- Local development roles. Passwords are dev-only and must never be reused.
-- np_pipeline: reads and appends business data; NO access to the eval schema.
-- np_eval: reads business data and reads/writes ground-truth labels.
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'np_pipeline') THEN
    CREATE ROLE np_pipeline LOGIN PASSWORD 'np_pipeline_dev';
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'np_eval') THEN
    CREATE ROLE np_eval LOGIN PASSWORD 'np_eval_dev';
  END IF;
END $$;

REVOKE ALL ON SCHEMA eval FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA eval FROM PUBLIC;

GRANT USAGE ON SCHEMA np TO np_pipeline, np_eval;
GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA np TO np_pipeline;   -- append-only: no UPDATE/DELETE
GRANT SELECT ON ALL TABLES IN SCHEMA np TO np_eval;

GRANT USAGE ON SCHEMA eval TO np_eval;
GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA eval TO np_eval;
