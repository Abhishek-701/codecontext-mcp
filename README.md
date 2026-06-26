# CodeContext

A live-indexed codebase context server that gives LLM agents structured, queryable access to symbols, call graphs, and git history — without pasting files into the chat.

## The problem

LLM coding assistants start every conversation with no memory of your repository. To answer a question about `validate_token`, you have to know which files matter and paste them in yourself. That works for small snippets; on a large or unfamiliar codebase it breaks down fast. Manual grep, scrolling GitHub, and one-off file dumps do not compose with agent workflows and do not stay current as the code changes.

## How it works

CodeContext watches your repository for changes, parses each edited Python or JavaScript/TypeScript file with tree-sitter, and writes symbols, call relationships, and semantic embeddings into PostgreSQL. A separate MCP server process exposes that index as five structured tools any compatible agent can call. The watcher handles filesystem events and debouncing; the indexer parses and persists; the database holds the live index; the MCP server answers queries — each layer only talks to its neighbor.

## MCP tools

| Tool | What it answers | Key inputs |
|---|---|---|
| `get_symbol` | Use this when you need the definition, file location, and docstring for a named function or class. | `name`, `repo_path` |
| `find_callers` | Use this when you need every place in the repo that calls a given function or method. | `symbol_name`, `repo_path` |
| `get_change_history` | Use this when you need recent git commits that touched a symbol's lines and why they changed. | `symbol_name`, `repo_path`, `limit` |
| `semantic_search` | Use this when you know the concept (e.g. "token refresh") but not the exact symbol name. | `query_text`, `repo_path`, `limit` |
| `get_file_outline` | Use this when you need a quick map of everything defined in one file, in line order. | `file_path`, `repo_path` |

All tools return JSON dicts. Errors return `{"error": "...", "code": "ERROR_CODE"}` — never raised exceptions.

## Quick start

```bash
git clone https://github.com/Abhishek-701/codecontext-mcp.git
cd codecontext-mcp
cp .env.example .env
# Edit .env: set REPO_PATH to the absolute path of the repo you want to index
docker compose up
```

This starts PostgreSQL (with pgvector) on host port **5433** (avoids conflict with a local Postgres on 5432), runs schema migrations once, performs an initial index of `REPO_PATH`, then launches the watcher. The watcher uses polling mode inside Docker so file changes on Windows bind mounts are detected. Edit a file under `REPO_PATH` to trigger incremental reindexing.

The MCP server is **not** run in Docker — it uses stdio transport and must run on the host (see Claude Desktop config below).

To use CodeContext from Claude Desktop, add the MCP server config below to `%APPDATA%\Claude\claude_desktop_config.json` on Windows or `~/Library/Application Support/Claude/claude_desktop_config.json` on macOS. Set `cwd` to your clone path, point `POSTGRES_URL` at the running Postgres instance (`postgresql://codecontext:codecontext@localhost:5433/codecontext` when using Docker Compose), and restart Claude Desktop. The hammer icon in a new chat should list the `codecontext` tools.

## Claude Desktop config

```json
{
  "mcpServers": {
    "codecontext": {
      "command": "python",
      "args": ["-m", "src.mcp.server"],
      "cwd": "/absolute/path/to/codecontext",
      "env": {
        "POSTGRES_URL": "postgresql://codecontext:codecontext@localhost:5433/codecontext",
        "EMBEDDING_MODEL": "all-MiniLM-L6-v2",
        "PYTHONPATH": "/absolute/path/to/codecontext"
      }
    }
  }
}
```

On Windows, use full paths (e.g. `C:\\Users\\you\\codecontext-mcp`) and the Python executable you installed with (`where python`).

## Why not just ask Claude directly?

Claude in the IDE already sees your open files, but that view is a snapshot of whatever fits in context — not a queryable index of the whole repo. CodeContext maintains a live symbol graph and embedding index that updates on save, so agents can chain exact lookups (`find_callers` → `get_symbol` → `get_change_history`) without you curating each file. Tool responses are structured dicts with stable fields (file, line, docstring, similarity), which is easier to reason over than prose summaries. It complements Claude; it does not replace reading code when you are already looking at the right file.

## Architecture

```
  Codebase (filesystem)
         |
         v
     [Watcher]  — watchdog, debounced file events
         |
         v
     [Indexer]  — tree-sitter parse → symbols + relationships + embeddings
         |
         v
   [PostgreSQL] — symbols, relationships, file_index, pgvector
         |
         v
  [Query Engine] — exact SQL + semantic search (+ git log on demand)
         |
         v
    [MCP Server] — five FastMCP tools for LLM agents
```

Git history for `get_change_history` is read from `git log` at query time; it is not stored in the database.

## Development

```bash
pip install -e ".[dev]"
cp .env.example .env
docker compose up -d postgres
pytest tests/ -m "not integration"    # fast, no DB needed
pytest tests/                          # full suite, needs TEST_POSTGRES_URL
```

Set `TEST_POSTGRES_URL` for integration tests (same credentials as `POSTGRES_URL` in Compose). Run `ruff check .` before opening a PR.

## Stack

- **Python 3.12 + FastMCP** — async-first server with a standard MCP tool surface for Claude, Cursor, and other agents.
- **tree-sitter** — fast, incremental AST parsing for Python and JavaScript/TypeScript without running the interpreter.
- **PostgreSQL 16 + pgvector** — one store for relational symbol data and cosine-similarity semantic search.
- **asyncpg** — non-blocking Postgres access throughout the watcher and query path.
- **sentence-transformers** — local `all-MiniLM-L6-v2` embeddings for docstring-aware semantic search without an API key.
- **watchdog** — cross-platform filesystem notifications with debouncing for incremental reindexing.
- **Docker Compose** — one command to run Postgres, migrations, initial index, and watcher for local development.
