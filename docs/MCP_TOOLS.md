# CodeContext — MCP Tools Specification

## Overview

Five tools. Each is a thin wrapper over the query engine.
All tools return dicts — never raise exceptions to the MCP client.
On error, return `{"error": "<message>", "code": "<ERROR_CODE>"}`.

Tool handlers live in `src/mcp/server.py`.
All business logic lives in `src/query/exact.py` or `src/query/semantic.py`.

---

## Tool: get_symbol

Returns the definition and metadata for a named symbol.

**Input:**
```json
{
  "name": "validate_token",
  "repo_path": "/home/user/myproject"
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `name` | string | yes | Symbol name, exact match |
| `repo_path` | string | yes | Absolute path to the indexed repo |

**Output (success):**
```json
{
  "name": "validate_token",
  "qualified_name": "auth.validator.validate_token",
  "kind": "function",
  "file_path": "auth/validator.py",
  "line_start": 42,
  "line_end": 61,
  "docstring": "Validates a JWT token and returns the decoded payload.",
  "language": "python",
  "indexed_at": "2024-01-15T10:23:00Z"
}
```

**Output (error):**
```json
{
  "error": "Symbol 'validate_token' not found in repo",
  "code": "SYMBOL_NOT_FOUND"
}
```

**Error codes:** `SYMBOL_NOT_FOUND`, `REPO_NOT_INDEXED`

**Notes:**
- If multiple symbols share the same name (across files), returns the first
  match ordered by `file_path` alphabetically. A future version may return
  all matches — do not assume uniqueness in the handler.
- `repo_path` is used to scope the query to a specific repo in multi-repo
  deployments. For v1, only one repo is indexed at a time, but include the
  parameter now for forward compatibility.

---

## Tool: find_callers

Returns all locations in the codebase that call a named symbol.

**Input:**
```json
{
  "symbol_name": "validate_token",
  "repo_path": "/home/user/myproject"
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `symbol_name` | string | yes | Name of the callee to search for |
| `repo_path` | string | yes | Absolute path to the indexed repo |

**Output (success):**
```json
{
  "symbol_name": "validate_token",
  "caller_count": 3,
  "callers": [
    {
      "caller_name": "handle_request",
      "caller_file": "api/handlers.py",
      "call_site_file": "api/handlers.py",
      "call_site_line": 88,
      "context_snippet": "  token = request.headers.get('Authorization')\n  payload = validate_token(token)\n  if not payload:"
    }
  ]
}
```

**Output (no callers):**
```json
{
  "symbol_name": "validate_token",
  "caller_count": 0,
  "callers": []
}
```

**Error codes:** `REPO_NOT_INDEXED`

**Notes:**
- Returns an empty `callers` list (not an error) if the symbol exists but
  has no callers.
- `context_snippet` is stored at index time — it is not read from disk at
  query time. It may be slightly stale if the file changed without reindexing.

---

## Tool: get_change_history

Returns the git commit history for lines touched by a named symbol.

**Input:**
```json
{
  "symbol_name": "validate_token",
  "repo_path": "/home/user/myproject",
  "limit": 10
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `symbol_name` | string | yes | Symbol to look up history for |
| `repo_path` | string | yes | Must be a git repo root or subdirectory |
| `limit` | integer | no | Max commits to return, default 10, max 50 |

**Output (success):**
```json
{
  "symbol_name": "validate_token",
  "file_path": "auth/validator.py",
  "commit_count": 3,
  "commits": [
    {
      "hash": "a3f2c1d",
      "author": "Jane Smith",
      "date": "2024-01-10T14:32:00Z",
      "message": "fix: handle expired token edge case",
      "lines_changed": 4
    }
  ]
}
```

**Output (error):**
```json
{
  "error": "Symbol 'validate_token' not found",
  "code": "SYMBOL_NOT_FOUND"
}
```

**Error codes:** `SYMBOL_NOT_FOUND`, `NOT_A_GIT_REPO`, `GIT_COMMAND_FAILED`

**Implementation notes:**
- First queries the DB to get `file_path`, `line_start`, `line_end` for the
  symbol.
- Then runs `git log -L {line_start},{line_end}:{file_path}` via subprocess
  in the `repo_path` directory.
- Does not store git history in the DB. Always queries git directly.
- If `git` is not available or the path is not a git repo, return
  `NOT_A_GIT_REPO` error — do not crash.

---

## Tool: semantic_search

Returns symbols whose meaning matches a natural language query.

**Input:**
```json
{
  "query": "functions that handle authentication errors",
  "repo_path": "/home/user/myproject",
  "limit": 10
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `query` | string | yes | Natural language search query |
| `repo_path` | string | yes | Absolute path to the indexed repo |
| `limit` | integer | no | Max results, default 10, max 50 |

**Output (success):**
```json
{
  "query": "functions that handle authentication errors",
  "result_count": 4,
  "results": [
    {
      "name": "handle_auth_error",
      "qualified_name": "api.errors.handle_auth_error",
      "kind": "function",
      "file_path": "api/errors.py",
      "line_start": 14,
      "docstring": "Handles 401 and 403 errors from the auth service.",
      "similarity": 0.87
    }
  ]
}
```

**Output (no results):**
```json
{
  "query": "...",
  "result_count": 0,
  "results": []
}
```

**Error codes:** `REPO_NOT_INDEXED`, `EMBEDDING_MODEL_UNAVAILABLE`

**Notes:**
- Only returns symbols with non-null embeddings. Symbols without docstrings
  may have no embedding if the fallback embedding (from name only) failed.
- `similarity` is a float 0–1. Results are ordered descending by similarity.
  A similarity below 0.5 is usually a weak match — callers can use this to
  filter if needed.
- The embedding model is loaded once at process startup. If it fails to load,
  this tool returns `EMBEDDING_MODEL_UNAVAILABLE` on every call.

---

## Tool: get_file_outline

Returns all top-level symbols in a file, in line order.

**Input:**
```json
{
  "file_path": "auth/validator.py",
  "repo_path": "/home/user/myproject"
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `file_path` | string | yes | Relative path from repo root |
| `repo_path` | string | yes | Absolute path to the indexed repo |

**Output (success):**
```json
{
  "file_path": "auth/validator.py",
  "language": "python",
  "symbol_count": 4,
  "symbols": [
    {
      "name": "TokenValidator",
      "kind": "class",
      "line_start": 8,
      "line_end": 95,
      "docstring": "Validates and decodes JWT tokens."
    },
    {
      "name": "validate_token",
      "kind": "method",
      "line_start": 42,
      "line_end": 61,
      "docstring": "Validates a JWT token and returns the decoded payload."
    }
  ]
}
```

**Output (error):**
```json
{
  "error": "File 'auth/validator.py' has not been indexed",
  "code": "FILE_NOT_INDEXED"
}
```

**Error codes:** `FILE_NOT_INDEXED`, `REPO_NOT_INDEXED`

**Notes:**
- Returns all symbols for the file regardless of nesting depth (top-level
  functions AND methods inside classes). Ordered by `line_start`.
- This is intentionally simpler than a full AST — it's a flat list, not a
  tree. Good enough for "what's in this file" questions.
- `FILE_NOT_INDEXED` means the file exists but has never been indexed, or
  was indexed and had zero symbols extracted.

---

## Shared error codes reference

| Code | Meaning |
|---|---|
| `SYMBOL_NOT_FOUND` | No symbol with that name in the index |
| `FILE_NOT_INDEXED` | File path not present in `file_index` |
| `REPO_NOT_INDEXED` | `repo_path` has no indexed files at all |
| `NOT_A_GIT_REPO` | `repo_path` is not a git repository |
| `GIT_COMMAND_FAILED` | `git` subprocess returned non-zero exit |
| `EMBEDDING_MODEL_UNAVAILABLE` | sentence-transformers model failed to load |
