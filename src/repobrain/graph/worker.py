import sys
from uuid import UUID

from pydantic import TypeAdapter

from repobrain.graph.analyzer import Analyzer, GraphError, InputFile

files_adapter = TypeAdapter(list[InputFile])


def main() -> int:
    try:
        files = files_adapter.validate_json(sys.stdin.buffer.read())
        graph = Analyzer(UUID(sys.argv[1]), files).build()
        sys.stdout.buffer.write(graph.model_dump_json().encode("utf-8"))
    except GraphError as exc:
        sys.stdout.buffer.write(str(exc).encode("ascii"))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
