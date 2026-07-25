# Roadmap

Eleven phases, each with acceptance criteria. `main` stays green; each
phase is a short-lived `feat/` branch ending in a tagged release.

## Phase 0 — Scaffolding & infrastructure `v0.0.1` ✅
- [x] Project layout, uv, ruff, pytest, pre-commit
- [x] Settings from the environment, validated at startup
- [x] Multi-stage Dockerfile, one image for API and worker
- [x] Docker Compose: API, worker, PostgreSQL, Redis
- [x] Liveness and readiness endpoints that really check dependencies
- [x] Structured logging (JSON in production, readable locally)
- [x] CI with service containers and a Docker build

**Acceptance:** `docker compose up` brings four services up; `/health/ready`
returns 200 with every dependency "ok".

## Phase 1 — Database
- [ ] SQLAlchemy models: locations, observations, forecasts, accuracy
- [ ] Alembic migrations
- [ ] Seed script: 81 Turkish provinces
- [ ] Idempotent upserts (the same hour written twice stays one row)
- [ ] Indexes for time-series queries

**Acceptance:** tables visible in a GUI, provinces loaded, re-running the
seed changes nothing.

## Phase 2 — Open-Meteo client
- [ ] Async httpx client with timeouts
- [ ] Retry with exponential backoff; transient vs permanent errors
- [ ] Response validation with Pydantic
- [ ] Recorded real responses as test fixtures

**Acceptance:** real data lands in the database; a simulated outage
retries and gives up gracefully instead of crashing.

## Phase 3 — Scheduled worker
- [ ] APScheduler: hourly observations, daily forecasts
- [ ] Overlap prevention and job run history
- [ ] Backfill command for historical data

**Acceptance:** left running, the database fills up on schedule.

## Phase 4 — REST API
- [ ] Locations: list, add, deactivate
- [ ] Current conditions, historical range queries, pagination
- [ ] Pydantic response schemas, consistent error format

**Acceptance:** every endpoint usable from `/docs`; invalid input gives a
clear 422.

## Phase 5 — Production hardening
- [ ] API key authentication
- [ ] Rate limiting
- [ ] Redis response caching with sensible TTLs
- [ ] Request ID middleware

**Acceptance:** unauthenticated requests 401, floods 429, repeat queries
measurably faster.

## Phase 6 — Forecast accuracy
- [ ] Match forecasts to observations by target time
- [ ] MAE, RMSE, bias per metric
- [ ] Breakdown by horizon and by location
- [ ] Accuracy endpoints

**Acceptance:** "average error of a 3-day temperature forecast for
Istanbul" is one API call.

## Phase 7 — Observability
- [ ] Request/response logging with correlation IDs
- [ ] Job metrics
- [ ] Deeper health checks

## Phase 8 — Frontend foundations
- [ ] React + Vite + TypeScript + Tailwind
- [ ] API client, layout, routing

## Phase 9 — Frontend data
- [ ] Location list and search
- [ ] Current conditions and history charts
- [ ] Loading and error states

## Phase 10 — Accuracy dashboard
- [ ] Forecast-vs-actual charts
- [ ] Error by horizon
- [ ] Location comparison

## Phase 11 — Showcase `v1.0.0`
- [ ] README with architecture and screenshots
- [ ] Deployment notes
- [ ] Release
