# weather-service

A weather data pipeline that collects forecasts and observations for
Turkish cities, then measures how accurate those forecasts turned out to
be. REST API, scheduled collection, and a web dashboard.

> 🚧 **Status: Phase 4 (REST API).** A paginated read/write API over the
> data: manage locations, read current conditions, query history and
> forecasts. Try it at `/docs`. Auth and caching arrive in Phase 5. See
> the [roadmap](ROADMAP.md).

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

Pull data immediately instead of waiting for the schedule:

```bash
docker compose exec worker python -m weather.workers.main --once
```

```bash
docker compose ps       # what is running
docker compose logs -f  # follow the logs
docker compose down     # stop (data survives)
docker compose down -v  # stop and delete the database
```

## Endpoints

Full interactive docs at `/docs`. In brief:

| Method | Path | What |
|---|---|---|
| GET | `/locations` | list active locations (`?active_only=false` for all) |
| POST | `/locations` | add a location (409 if the coordinates exist) |
| GET | `/locations/{id}` | one location |
| DELETE | `/locations/{id}` | deactivate (keeps history, stops collection) |
| GET | `/locations/{id}/current` | most recent observation |
| GET | `/locations/{id}/observations` | history, paginated, date-filterable |
| GET | `/locations/{id}/forecasts` | forecasts (`?latest_only=false` for all) |

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
