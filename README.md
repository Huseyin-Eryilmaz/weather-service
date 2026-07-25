# weather-service

A weather data pipeline that collects forecasts and observations for
Turkish cities, then measures how accurate those forecasts turned out to
be. REST API, scheduled collection, and a web dashboard.

> 🚧 **Status: Phase 0 (scaffolding).** Four services come up together
> and report their health; data collection starts in Phase 2. See the
> [roadmap](ROADMAP.md).

## What it does

Weather apps tell you tomorrow's forecast. This one keeps score: every
forecast is stored when it is issued, every observation is stored when it
arrives, and the two are matched up afterwards to answer questions like
*"how far off is a three-day temperature forecast for Ankara, on average?"*

## Quick start

```bash
docker compose up --build
```

Then:

- API docs: http://localhost:8000/docs
- Health: http://localhost:8000/health/ready

```bash
docker compose ps       # what is running
docker compose logs -f  # follow the logs
docker compose down     # stop (data survives)
docker compose down -v  # stop and delete the database
```

## Architecture

```
Browser ──► FastAPI ──► PostgreSQL ◄── Worker ──► Open-Meteo
              │                                    (external)
              └──► Redis (cache)
```

Four containers, one image. The API and the worker share a codebase but
run as separate processes: a slow data fetch should never make an HTTP
request wait, and the two need to fail and scale independently.

## Development

```bash
uv sync
uv run pytest --cov=weather
uv run ruff check . && uv run ruff format .
```

Running the API outside Docker needs a `.env` (copy `.env.example`),
because the hostnames `db` and `cache` only exist inside the compose
network.

## License

MIT
