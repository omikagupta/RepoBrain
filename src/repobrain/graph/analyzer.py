import ast
import json
import keyword
import re
from collections import defaultdict
from hashlib import sha256
from pathlib import PurePosixPath
from uuid import UUID, uuid5

from pydantic import BaseModel, Field

MAX_FILES = 1000
MAX_FILE_BYTES = 256 * 1024
MAX_TOTAL_BYTES = 4 * 1024**2
MAX_AST_NODES = 300_000
MAX_GRAPH_NODES = 20_000
MAX_GRAPH_EDGES = 40_000
MAX_IMPORTS = 20_000
MAX_DIAGNOSTICS = 4_000
MAX_LABEL_BYTES = 1024


class GraphError(Exception):
    """Safe analysis failure."""


class InputFile(BaseModel):
    id: UUID
    path: str
    content: str


class Node(BaseModel):
    id: UUID
    source_file_id: UUID
    stable_key: str
    kind: str
    qualified_name: str
    start_line: int | None
    end_line: int | None
    is_async: bool = False


class Edge(BaseModel):
    id: UUID
    source_id: UUID
    target_id: UUID
    stable_key: str
    relationship: str
    line: int | None
    column: int | None
    provenance: str


class Diagnostic(BaseModel):
    path: str
    line: int | None
    code: str
    reference: str | None = None


class Graph(BaseModel):
    analyzed_files: int = 0
    nodes: list[Node] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)
    diagnostics: list[Diagnostic] = Field(default_factory=list)


def stable_key(*parts: str | int | None) -> str:
    return sha256(json.dumps(parts, separators=(",", ":")).encode()).hexdigest()


def source_lines(content: str) -> list[str]:
    lines = re.split(r"\r\n|\r|\n", content)
    if not lines[-1]:
        lines.pop()
    return lines


def module_name(path: PurePosixPath, packages: set[PurePosixPath]) -> str | None:
    parts = path.parts
    name = parts[:-1] if path.name == "__init__.py" else (*parts[:-1], path.stem)
    if not name or any(
        not part.isidentifier() or keyword.iskeyword(part) for part in name
    ):
        return None
    if any(PurePosixPath(*parts[:end]) not in packages for end in range(1, len(parts))):
        return None
    return ".".join(name)


def decorator_start(
    definition: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef, lines: list[str]
) -> int:
    if not definition.decorator_list:
        return definition.lineno
    index = definition.decorator_list[0].lineno - 1
    # A parenthesized decorator can start before the expression's AST line.
    while index > 0:
        line = lines[index]
        if line[definition.col_offset :].startswith("@"):
            break
        index -= 1
    return index + 1


def plain_functions(tree: ast.Module) -> set[str]:
    names: list[str] = []
    for index, stmt in enumerate(tree.body):
        if (
            index == 0
            and isinstance(stmt, ast.Expr)
            and isinstance(stmt.value, ast.Constant)
        ):
            if isinstance(stmt.value.value, str):
                continue
        if not isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return set()
        args = stmt.args
        parameters = [*args.posonlyargs, *args.args, *args.kwonlyargs]
        parameters.extend(
            param for param in (args.vararg, args.kwarg) if param is not None
        )
        if (
            stmt.decorator_list
            or stmt.type_params
            or stmt.returns
            or args.defaults
            or any(default is not None for default in args.kw_defaults)
            or any(param.annotation is not None for param in parameters)
        ):
            return set()
        names.append(stmt.name)
    unique = set(names)
    if len(unique) != len(names):
        return set()
    return unique


