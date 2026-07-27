# weather-service

A weather data pipeline that collects forecasts and observations for
Turkish cities, then measures how accurate those forecasts turned out to
be. REST API, scheduled collection, and a web dashboard.

> 🚧 **Status: Phase 6 (forecast accuracy).** The service now scores its
> own forecasts against what actually happened — MAE, RMSE, bias, and how
> error grows with lead time. This is the question the whole pipeline was
> built to answer. The frontend begins in Phase 8. See the
> [roadmap](ROADMAP.md).

## What it does

Weather apps tell you tomorrow's forecast. This one keeps score: every
forecast is stored when it is issued, every observation is stored when it
arrives, and the two are matched up afterwards to answer questions like
*"how far off is a three-day temperature forecast for Ankara, on average?"*

The finding falls straight out of the data — error grows with lead time:

```
 6h ahead  ->  MAE 1.0 C
24h ahead  ->  MAE 3.0 C
72h ahead  ->  MAE 8.0 C
```

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

Full interactive docs at `/docs`. Reads are open; writes (POST/DELETE)
require an `X-API-Key` header when `API_KEYS` is configured. Every route
is rate-limited per caller, and current conditions are cached briefly.

In brief:

| Method | Path | What |
|---|---|---|
| GET | `/locations` | list active locations (`?active_only=false` for all) |
| POST | `/locations` | add a location (409 if the coordinates exist) |
| GET | `/locations/{id}` | one location |
| DELETE | `/locations/{id}` | deactivate (keeps history, stops collection) |
| GET | `/locations/{id}/current` | most recent observation |
| GET | `/locations/{id}/observations` | history, paginated, date-filterable |
| GET | `/locations/{id}/forecasts` | forecasts (`?latest_only=false` for all) |
| GET | `/accuracy/summary` | MAE, RMSE, bias (`?location_id=`, `?max_horizon=`) |
| GET | `/accuracy/by-horizon` | error broken down by forecast lead time |

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
