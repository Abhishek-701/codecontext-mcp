"""Python source parser using tree-sitter."""

import ast
import logging
import pathlib
from collections.abc import Iterator
from typing import ClassVar, Optional

import tree_sitter_python as tspython
from tree_sitter import Language, Node, Parser

from src.indexer.models import CallSite, Symbol
from src.indexer.parsers.base import BaseParser

logger = logging.getLogger(__name__)


class PythonParser(BaseParser):
    """Parses Python source files with tree-sitter to extract symbols and call sites."""

    # Grammar and parser loaded once at class level — not per parse() call.
    _language: ClassVar[Language] = Language(tspython.language())
    _ts_parser: ClassVar[Parser] = Parser(_language)

    def parse(self, file_path: str) -> tuple[list[Symbol], list[CallSite]]:
        """Parse a Python file; returns ([], []) and logs a warning on any error."""
        try:
            source_bytes = pathlib.Path(file_path).read_bytes()
            source_lines = source_bytes.decode("utf-8").splitlines()
            tree = self._ts_parser.parse(source_bytes)
            module_path = self._module_path(file_path)
            symbols = self._extract_symbols(tree.root_node, module_path, file_path)
            calls = self._extract_calls(tree.root_node, source_lines, file_path)
            return symbols, calls
        except Exception as e:
            logger.warning("Parse failed", extra={"file": file_path, "error": str(e)})
            return [], []

    # ------------------------------------------------------------------ symbols

    def _module_path(self, file_path: str) -> str:
        """Derive dotted module path from a relative file path."""
        return file_path.replace("\\", "/").removesuffix(".py").replace("/", ".").lstrip(".")

    def _extract_symbols(
        self,
        node: Node,
        module_path: str,
        file_path: str,
        class_name: Optional[str] = None,
    ) -> list[Symbol]:
        """Recursively walk an AST node and collect all Symbol objects."""
        symbols: list[Symbol] = []
        for child in node.children:
            if child.type == "class_definition":
                sym = self._make_class_symbol(child, module_path, file_path)
                if sym:
                    symbols.append(sym)
                    body = child.child_by_field_name("body")
                    if body:
                        symbols.extend(
                            self._extract_symbols(body, module_path, file_path, sym.name)
                        )
            elif child.type == "decorated_definition":
                inner = self._unwrap_decorated(child)
                if inner and inner.type == "function_definition":
                    sym = self._make_function_symbol(inner, module_path, file_path, class_name)
                    if sym:
                        symbols.append(sym)
            elif child.type == "function_definition":
                sym = self._make_function_symbol(child, module_path, file_path, class_name)
                if sym:
                    symbols.append(sym)
            elif child.type in ("import_statement", "import_from_statement"):
                symbols.extend(self._make_import_symbols(child, module_path, file_path))
            else:
                symbols.extend(
                    self._extract_symbols(child, module_path, file_path, class_name)
                )
        return symbols

    def _make_function_symbol(
        self,
        node: Node,
        module_path: str,
        file_path: str,
        class_name: Optional[str] = None,
    ) -> Optional[Symbol]:
        """Build a Symbol for a function_definition node."""
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return None
        name = name_node.text.decode("utf-8")
        kind = "method" if class_name else "function"
        qname = f"{module_path}.{class_name}.{name}" if class_name else f"{module_path}.{name}"
        body = node.child_by_field_name("body")
        return Symbol(
            id=None,
            name=name,
            qualified_name=qname,
            kind=kind,
            file_path=file_path,
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            docstring=self._get_docstring(body),
            language="python",
        )

    def _make_class_symbol(
        self, node: Node, module_path: str, file_path: str
    ) -> Optional[Symbol]:
        """Build a Symbol for a class_definition node."""
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return None
        name = name_node.text.decode("utf-8")
        body = node.child_by_field_name("body")
        return Symbol(
            id=None,
            name=name,
            qualified_name=f"{module_path}.{name}",
            kind="class",
            file_path=file_path,
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            docstring=self._get_docstring(body),
            language="python",
        )

    def _make_import_symbols(
        self, node: Node, module_path: str, file_path: str
    ) -> list[Symbol]:
        """Build a Symbol for each name introduced by an import statement."""
        names = self._parse_import_names(node.text.decode("utf-8").strip())
        line_start = node.start_point[0] + 1
        line_end = node.end_point[0] + 1
        return [
            Symbol(
                id=None,
                name=n,
                qualified_name=f"{module_path}.{n}",
                kind="import",
                file_path=file_path,
                line_start=line_start,
                line_end=line_end,
                docstring=None,
                language="python",
            )
            for n in names
        ]

    def _parse_import_names(self, import_text: str) -> list[str]:
        """Use Python's ast module to extract the local names from an import line."""
        try:
            tree = ast.parse(import_text)
            stmt = tree.body[0] if tree.body else None
            if isinstance(stmt, ast.Import):
                return [a.asname or a.name.split(".")[-1] for a in stmt.names]
            if isinstance(stmt, ast.ImportFrom):
                return [a.asname or a.name for a in stmt.names] if stmt.names else []
        except SyntaxError:
            pass
        return []

    def _unwrap_decorated(self, node: Node) -> Optional[Node]:
        """Return the function_definition or class_definition inside a decorated_definition."""
        for child in node.children:
            if child.type in ("function_definition", "class_definition"):
                return child
        return None

    def _get_docstring(self, body_node: Optional[Node]) -> Optional[str]:
        """Extract docstring text if the first statement of a body block is a string literal."""
        if body_node is None:
            return None
        for child in body_node.children:
            if child.type == "expression_statement":
                string_node = next(
                    (c for c in child.children if c.type == "string"), None
                )
                if string_node is None:
                    return None
                raw = string_node.text.decode("utf-8")
                try:
                    result = ast.literal_eval(raw)
                    return result if isinstance(result, str) else None
                except (ValueError, SyntaxError):
                    return raw.strip("'\"")
            if child.is_named:
                return None
        return None

    # ----------------------------------------------------------------- call sites

    def _extract_calls(
        self, root: Node, source_lines: list[str], file_path: str
    ) -> list[CallSite]:
        """Walk all function definitions and collect their direct call sites."""
        calls: list[CallSite] = []
        for func_node, caller_name in self._iter_functions(root):
            body = func_node.child_by_field_name("body")
            if body:
                calls.extend(self._calls_in_body(body, caller_name, source_lines, file_path))
        return calls

    def _iter_functions(self, node: Node) -> Iterator[tuple[Node, str]]:
        """Yield (function_definition_node, name) for every function in the tree."""
        for child in node.children:
            if child.type == "decorated_definition":
                inner = self._unwrap_decorated(child)
                if inner and inner.type == "function_definition":
                    name_node = inner.child_by_field_name("name")
                    if name_node:
                        yield inner, name_node.text.decode("utf-8")
                    yield from self._iter_functions(inner)
            elif child.type == "function_definition":
                name_node = child.child_by_field_name("name")
                if name_node:
                    yield child, name_node.text.decode("utf-8")
                yield from self._iter_functions(child)
            else:
                yield from self._iter_functions(child)

    def _calls_in_body(
        self,
        body_node: Node,
        caller_name: str,
        source_lines: list[str],
        file_path: str,
    ) -> list[CallSite]:
        """Collect call sites in a function body without descending into nested functions."""
        calls: list[CallSite] = []
        for node in self._body_nodes(body_node):
            if node.type != "call":
                continue
            callee = self._get_call_name(node)
            if callee is None:
                continue
            line_0 = node.start_point[0]
            calls.append(
                CallSite(
                    caller_name=caller_name,
                    call_site_file=file_path,
                    call_site_line=line_0 + 1,
                    context_snippet=self._get_context_snippet(source_lines, line_0),
                    callee_name=callee,
                )
            )
        return calls

    def _body_nodes(self, node: Node) -> Iterator[Node]:
        """Yield descendants depth-first, stopping at nested function boundaries."""
        yield node
        for child in node.children:
            if child.type not in ("function_definition", "decorated_definition"):
                yield from self._body_nodes(child)

    def _get_call_name(self, call_node: Node) -> Optional[str]:
        """Extract the callee name from a call node; handles attribute access."""
        func = call_node.child_by_field_name("function")
        if func is None:
            return None
        if func.type == "identifier":
            return func.text.decode("utf-8")
        if func.type == "attribute":
            attr = func.child_by_field_name("attribute")
            return attr.text.decode("utf-8") if attr else None
        return None

    def _get_context_snippet(self, source_lines: list[str], line_0: int) -> str:
        """Return the call line plus one surrounding line on each side."""
        start = max(0, line_0 - 1)
        end = min(len(source_lines), line_0 + 2)
        return "\n".join(source_lines[start:end])
