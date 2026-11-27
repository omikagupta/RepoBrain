import re
from bisect import bisect_right
from collections import defaultdict
from collections.abc import Iterable, Iterator
from hashlib import sha256
from itertools import accumulate
from uuid import UUID, uuid5

from repobrain.database.models import SourceChunk
from repobrain.graph.analyzer import GraphError, InputFile, Node, stable_key

VERSION = "python-lines-v1"
MAX_LINES = 80
MAX_BYTES = 8192
MAX_CHUNKS = 10_000
MAX_TOKEN_BYTES = 128
WORD = re.compile(r"\w+(?:\.[^\W\d]\w*)*")


def search_terms(text: str) -> Iterator[str]:
    for match in WORD.finditer(text):
        term = match[0].casefold()
        if (
            any(char.isalnum() for char in term)
            and len(term.encode()) <= MAX_TOKEN_BYTES
        ):
            yield term


def lexeme(term: str) -> str:
    # A parser-safe ASCII word preserves dots, underscores and Unicode identity.
    return "k" + term.encode().hex()


def index_text(content: str, names: Iterable[str]) -> str:
    tokens: list[str] = []
    for term in search_terms(content):
        forms = dict.fromkeys([term, *re.split(r"[._]+", term)])
        tokens.extend(lexeme(form) for form in forms if form)
    for name in names:
        segments = name.split(".")
        tokens.extend(
            lexeme(term)
            for offset in range(len(segments))
            for term in search_terms(".".join(segments[offset:]))
        )
    document = " ".join(tokens)
    if len(document) > 65536:
        raise GraphError("Lexical token document exceeds the byte limit")
    return document


def exact_lines(content: str) -> list[str]:
    return [
        match[0]
        for match in re.finditer(r"[^\r\n]*(?:\r\n|\r|\n|$)", content)
        if match[0]
    ]


def chunk_file(
    snapshot_id: UUID, source: InputFile, nodes: list[Node]
) -> Iterator[SourceChunk]:
    lines = exact_lines(source.content)
    offsets = list(accumulate((len(line.encode()) for line in lines), initial=0))
    if any(
        end - start > MAX_BYTES
        for start, end in zip(offsets, offsets[1:], strict=False)
    ):
        raise GraphError("A source line exceeds the lexical chunk byte limit")
    boundaries = {0, len(lines)}
    names: dict[int, list[str]] = defaultdict(list)
    protected_end = 0
    spans = sorted(
        (node.start_line, -node.end_line, node.qualified_name, node.kind)
        for node in nodes
        if node.kind != "module"
        and node.start_line is not None
        and node.end_line is not None
    )
    for first, negative_last, name, kind in spans:
        last = -negative_last
        if not 1 <= first <= last <= len(lines):
            raise GraphError("Invalid AST span for lexical chunking")
        names[first].append(name)
        if first <= protected_end:
            continue
        boundaries.update((first - 1, last))
        if (
            kind in {"function", "method"}
            and last - first < MAX_LINES
            and offsets[last] - offsets[first - 1] <= MAX_BYTES
        ):
            protected_end = last

    source_digest = sha256(source.content.encode()).hexdigest()
    ordered = sorted(boundaries)
    for left, right in zip(ordered, ordered[1:], strict=False):
        start = left
        while start < right:
            end = (
                bisect_right(
                    offsets,
                    offsets[start] + MAX_BYTES,
                    start + 1,
                    min(right, start + MAX_LINES) + 1,
                )
                - 1
            )
            content = "".join(lines[start:end])
            key = stable_key(str(snapshot_id), source.path, start + 1, end, VERSION)
            yield SourceChunk(
                id=uuid5(snapshot_id, key),
                snapshot_id=snapshot_id,
                chunking_version=VERSION,
                source_file_id=source.id,
                stable_key=key,
                start_line=start + 1,
                end_line=end,
                content=content,
                source_sha256=source_digest,
                content_sha256=sha256(content.encode()).hexdigest(),
                token_text=index_text(
                    content,
                    (
                        name
                        for line in range(start + 1, end + 1)
                        for name in names.get(line, [])
                    ),
                ),
            )
            start = end
