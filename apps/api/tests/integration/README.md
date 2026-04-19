# Integration Tests (Postgres-backed)

These tests require **Docker** running locally. `testcontainers` spins up a
throwaway `postgres:17-alpine` container per pytest session and tears it
down at the end. Per-test state isolation is achieved via `TRUNCATE ... CASCADE`.

## Prerequisites
- Docker Desktop / engine running
- Project deps installed with dev extras (`uv sync --dev` or equivalent)

## Run

```bash
# only integration tests (spawns throwaway Postgres via testcontainers)
pytest -m integration apps/api/tests/integration/ -v

# OR point at an existing Postgres (faster for local dev):
TEST_DATABASE_URL=postgresql+psycopg://invest:dev_only_password@localhost:54329/investment_platform \
  pytest -m integration apps/api/tests/integration/ -v

# unit tests only (fast; skips docker)
pytest -m "not integration" -v
```

## Notes
- Container boot is ~5–10s on first use; subsequent test functions reuse it.
- If testcontainers cannot reach the Docker socket, tests will fail at fixture
  setup — this is intentional (they require Docker).
- Tests only exercise ledger + account flows. Corporate actions, dividends,
  and recommendations are out of scope for this batch.
