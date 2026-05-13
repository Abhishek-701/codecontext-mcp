# CodeContext — Architecture

## Overview

Four components form a pipeline. Each has a single responsibility and a clean
interface to the next. No component reaches past its neighbor.

```
Codebase (filesystem)
      |
      v
  [Watcher]          — detects file changes, debounces, triggers indexer
      |
      v
  [Indexer]          — parses source → extracts symbols → writes to DB
      |
      v
  [PostgreSQL]       — stores symbols, relationships, file index, embeddings
      |
      v
  [Query Engine]     — exact SQL queries + pgvector semantic search
      |
      v
  [MCP Server]       — exposes 5 structured tools to LLM agents
```

Git history is pulled by the Query Engine directly (via subprocess `git log`)
when `get_change_history` is called. It is not stored in the DB.

---

## Component: Watcher

**Responsibility:** Detect source file changes and trigger incremental reindexing.

**Implementation:** `watchdog` library watching `WATCH_PATH` recursively.
Only `.py` and `.js/.ts` files trigger reindex events. Events are debounced
with a 300ms window — rapid successive saves to the same file produce one
reindex, not many.

**Interface out:** Calls `indexer.pipeline.reindex_file(path)` for each
changed file.

**Failure mode:** If the indexer raises, log the error and continue watching.
The watcher must never crash on a bad file.

---

## Component: Indexer

**Responsibility:** Parse a source file and write its symbols and relationships
to the database.

**Two stages:**

1. **Parser** (`src/indexer/parser.py`) — uses `tree-sitter` to walk the AST
   and extract Symbol objects. Handles: function defs, class defs, imports,
   method defs. Extracts docstrings from the first string literal following a
   `def` or `class` node.

2. **Writer** (`src/indexer/writer.py`) — takes a list of Symbols and writes
   them to PostgreSQL. Before writing, computes the SHA-256 hash of the file
   content and checks `file_index`. If the hash matches the stored hash, skip.
   This is the incremental update mechanism.

**Relationship extraction:** After writing symbols for a file, the writer
queries the `symbols` table to resolve call sites to symbol IDs and writes
rows to the `relationships` table.

**Embedding generation:** After symbols are written, the writer generates
embeddings for each symbol's docstring (or name if no docstring) and stores
them in `symbols.embedding` via pgvector.

**Interface in:** `reindex_file(path: str, pool: asyncpg.Pool) -> IndexResult`

**Interface out:** Writes to `symbols`, `relationships`, `file_index` tables.

---

## Component: Query Engine

**Two modules:**

### exact.py
Structured queries against the `symbols` and `relationships` tables.
All SQL lives in `src/db/queries.py` — `exact.py` calls named query functions,
never writes SQL directly.

Functions:
- `get_symbol(name, pool)` → `Symbol | None`
- `find_callers(symbol_name, pool)` → `list[CallSite]`
- `get_file_outline(file_path, pool)` → `list[Symbol]`
- `get_change_history(symbol_name, repo_path, limit)` → `list[Commit]`
  (calls `git log -L` via subprocess, does not touch DB)

### semantic.py
Vector similarity search using pgvector.

Functions:
- `semantic_search(query, pool, limit)` → `list[SearchResult]`
- `generate_embedding(text)` → `list[float]`
  (loads the sentence-transformers model once at import time)

---

## Component: MCP Server

**Responsibility:** Expose query engine functions as callable MCP tools.

**Implementation:** FastMCP. Each tool is a thin wrapper — validates input,
calls the appropriate `src/query/` function, formats the response.

No DB imports in this layer. No business logic. If a query function returns
`None`, the tool returns `{"error": "not found", "code": "SYMBOL_NOT_FOUND"}`.

Tool definitions live in `src/mcp/server.py`. If the tool list grows, split
into `src/mcp/tools/` with one file per tool.

---

## Data flow: file edit → query

1. Developer saves `auth/validator.py`
2. Watcher detects change, debounces 300ms
3. Watcher calls `reindex_file("auth/validator.py")`
4. Indexer computes SHA-256 of file content
5. Indexer checks `file_index` — hash differs, proceed
6. Parser extracts 3 functions, 1 class from the file
7. Writer deletes old symbols for this file, inserts new ones
8. Writer resolves call sites, updates `relationships`
9. Writer generates embeddings, stores in `symbols.embedding`
10. Writer updates `file_index` with new hash and timestamp
11. LLM calls `find_callers("validate_token")`
12. MCP server calls `query.exact.find_callers(...)`
13. Query engine runs SQL against `relationships` join `symbols`
14. Returns list of CallSite objects with file, line, context snippet
15. MCP server serializes to dict, returns to LLM

Total time target: steps 2–10 under 1 second, steps 11–15 under 200ms.

---

## Incremental indexing

The content hash in `file_index` is the sole mechanism for skipping unchanged
files. The flow:

```
hash = sha256(file_content)
existing = SELECT content_hash FROM file_index WHERE file_path = $1
if existing and existing.content_hash == hash:
    return IndexResult(skipped=True)
else:
    DELETE FROM symbols WHERE file_path = $1
    INSERT new symbols ...
    UPDATE file_index SET content_hash = $hash, last_indexed = now()
```

This means a rename (file_path changes) is treated as a delete + insert, which
is correct — the old path's symbols are cleaned up automatically.

---

## Language support

Language support is isolated in the Parser. Adding a new language requires:
1. `pip install tree-sitter-{language}`
2. A new parser class in `src/indexer/parsers/{language}.py` implementing the
   `BaseParser` interface
3. A mapping from file extension to parser class in `src/indexer/parser.py`

No changes to the Writer, Query Engine, or MCP Server.

---

## Deployment (local dev)

```
docker compose up -d     # postgres:16 with pgvector
python -m src.db.init    # run schema migrations
python -m src.watcher.daemon   # watcher + indexer process
python -m src.mcp.server       # MCP server process
```

Two processes. The watcher and MCP server are intentionally separate — the
watcher does CPU-bound parsing, the MCP server handles I/O-bound queries. They
share the same PostgreSQL instance.
