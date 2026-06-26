# Contributing to CodeContext

## Dev setup

```bash
pip install -e ".[dev]"
cp .env.example .env
docker compose up -d postgres
```

Set `REPO_PATH` in `.env` to the repo you want indexed. For DB-backed tests, export `TEST_POSTGRES_URL=postgresql://codecontext:codecontext@localhost:5433/codecontext`.

## Tests

```bash
pytest tests/ -m "not integration"   # unit tests, no database
pytest tests/integration/            # pipeline tests (needs TEST_POSTGRES_URL)
pytest tests/                        # everything
```

Integration tests use a real Postgres instance — no mocks. Every new query or indexer function needs at least one test.

## Project layout

| Directory | Responsibility |
|---|---|
| `src/watcher/` | Filesystem watching, event debouncing, daemon entrypoint |
| `src/indexer/` | tree-sitter parsing, DB writes, embeddings after index |
| `src/db/` | Schema, migrations, connection pool, SQL query constants |
| `src/query/` | Exact and semantic query functions (no SQL outside `db/queries.py`) |
| `src/mcp/` | FastMCP server and tool handlers — thin wrappers over `src/query/` |

Read `docs/ARCHITECTURE.md` before changing boundaries between layers.

## Rules

- **One component per PR** — watcher, indexer, query, and MCP changes should not land in the same pull request unless they are tightly coupled.
- **Tests required** — mirror source layout under `tests/`; use fixtures in `tests/fixtures/` for parser/indexer inputs.
- **`ruff check .` must pass** before merge.
- **Conventional commits** — `feat:`, `fix:`, `test:`, `chore:`, `docs:` in imperative mood (e.g. `feat: add find_callers MCP tool`).

Do not put raw SQL outside `src/db/queries.py`. Do not import `src.db` from `src/mcp/`.
