# CodeContext — Product Requirements Document

## Problem

LLMs are useful for code questions, but they have no persistent awareness of a
codebase. Every conversation starts from scratch. To get useful answers, a
developer has to manually paste the relevant files — which means they already
have to know which files are relevant. For large or unfamiliar codebases, this
breaks down entirely.

Existing workarounds (pasting files, using grep, scrolling through GitHub) are
manual, context-dependent, and don't compose with agent workflows.

## Solution

CodeContext is a backend service that maintains a live, queryable index of a
codebase. It parses source files into structured symbols, tracks relationships
between them, records git history per symbol, and exposes everything through a
clean MCP tool interface.

An LLM agent with access to CodeContext can answer questions like:
- "What functions call `auth.validate_token`?"
- "Which files changed most in the last 30 days?"
- "Find all functions related to retry logic"
- "What is the full call chain from the API handler to the database?"

Without any file pasting. Without context window limits on large repos.

## Users

Primary: developers using LLM coding assistants (Claude, Cursor, Copilot) on
medium-to-large codebases (10k–500k lines).

Secondary: agent workflows that need programmatic, structured access to
codebase state — CI bots, automated reviewers, refactoring agents.

## MCP Tools (the public API)

| Tool | Input | Output |
|---|---|---|
| `get_symbol` | name, repo_path | Symbol definition, location, docstring |
| `find_callers` | symbol_name, repo_path | All call sites across the repo |
| `get_change_history` | symbol_name, repo_path, limit | Last N git commits touching this symbol |
| `semantic_search` | query, repo_path, limit | Top N symbols matching by meaning |
| `get_file_outline` | file_path, repo_path | All top-level symbols in a file |

Full input/output specs in docs/MCP_TOOLS.md.

## Success criteria

- Claude can answer a cross-file question about a 10k-line Python repo in
  under 500ms end-to-end
- Editing a file updates the index within 1 second
- Renaming a function does not leave stale entries in the index
- All five MCP tools return structured, consistent responses
- The service starts with a single `docker compose up`
- A second language (JavaScript/TypeScript) can be added by adding one
  tree-sitter grammar — no changes to the query or MCP layers

## Out of scope (v1)

- Multi-user auth or access control
- Cloud deployment or managed hosting
- Support for compiled languages (Go, Rust, Java) — Python and JS/TS only
- Real-time collaboration or conflict resolution
- Web UI or dashboard
