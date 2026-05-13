"""Module-level SQL query constants for all database operations."""

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

GET_FILE_OUTLINE = """
    SELECT name, kind, line_start, line_end, docstring
    FROM symbols
    WHERE file_path = $1
    ORDER BY line_start
"""

DELETE_SYMBOLS_FOR_FILE = """
    DELETE FROM symbols WHERE file_path = $1
"""

UPSERT_FILE_INDEX = """
    INSERT INTO file_index (file_path, content_hash, last_indexed, symbol_count, language)
    VALUES ($1, $2, now(), $3, $4)
    ON CONFLICT (file_path) DO UPDATE
    SET content_hash  = EXCLUDED.content_hash,
        last_indexed  = EXCLUDED.last_indexed,
        symbol_count  = EXCLUDED.symbol_count
"""

SEMANTIC_SEARCH = """
    SELECT id, name, file_path, line_start, docstring,
           1 - (embedding <=> $1::vector) AS similarity
    FROM symbols
    WHERE embedding IS NOT NULL
    ORDER BY embedding <=> $1::vector
    LIMIT $2
"""

INSERT_SYMBOL = """
    INSERT INTO symbols
        (name, qualified_name, kind, file_path, line_start, line_end, docstring, language)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
    RETURNING id
"""

INSERT_RELATIONSHIP = """
    INSERT INTO relationships
        (caller_id, callee_name, callee_id, call_site_file, call_site_line, context_snippet)
    VALUES ($1, $2, $3, $4, $5, $6)
"""

GET_FILE_HASH = """
    SELECT content_hash FROM file_index WHERE file_path = $1
"""

GET_SYMBOL_IDS_FOR_FILE = """
    SELECT id FROM symbols WHERE file_path = $1
"""

GET_SYMBOL_BY_ID = """
    SELECT name, docstring FROM symbols WHERE id = $1
"""

UPDATE_SYMBOL_EMBEDDING = """
    UPDATE symbols SET embedding = $1 WHERE id = $2
"""

RESOLVE_CALLEE_ID = """
    SELECT id FROM symbols WHERE name = $1 LIMIT 1
"""

DELETE_FILE_INDEX = """
    DELETE FROM file_index WHERE file_path = $1
"""
