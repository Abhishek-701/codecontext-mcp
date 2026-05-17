# CodeContext MCP

A persistent, live-indexed codebase context server with an MCP interface. It watches a codebase, keeps a queryable index of symbols and relationships, and exposes structured tools so LLM agents can query code they can't fit in a context window.

## How it works

1. **Watcher** monitors the repo for file changes using `watchdog` and debounces rapid edits.
2. **Indexer** parses changed files with `tree-sitter`, extracts symbols (functions, classes, methods), and writes them to PostgreSQL.
3. **Query layer** answers exact lookups (by name or file) and semantic search (via `pgvector` + sentence-transformers embeddings).
4. **MCP server** exposes five tools over FastMCP so any MCP-compatible agent can call them.

## Stack

| Layer | Technology |
|---|---|
| Parser | tree-sitter (Python + JavaScript grammars) |
| Storage | PostgreSQL 16 + pgvector |
| DB driver | asyncpg |
| Embeddings | sentence-transformers `all-MiniLM-L6-v2` |
| FS events | watchdog |
| MCP server | FastMCP |
| Tests | pytest + pytest-asyncio |
| Lint | ruff |

## MCP Tools

| Tool | Description |
|---|---|
| `get_symbol` | Return definition, location, and docstring for a named symbol |
| `find_callers` | Return all call sites of a symbol across the indexed repo |
| `get_change_history` | Return git commit history for the lines touched by a symbol |
| `semantic_search` | Find symbols whose meaning matches a natural language query |
| `get_file_outline` | Return all indexed symbols in a file, ordered by line number |

All tools return plain dicts. Errors return `{"error": "...", "code": "ERROR_CODE"}` — they never raise exceptions to the client.

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
docs/             — PRD, ARCHITECTURE, SCHEMA, MCP_TOOLS, CONVENTIONS
```

## Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `POSTGRES_URL` | yes | — | asyncpg connection string, e.g. `postgresql://user:pass@localhost/codecontext` |
| `WATCH_PATH` | yes | — | Absolute path to the repo being indexed |
| `EMBEDDING_MODEL` | no | `all-MiniLM-L6-v2` | sentence-transformers model name |
| `LOG_LEVEL` | no | `INFO` | `DEBUG`, `INFO`, or `WARNING` |

## Quick start

```bash
# 1. Start PostgreSQL with pgvector
docker compose up -d

# 2. Set environment variables
export POSTGRES_URL=postgresql://codecontext:codecontext@localhost/codecontext
export WATCH_PATH=/path/to/repo/to/index

# 3. Start the watcher (indexes the repo and watches for changes)
python -m src.watcher.daemon

# 4. Start the MCP server (separate terminal)
python -m src.mcp.server
```

The default Docker Compose connection string is `postgresql://codecontext:codecontext@localhost/codecontext`.

## Development

```bash
pytest          # run tests (requires a running test DB)
ruff check .    # lint
```

Tests that touch the DB use a real PostgreSQL connection — no mocks. Set `POSTGRES_URL` before running.
