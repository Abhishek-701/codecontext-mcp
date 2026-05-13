CREATE EXTENSION IF NOT EXISTS vector;

-- Stores every indexed symbol (function, class, method, import) from the watched codebase.
CREATE TABLE IF NOT EXISTS symbols (
    id             BIGSERIAL    PRIMARY KEY,
    name           TEXT         NOT NULL,
    qualified_name TEXT         NOT NULL,
    kind           TEXT         NOT NULL,
    file_path      TEXT         NOT NULL,
    line_start     INTEGER      NOT NULL,
    line_end       INTEGER      NOT NULL,
    docstring      TEXT,
    embedding      vector(384),
    language       TEXT         NOT NULL,
    indexed_at     TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_symbols_name      ON symbols (name);
CREATE INDEX IF NOT EXISTS idx_symbols_file_path ON symbols (file_path);
CREATE INDEX IF NOT EXISTS idx_symbols_kind      ON symbols (kind);
CREATE INDEX IF NOT EXISTS idx_symbols_embedding ON symbols USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- Stores call-graph edges between symbols, tracking which symbol calls which.
CREATE TABLE IF NOT EXISTS relationships (
    id               BIGSERIAL PRIMARY KEY,
    caller_id        BIGINT    NOT NULL REFERENCES symbols(id) ON DELETE CASCADE,
    callee_name      TEXT      NOT NULL,
    callee_id        BIGINT    REFERENCES symbols(id) ON DELETE SET NULL,
    call_site_file   TEXT      NOT NULL,
    call_site_line   INTEGER   NOT NULL,
    context_snippet  TEXT      NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_relationships_caller_id   ON relationships (caller_id);
CREATE INDEX IF NOT EXISTS idx_relationships_callee_id   ON relationships (callee_id);
CREATE INDEX IF NOT EXISTS idx_relationships_callee_name ON relationships (callee_name);

-- Tracks the indexing state of each file for incremental updates and change detection.
CREATE TABLE IF NOT EXISTS file_index (
    file_path     TEXT        PRIMARY KEY,
    content_hash  TEXT        NOT NULL,
    last_indexed  TIMESTAMPTZ NOT NULL DEFAULT now(),
    symbol_count  INTEGER     NOT NULL DEFAULT 0,
    language      TEXT        NOT NULL
);
