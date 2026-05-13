# CodeContext — Claude Code instructions

## What this project is
A persistent, live-indexed codebase context server with an MCP interface.
It watches a codebase, keeps a queryable index of symbols and relationships,
and exposes structured MCP tools so LLM agents can query code they can't
fit in a context window.

## Stack
- Python 3.12
- FastMCP (MCP server)
- tree-sitter + tree-sitter-python + tree-sitter-javascript (parsing)
- PostgreSQL 16 + pgvector (storage + semantic search)
- asyncpg (async DB driver)
- sentence-transformers, model: all-MiniLM-L6-v2 (embeddings)
- watchdog (filesystem events)
- pytest + pytest-asyncio (tests)
- ruff (linting)
- Docker Compose (local dev)

## Project layout
```
src/
  watcher/        — filesystem watching and event debouncing
  indexer/        — tree-sitter parsing and DB writes
  query/          — exact SQL queries and pgvector semantic search
  mcp/            — FastMCP server and tool definitions
  db/             — schema, migrations, connection pool, query helpers
tests/
  fixtures/       — sample source files used in tests
  watcher/
  indexer/
  query/
  mcp/
  db/
docs/             — specs (PRD, ARCHITECTURE, SCHEMA, MCP_TOOLS, CONVENTIONS)
                    never modify docs/ unless explicitly asked
```

## Boundaries — where things live
- All raw SQL lives in `src/db/queries.py` only. No SQL anywhere else.
- All DB access goes through the pool from `src/db/init.py`. No direct connections elsewhere.
- MCP tool handlers in `src/mcp/server.py` call `src/query/` functions only — no DB imports in mcp/.
- Embedding generation lives in `src/query/semantic.py`. Nothing else generates embeddings.
- Filesystem events are handled only in `src/watcher/`. The indexer does not import watchdog.

## Code rules
- No function longer than 40 lines. If it's getting long, split it and explain why in a comment.
- Every public function and class needs a docstring. One sentence minimum.
- Use dataclasses for all internal data models (Symbol, CallSite, FileRecord).
- Type-annotate every function signature. No `Any` unless unavoidable — explain it if used.
- Async all the way down for DB access. No sync DB calls.
- Use conventional commits: `feat:`, `fix:`, `chore:`, `test:`, `docs:`

## Error handling
- Never raise bare exceptions. Always use a specific exception type.
- DB not found → return `None`, not an exception. Let the caller decide.
- MCP tool errors → return `{"error": "...", "code": "SYMBOL_NOT_FOUND"}` dict, not a raised exception.
- Log errors with `logging.error(...)`, include the file path and operation name.

## Testing rules
- Every new function needs at least one test.
- Tests that touch the DB must use a real test DB, not mocks. Use the `db_pool` pytest fixture.
- Fixture source files live in `tests/fixtures/`. Never hardcode source strings inline in tests.
- Test file mirrors source file: `src/indexer/parser.py` → `tests/indexer/test_parser.py`
- Run `ruff check . && pytest` before considering any task done. Fix all failures.

## What to do when starting a task
1. Read the relevant doc in `docs/` before writing any code.
2. Check `src/db/queries.py` before writing any new query — it may already exist.
3. Check existing dataclasses in `src/indexer/models.py` before creating new ones.
4. Write the test file first if the task is a new function or module.

## Never do this
- No raw SQL outside `src/db/queries.py`
- No `import watchdog` outside `src/watcher/`
- No `from src.db` imports inside `src/mcp/`
- No synchronous DB calls
- No `print()` statements — use `logging`
- No skipping tests because "it's just a helper function"
- No TODO comments left in committed code — either implement it or open an issue

## Environment variables (all required)
```
POSTGRES_URL        — asyncpg connection string, e.g. postgresql://user:pass@localhost/codecontext
WATCH_PATH          — absolute path to the repo being indexed
EMBEDDING_MODEL     — sentence-transformers model name, default: all-MiniLM-L6-v2
LOG_LEVEL           — DEBUG | INFO | WARNING, default: INFO
```

## Running locally
```bash
docker compose up -d          # start postgres
python -m src.watcher.daemon  # start watcher + indexer
python -m src.mcp.server      # start MCP server (separate terminal)
pytest                        # run tests
ruff check .                  # lint
```

## Key docs to read for each area
- Adding a new MCP tool → read docs/MCP_TOOLS.md first
- Changing the DB schema → read docs/SCHEMA.md first, update schema.sql, then write a migration
- Changing indexing logic → read docs/ARCHITECTURE.md "Indexer" section first
- Anything unclear about error handling or naming → read docs/CONVENTIONS.md