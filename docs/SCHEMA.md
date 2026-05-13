# CodeContext — Database Schema

## Overview

Three tables. `symbols` is the core — everything else references it.
`relationships` tracks call-graph edges. `file_index` tracks indexing state
for incremental updates.

The schema SQL lives in `src/db/schema.sql`. Migrations are plain SQL files
in `src/db/migrations/` named `001_initial.sql`, `002_add_x.sql`, etc.

---

## Table: symbols

Stores every indexed symbol (function, class, method, import).

```sql
CREATE TABLE symbols (
    id            BIGSERIAL PRIMARY KEY,
    name          TEXT        NOT NULL,
    qualified_name TEXT       NOT NULL,  -- e.g. "auth.validator.validate_token"
    kind          TEXT        NOT NULL,  -- "function" | "class" | "method" | "import"
    file_path     TEXT        NOT NULL,
    line_start    INTEGER     NOT NULL,
    line_end      INTEGER     NOT NULL,
    docstring     TEXT,                  -- NULL if no docstring
    embedding     vector(384),           -- all-MiniLM-L6-v2 output dimension
    language      TEXT        NOT NULL,  -- "python" | "javascript" | "typescript"
    indexed_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_symbols_name        ON symbols (name);
CREATE INDEX idx_symbols_file_path   ON symbols (file_path);
CREATE INDEX idx_symbols_kind        ON symbols (kind);
CREATE INDEX idx_symbols_embedding   ON symbols USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
```

**Notes:**
- `qualified_name` is `{module_path}.{name}`, dots as separators. Used for
  disambiguation when the same name exists in multiple files.
- `embedding` uses pgvector's `vector(384)` type. The ivfflat index requires
  at least a few hundred rows to be effective — skip the index in dev if the
  repo is small.
- On reindex of a file, all symbols for that `file_path` are deleted and
  re-inserted. No upsert — delete + insert is simpler and avoids stale rows
  from renamed functions.

---

## Table: relationships

Stores call-graph edges between symbols.

```sql
CREATE TABLE relationships (
    id              BIGSERIAL PRIMARY KEY,
    caller_id       BIGINT      NOT NULL REFERENCES symbols(id) ON DELETE CASCADE,
    callee_name     TEXT        NOT NULL,  -- name as written at the call site
    callee_id       BIGINT      REFERENCES symbols(id) ON DELETE SET NULL,
    call_site_file  TEXT        NOT NULL,
    call_site_line  INTEGER     NOT NULL,
    context_snippet TEXT        NOT NULL   -- 1-3 lines around the call site
);

CREATE INDEX idx_relationships_caller_id  ON relationships (caller_id);
CREATE INDEX idx_relationships_callee_id  ON relationships (callee_id);
CREATE INDEX idx_relationships_callee_name ON relationships (callee_name);
```

**Notes:**
- `callee_id` is nullable. If the callee is defined outside the indexed repo
  (stdlib, third-party), `callee_id` is NULL and only `callee_name` is stored.
- `ON DELETE CASCADE` on `caller_id` — when a file is reindexed and its
  symbols deleted, outgoing call edges are automatically cleaned up.
- `ON DELETE SET NULL` on `callee_id` — if the callee symbol is deleted
  (e.g. the function was removed), the edge is preserved with `callee_id=NULL`
  rather than dropped. This avoids silently losing call-site records.
- `context_snippet` is the line of the call plus one line before and after,
  joined by `\n`. Extracted during parsing, not queried from disk at serve time.

---

## Table: file_index

Tracks the indexing state of each file for incremental updates.

```sql
CREATE TABLE file_index (
    file_path     TEXT        PRIMARY KEY,
    content_hash  TEXT        NOT NULL,  -- SHA-256 hex digest of file content
    last_indexed  TIMESTAMPTZ NOT NULL DEFAULT now(),
    symbol_count  INTEGER     NOT NULL DEFAULT 0,
    language      TEXT        NOT NULL
);
```

**Notes:**
- `content_hash` is compared before every reindex. If it matches the current
  file hash, indexing is skipped entirely.
- `symbol_count` is updated after each reindex. Useful for debugging and
  for surfacing files with unexpectedly zero symbols.
- When a file is deleted from the filesystem, its row should be deleted from
  `file_index` and its symbols will cascade-delete via the symbols table's
  `file_path` column. The watcher handles this on DELETE events.

---

## pgvector setup

pgvector must be enabled before running migrations:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

This runs as part of `src/db/init.py` on startup, before any migrations.

Cosine similarity query pattern (used in `src/db/queries.py`):

```sql
SELECT id, name, file_path, line_start, docstring,
       1 - (embedding <=> $1::vector) AS similarity
FROM symbols
WHERE embedding IS NOT NULL
ORDER BY embedding <=> $1::vector
LIMIT $2;
```

`<=>` is the cosine distance operator. `1 - distance` gives similarity.
Always filter `WHERE embedding IS NOT NULL` — symbols without docstrings
may have NULL embeddings if the embedding step failed.

---

## Query patterns reference

These are the queries implemented in `src/db/queries.py`. Listed here so
the schema can be validated against them.

```sql
-- get_symbol
SELECT * FROM symbols WHERE name = $1 LIMIT 1;

-- find_callers
SELECT r.call_site_file, r.call_site_line, r.context_snippet,
       s.name AS caller_name, s.file_path AS caller_file
FROM relationships r
JOIN symbols s ON s.id = r.caller_id
WHERE r.callee_name = $1;

-- get_file_outline
SELECT name, kind, line_start, line_end, docstring
FROM symbols
WHERE file_path = $1
ORDER BY line_start;

-- delete symbols for reindex
DELETE FROM symbols WHERE file_path = $1;

-- upsert file_index
INSERT INTO file_index (file_path, content_hash, last_indexed, symbol_count, language)
VALUES ($1, $2, now(), $3, $4)
ON CONFLICT (file_path) DO UPDATE
SET content_hash = EXCLUDED.content_hash,
    last_indexed = EXCLUDED.last_indexed,
    symbol_count = EXCLUDED.symbol_count;
```
