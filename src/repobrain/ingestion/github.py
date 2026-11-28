import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha1, sha256
from time import time
from urllib.parse import quote

import httpx

from repobrain.settings import Settings

OWNER = r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*"
REPOSITORY_PATTERN = rf"^{OWNER}/[a-zA-Z0-9_.-]{{1,100}}$"
SHA_PATTERN = r"[a-f0-9]{40}"
API = "https://api.github.com"
EXCLUDED = {
    "vendor",
    "vendors",
    "node_modules",
    "dist",
    "build",
    "generated",
    ".venv",
    "venv",
}
CONTROL_BYTES = re.compile(rb"[\x00-\x08\x0b\x0e-\x1f\x7f]")
ENTRY_MODES = {
    "tree": ("040000",),
    "commit": ("160000",),
    "blob": ("120000", "100644", "100755"),
}


class IngestionError(Exception):
    def __init__(
        self, status: int, code: str, message: str, retry_after: int | None = None
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.retry_after = retry_after


def github_retry_after(headers: httpx.Headers) -> int:
    seconds = headers.get("retry-after", "")
    if re.fullmatch(r"[0-9]{1,8}", seconds):
        return max(1, min(3600, int(seconds)))
    reset = headers.get("x-ratelimit-reset", "")
    if re.fullmatch(r"[0-9]{1,12}", reset):
        return max(1, min(3600, int(reset) - int(time())))
    return 60


def upstream_error() -> IngestionError:
    return IngestionError(
        502, "github_unavailable", "GitHub returned an unexpected response"
    )


def limit_error() -> IngestionError:
    return IngestionError(
        413, "ingestion_limit", "Repository exceeds an ingestion limit"
    )


def validate_ref(value: str) -> str:
    parts = value.split("/")
    if (
        not re.fullmatch(r"[A-Za-z0-9._/-]{1,200}", value)
        or ".." in value
        or value.endswith(".")
        or any(
            not part or part.startswith(".") or part.endswith(".lock") for part in parts
        )
    ):
        raise ValueError("Invalid GitHub ref")
    return value


def canonical_repository(value: str) -> str:
    if (
        not re.fullmatch(REPOSITORY_PATTERN, value)
        or len(value.split("/")[0]) > 39
        or value.split("/")[1] in {".", ".."}
    ):
        raise ValueError("Expected a GitHub owner/name")
    return value.lower()


def object_sha(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(SHA_PATTERN, value):
        raise upstream_error()
    return value


def json_object(value: object) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise upstream_error()
    return value


def safe_path(value: object) -> str:
    if not isinstance(value, str):
        raise upstream_error()
    try:
        size = len(value.encode("utf-8"))
    except UnicodeError:
        raise upstream_error() from None
    if (
        size > 1024
        or "\\" in value
        or re.match(r"^[A-Za-z]:", value)
        or any(part in {"", ".", ".."} for part in value.split("/"))
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise IngestionError(422, "unsafe_path", "GitHub tree contains an unsafe path")
    return value


@dataclass(frozen=True)
class Commit:
    repository: str
    sha: str
    tree_sha: str


@dataclass(frozen=True)
class PythonFile:
    path: str
    content: str
    content_sha256: str
    line_count: int


class GitHub:
    def __init__(self, client: httpx.AsyncClient, settings: Settings) -> None:
        self.client = client
        self.settings = settings
        self.remaining = settings.ingestion_max_network_bytes

    async def read(
        self, path: str, accept: str, missing: IngestionError, cap: int
    ) -> bytes:
        try:
            async with self.client.stream(
                "GET",
                API + path,
                headers={
                    "Accept": accept,
                    "Accept-Encoding": "identity",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                follow_redirects=False,
            ) as response:
                if response.status_code in {404, 409, 422}:
                    raise missing
                if response.status_code == 429 or (
                    response.status_code == 403
                    and (
                        response.headers.get("x-ratelimit-remaining") == "0"
                        or "retry-after" in response.headers
                    )
                ):
                    raise IngestionError(
                        503,
                        "github_rate_limited",
                        "GitHub rate limit reached",
                        github_retry_after(response.headers),
                    )
                if response.status_code == 403:
                    raise missing
                if response.status_code != 200:
                    raise upstream_error()
                if (
                    response.headers.get("content-encoding", "identity").lower()
                    != "identity"
                ):
                    raise upstream_error()
                length = response.headers.get("content-length")
                if length is not None and length.isdecimal() and len(length) <= 20:
                    if int(length) > min(cap, self.remaining):
                        raise limit_error()
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    self.remaining -= len(chunk)
                    if self.remaining < 0 or len(body) + len(chunk) > cap:
                        raise limit_error()
                    body.extend(chunk)
                return bytes(body)
        except httpx.TimeoutException:
            raise IngestionError(
                504, "github_timeout", "GitHub request timed out"
            ) from None
        except httpx.HTTPError:
            raise upstream_error() from None

    async def json(self, path: str, missing: IngestionError) -> Mapping[str, object]:
        raw = await self.read(
            path, "application/vnd.github+json", missing, self.remaining
        )
        try:
            return json_object(json.loads(raw))
        except (ValueError, UnicodeError, RecursionError):
            raise upstream_error() from None

    async def resolve(self, repository: str, ref: str | None) -> Commit:
        missing = IngestionError(
            404, "repository_not_found", "Public repository not found"
        )
        metadata = await self.json(f"/repos/{repository}", missing)
        if (
            metadata.get("private") is not False
            or metadata.get("visibility") != "public"
        ):
            raise missing
        name = metadata.get("full_name")
        selected_ref = ref if ref is not None else metadata.get("default_branch")
        if not isinstance(name, str) or not isinstance(selected_ref, str):
            raise upstream_error()
        try:
            name = canonical_repository(name)
            selected_ref = validate_ref(selected_ref)
        except ValueError:
            raise upstream_error() from None
        unresolved = IngestionError(
            422, "ref_not_found", "GitHub ref could not be resolved"
        )
        if ref is None:
            selected_ref = f"refs/heads/{selected_ref}"
        data = await self.json(
            f"/repos/{name}/commits/{quote(selected_ref, safe='')}", unresolved
        )
        sha = object_sha(data.get("sha"))
        if (
            re.fullmatch(r"[A-Fa-f0-9]{40}", selected_ref)
            and sha != selected_ref.lower()
        ):
            raise unresolved
        tree = json_object(json_object(data.get("commit")).get("tree"))
        return Commit(name, sha, object_sha(tree.get("sha")))

    async def collect(self, commit: Commit) -> list[PythonFile]:
        path = f"/repos/{commit.repository}/git"
        tree = await self.json(
            f"{path}/trees/{commit.tree_sha}?recursive=1", upstream_error()
        )
        if tree.get("truncated") is True:
            raise limit_error()
        entries = tree.get("tree")
        if (
            tree.get("truncated") is not False
            or tree.get("sha") != commit.tree_sha
            or not isinstance(entries, list)
        ):
            raise upstream_error()
        files: list[PythonFile] = []
        seen: set[str] = set()
        remaining = self.settings.ingestion_max_total_bytes
        candidates = 0
        for raw in entries:
            entry = json_object(raw)
            relative = safe_path(entry.get("path"))
            if relative in seen:
                raise upstream_error()
            seen.add(relative)
            kind = entry.get("type")
            mode = entry.get("mode")
            if not isinstance(kind, str) or mode not in ENTRY_MODES.get(kind, ()):
                raise upstream_error()
            blob = object_sha(entry.get("sha"))
            if kind != "blob":
                continue
            size = entry.get("size")
            if type(size) is not int or size < 0:
                raise upstream_error()
            if (
                mode == "120000"
                or not relative.endswith(".py")
                or EXCLUDED.intersection(
                    part.lower() for part in relative.split("/")[:-1]
                )
            ):
                continue
            if size > self.settings.ingestion_max_file_bytes:
                continue
            candidates += 1
            if candidates > self.settings.ingestion_max_files:
                raise limit_error()
            data = await self.read(
                f"{path}/blobs/{blob}",
                "application/vnd.github.raw+json",
                upstream_error(),
                min(size, remaining),
            )
            checksum = sha1(f"blob {size}\0".encode(), usedforsecurity=False)
            checksum.update(data)
            if len(data) != size or checksum.hexdigest() != blob:
                raise upstream_error()
            if CONTROL_BYTES.search(data):
                continue
            try:
                content = data.decode("utf-8")
            except UnicodeDecodeError:
                continue
            lines = content.count("\n") + content.count("\r") - content.count("\r\n")
            lines += bool(content and not content.endswith(("\r", "\n")))
            files.append(PythonFile(relative, content, sha256(data).hexdigest(), lines))
            remaining -= size
        return files
