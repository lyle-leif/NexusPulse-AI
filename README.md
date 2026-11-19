# NexusPulse AI

An autonomous business intelligence system for small online stores. NexusPulse AI continuously forecasts expected performance, detects unexpected changes, investigates where they occurred and what coincided with them, and produces traceable, evidence-backed reports.

**Project status:** Step 1 (reliable business data) is in progress: metric contracts, database schema, synthetic store generator, KPI engine, and reconciliation checks are implemented. Later roadmap steps have not started.

## Overview

Most analytics tools show what the numbers are. NexusPulse AI is designed to help an owner understand what changed, where it changed, and what to verify next.

For example, if revenue falls 25% below expectation, the system is designed to establish that traffic was stable, that the decline is accounted for mostly by lower conversion on mobile at the checkout step, and that it began within hours of a recorded checkout deployment. It then recommends verifying checkout errors before increasing advertising spend. Each figure in the report traces back to a specific calculation, and the report does not claim that the deployment caused the decline.

## Core principles

1. **Python computes, the AI explains.** The language model never produces numbers or relationships.
2. **Observed, attributed, associated, and hypothesized findings are kept separate.** A mathematical breakdown is not presented as proof of cause.
3. **No invented probabilities.** Strength of evidence is shown using published rules until calibration is demonstrated.
4. **Measured, not claimed.** Detection, investigation, and report quality are evaluated on held-out scenarios and shown in the product.
5. **Zero cost.** Everything runs locally on free, open-source software. No paid services are required.

## Planned capabilities (Version 1)

- **Reliable business data:** a session-linked data model, versioned metric contracts, and automatic reconciliation checks.
- **Measurable anomaly detection:** seasonal-naive and ETS forecasting, with deviations judged against forecasts issued before the period.
- **Evidence-backed investigation:** an exact revenue bridge, Shapley decomposition of revenue drivers, segment drill-down, and change-event matching.
- **Verified reports:** template-first report generation, with a local language model limited to bounded wording slots and a deterministic fallback.
- **Demonstrable evaluation:** held-out scenario results, isolated ground-truth labels, and a Time Machine demo that steps a simulated store forward day by day.

Features planned for later releases, including a what-if simulator and conversational follow-up, are listed in the PRD.

## Technology

| Area | Choice |
|---|---|
| Web application | Next.js (TypeScript) |
| Analytics and pipeline | Python, pandas or polars, statsmodels, scipy |
| API | FastAPI |
| Database | PostgreSQL |
| Language model | Ollama with a local open-weight model (optional) |
| Continuous integration | GitHub Actions |

## Local setup

Requirements: Docker Desktop, Python (managed by `uv`), and Node.js for the web app later.

```
py -m pip install --user uv
uv sync
docker compose up -d
uv run pytest
```

The development database is published on host port 5433 (to avoid clashing with a local PostgreSQL on 5432). The development credentials in `docker-compose.yml` and `db/roles.sql` are for local use only.

## Documentation

| Document | Contents |
|---|---|
| [PRD.md](PRD.md) | Problem, goals, scope, functional requirements, success metrics, roadmap, risks |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Components, pipeline, data model, revenue decomposition, forecasting, investigation, reports, evaluation, reproducibility |

## Roadmap

1. Reliable business data
2. Measurable detection
3. Evidence-backed investigation
4. Verified AI reports
5. Demonstrable evaluation

Details and completion criteria for each step are in the PRD.

## Contributing

The project is in an early design phase and is not yet accepting contributions.

## License

No license has been selected yet.