class Analyzer:
    def __init__(self, snapshot_id: UUID, files: list[InputFile]) -> None:
        self.snapshot_id = snapshot_id
        self.files = sorted(files, key=lambda file: file.path)
        self.graph = Graph()
        self.modules: dict[str, list[Node]] = defaultdict(list)
        self.package_ids: set[UUID] = set()
        self.symbols: dict[tuple[UUID, str], Node] = {}
        self.imports: list[
            tuple[InputFile, Node, str | None, ast.Import | ast.ImportFrom]
        ] = []
        self.ast_nodes = 0

    def node(
        self,
        file: InputFile,
        kind: str,
        qualified: str,
        start: int | None,
        end: int | None,
        column: int | None = None,
        *,
        is_async: bool = False,
    ) -> Node:
        if len(self.graph.nodes) >= MAX_GRAPH_NODES:
            raise GraphError("Graph node limit exceeded")
        if len(qualified.encode()) > MAX_LABEL_BYTES:
            raise GraphError("Graph symbol name exceeds the byte limit")
        key = stable_key(file.path, kind, qualified, start, column)
        node = Node(
            id=uuid5(self.snapshot_id, key),
            source_file_id=file.id,
            stable_key=key,
            kind=kind,
            qualified_name=qualified,
            start_line=start,
            end_line=end,
            is_async=is_async,
        )
        self.graph.nodes.append(node)
        return node

    def edge(
        self,
        source: Node,
        target: Node,
        relationship: str,
        provenance: str,
        line: int | None,
        column: int | None,
    ) -> None:
        if len(self.graph.edges) >= MAX_GRAPH_EDGES:
            raise GraphError("Graph edge limit exceeded")
        if len(provenance.encode()) > MAX_LABEL_BYTES:
            raise GraphError("Graph provenance exceeds the byte limit")
        key = stable_key(
            source.stable_key, target.stable_key, relationship, line, column, provenance
        )
        self.graph.edges.append(
            Edge(
                id=uuid5(self.snapshot_id, key),
                source_id=source.id,
                target_id=target.id,
                stable_key=key,
                relationship=relationship,
                line=line,
                column=column,
                provenance=provenance,
            )
        )

    def diagnostic(
        self, file: InputFile, line: int | None, code: str, ref: str | None
    ) -> None:
        if len(self.graph.diagnostics) >= MAX_DIAGNOSTICS:
            raise GraphError("Diagnostic limit exceeded")
        if ref is not None and len(ref.encode()) > MAX_LABEL_BYTES:
            raise GraphError("Import reference exceeds the byte limit")
        self.graph.diagnostics.append(
            Diagnostic(path=file.path, line=line, code=code, reference=ref)
        )

    def analyze_file(self, file: InputFile, name: str | None, package: bool) -> None:
        lines = source_lines(file.content)
        module = self.node(
            file,
            "module",
            name or file.path,
            1 if lines else None,
            len(lines) if lines else None,
        )
        if name is not None:
            self.modules[name].append(module)
            if package:
                self.package_ids.add(module.id)
        try:
            tree = ast.parse(file.content)
        except SyntaxError as exc:
            self.diagnostic(file, exc.lineno, "syntax_error", None)
            return
        self.graph.analyzed_files += 1
        safe_exports = plain_functions(tree)
        stack: list[tuple[ast.AST, Node]] = [(tree, module)]
        while stack:
            item, parent = stack.pop()
            self.ast_nodes += 1
            if self.ast_nodes > MAX_AST_NODES:
                raise GraphError("AST node limit exceeded")
            if isinstance(item, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                enclosing = parent
                kind = (
                    "class"
                    if isinstance(item, ast.ClassDef)
                    else ("method" if enclosing.kind == "class" else "function")
                )
                parent = self.node(
                    file,
                    kind,
                    f"{enclosing.qualified_name}.{item.name}",
                    decorator_start(item, lines),
                    item.end_lineno,
                    item.col_offset,
                    is_async=isinstance(item, ast.AsyncFunctionDef),
                )
                self.edge(
                    enclosing,
                    parent,
                    "CONTAINS",
                    "lexical",
                    item.lineno,
                    item.col_offset,
                )
                if enclosing is module and item.name in safe_exports:
                    self.symbols[(module.id, item.name)] = parent
            elif isinstance(item, (ast.Import, ast.ImportFrom)):
                if len(self.imports) >= MAX_IMPORTS:
                    raise GraphError("Import statement limit exceeded")
                self.imports.append((file, module, name, item))
            stack.extend(
                (child, parent) for child in reversed(list(ast.iter_child_nodes(item)))
            )

    def resolve(self, name: str) -> tuple[Node | None, str]:
        parts = name.split(".")
        for end in range(1, len(parts) + 1):
            matches = self.modules.get(".".join(parts[:end]), [])
            if len(matches) > 1:
                return None, "ambiguous_import"
            if not matches or (
                end < len(parts) and matches[0].id not in self.package_ids
            ):
                return None, "unresolved_import"
        return matches[0], ""

    def add_imports(self) -> None:
        for file, source, name, stmt in self.imports:
            if isinstance(stmt, ast.ImportFrom) and stmt.level:
                parts = name.split(".") if name else []
                if source.id not in self.package_ids:
                    parts = parts[:-1]
                if (
                    stmt.level > len(parts)
                    or not name
                    or self.resolve(name)[0] != source
                ):
                    self.diagnostic(
                        file, stmt.lineno, "unresolved_relative_import", stmt.module
                    )
                    continue
                prefix = parts[: len(parts) - stmt.level + 1]
                base = ".".join([*prefix, stmt.module] if stmt.module else prefix)
            else:
                base = stmt.module or "" if isinstance(stmt, ast.ImportFrom) else ""
            for alias in stmt.names:
                target_name = base if isinstance(stmt, ast.ImportFrom) else alias.name
                spelling = alias.name + (f" as {alias.asname}" if alias.asname else "")
                if isinstance(stmt, ast.ImportFrom):
                    spelling = (
                        f"from {'.' * stmt.level}{stmt.module or ''} import {spelling}"
                    )
                target, reason = self.resolve(target_name)
                if target is None:
                    self.diagnostic(file, stmt.lineno, reason, spelling)
                    continue
                self.edge(
                    source, target, "IMPORTS", spelling, stmt.lineno, alias.col_offset
                )
                if isinstance(stmt, ast.ImportFrom) and alias.name != "*":
                    symbol = self.symbols.get((target.id, alias.name))
                    if (
                        symbol is not None
                        and f"{target_name}.{alias.name}" not in self.modules
                    ):
                        self.edge(
                            source,
                            symbol,
                            "IMPORTS_SYMBOL",
                            spelling,
                            stmt.lineno,
                            alias.col_offset,
                        )
                    else:
                        self.diagnostic(
                            file, stmt.lineno, "unresolved_symbol", spelling
                        )

    def build(self) -> Graph:
        packages = {
            PurePosixPath(file.path).parent
            for file in self.files
            if PurePosixPath(file.path).name == "__init__.py"
        }
        src_root = PurePosixPath("src")
        src_packages = {
            package.relative_to(src_root)
            for package in packages
            if package.is_relative_to(src_root)
        }
        for file in self.files:
            path = PurePosixPath(file.path)
            if (
                len(path.parts) > 1
                and path.parts[0] == "src"
                and src_root not in packages
            ):
                path = PurePosixPath(*path.parts[1:])
                name = module_name(path, src_packages)
            else:
                name = module_name(path, packages)
            self.analyze_file(file, name, path.name == "__init__.py")
        self.add_imports()
        self.graph.nodes.sort(key=lambda node: node.stable_key)
        self.graph.edges.sort(key=lambda edge: edge.stable_key)
        return self.graph
