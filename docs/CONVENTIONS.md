# CodeContext — Conventions

## Naming

**Files and modules:** `snake_case`. No abbreviations except well-known ones
(`db`, `mcp`, `ast`).

**Classes:** `PascalCase`. Suffix with the role where it clarifies:
`SymbolParser`, `IndexWriter`, `QueryEngine`.

**Functions:** `snake_case`. Use verb_noun form for actions: `parse_file`,
`write_symbols`, `get_symbol`, `find_callers`. Use noun form for constructors
and factories: `db_pool`, `embedding_model`.

**Constants:** `UPPER_SNAKE_CASE`. Defined at module level, never inside
functions.

**Dataclasses:** `PascalCase`. No `Data` or `Model` suffix — the class name
describes the thing: `Symbol`, `CallSite`, `FileRecord`, `Commit`,
`SearchResult`, `IndexResult`.

---

## Dataclasses

All internal data models are `@dataclass`. Use `@dataclass(frozen=True)` for
objects that should not be mutated after creation (Symbol, CallSite, Commit).
Use plain `@dataclass` for objects that are built incrementally (IndexResult).

```python
from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class Symbol:
    id: Optional[int]        # None before DB insert
    name: str
    qualified_name: str
    kind: str                # "function" | "class" | "method" | "import"
    file_path: str
    line_start: int
    line_end: int
    docstring: Optional[str]
    language: str
```

Never use dicts as internal data carriers between modules. If a function
returns structured data, it returns a dataclass, not a dict. Dicts are for
serialization at the MCP boundary only.

---

## Logging

Use the standard `logging` module. Never use `print()`.

```python
import logging
logger = logging.getLogger(__name__)
```

Log levels:
- `DEBUG` — per-file indexing steps, query execution details
- `INFO` — service start/stop, reindex triggers, tool calls received
- `WARNING` — recoverable issues (file parse failed, embedding skipped)
- `ERROR` — unrecoverable issues that affect a specific operation

Always include context in log messages:

```python
# Good
logger.info("Reindexing file", extra={"file": path, "reason": "content_changed"})
logger.error("Parse failed", extra={"file": path, "error": str(e)})

# Bad
logger.info(f"reindexing {path}")
logger.error("something went wrong")
```

---

## Error handling

**Never swallow exceptions silently.** If you catch an exception, either
re-raise it, log it and return a sentinel value, or convert it to a typed
error response.

**DB not found → return None:**
```python
async def get_symbol(name: str, pool) -> Symbol | None:
    row = await pool.fetchrow(queries.GET_SYMBOL, name)
    if row is None:
        return None
    return Symbol(**row)
```

**MCP tool errors → return error dict:**
```python
@mcp.tool()
async def get_symbol_tool(name: str, repo_path: str) -> dict:
    result = await query.exact.get_symbol(name, pool)
    if result is None:
        return {"error": f"Symbol '{name}' not found", "code": "SYMBOL_NOT_FOUND"}
    return dataclasses.asdict(result)
```

**Subprocess errors (git):**
```python
result = subprocess.run(["git", "log", ...], capture_output=True, text=True)
if result.returncode != 0:
    return {"error": "git command failed", "code": "GIT_COMMAND_FAILED",
            "detail": result.stderr.strip()}
```

---

## Async

All DB operations are async. Use `asyncpg` throughout.

```python
# Good
async def get_symbol(name: str, pool: asyncpg.Pool) -> Symbol | None:
    row = await pool.fetchrow(queries.GET_SYMBOL, name)
    ...

# Bad — blocks the event loop
def get_symbol(name: str, conn):
    return conn.execute(...)
```

For CPU-bound operations (tree-sitter parsing, embedding generation), use
`asyncio.get_event_loop().run_in_executor(None, sync_fn, *args)` to avoid
blocking. The watcher daemon uses a separate process for parsing via
`ProcessPoolExecutor`.

---

## SQL queries

All SQL lives in `src/db/queries.py` as module-level string constants.
Named in `UPPER_SNAKE_CASE` matching the operation:

```python
GET_SYMBOL = """
    SELECT id, name, qualified_name, kind, file_path,
           line_start, line_end, docstring, language, indexed_at
    FROM symbols
    WHERE name = $1
    LIMIT 1
"""

FIND_CALLERS = """
    SELECT r.call_site_file, r.call_site_line, r.context_snippet,
           s.name AS caller_name, s.file_path AS caller_file
    FROM relationships r
    JOIN symbols s ON s.id = r.caller_id
    WHERE r.callee_name = $1
"""
```

Never use f-strings to build SQL. Always use asyncpg's `$1`, `$2` parameters.

---

## Tests

**Fixture files** (`tests/fixtures/`) are real source files used as indexing
inputs. Name them descriptively: `simple_functions.py`, `class_with_methods.py`,
`cross_file_caller.py`. Never hardcode source strings inline in tests.

**DB fixture** — `tests/conftest.py` provides a `db_pool` pytest fixture that
connects to a test database, runs the schema, and tears down after each test
session. Tests that need the DB use this fixture; unit tests that don't should
not import it.

```python
@pytest.fixture(scope="session")
async def db_pool():
    pool = await asyncpg.create_pool(os.environ["TEST_POSTGRES_URL"])
    await db.init.run_migrations(pool)
    yield pool
    await pool.close()
```

**Test naming:** `test_{function_name}_{scenario}`:
- `test_get_symbol_returns_none_when_not_found`
- `test_parse_file_extracts_docstring`
- `test_writer_skips_unchanged_file`

---

## Commit messages

Conventional commits, lowercase, imperative mood:

```
feat: add semantic_search MCP tool
fix: handle null docstring in embedding generation
chore: add pgvector index to symbols table
test: add integration test for find_callers
docs: update SCHEMA.md with relationship cascade notes
refactor: split parser into per-language modules
```

One commit per logical change. Do not bundle unrelated fixes.
