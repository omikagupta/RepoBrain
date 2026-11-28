"""Hosted identity and workspace authorization."""

import asyncio
from time import monotonic
from typing import Annotated, Any
from uuid import UUID

import httpx
import jwt
from fastapi import APIRouter, Depends, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from repobrain.database.models import (
    Repository,
    RepositorySnapshot,
    SaaSUser,
    Workspace,
    WorkspaceSnapshot,
)
from repobrain.graph.exploration import ExplorationError

bearer = HTTPBearer(auto_error=False)
ALGORITHMS = ("ES256", "RS256")


def unauthorized() -> ExplorationError:
    return ExplorationError(401, "authentication_required", "Sign in to continue")


def hidden() -> ExplorationError:
    return ExplorationError(404, "workspace_resource_not_found", "Resource not found")


class Tokens:
    def __init__(
        self, issuer: str, audience: str, transport: httpx.AsyncBaseTransport | None
    ) -> None:
        self.issuer = issuer
        self.audience = audience
        self.transport = transport
        self.keys: dict[str, jwt.PyJWK] = {}
        self.expires = 0.0
        self.next_refresh = 0.0
        self.lock = asyncio.Lock()

    async def key(self, kid: str) -> jwt.PyJWK:
        async with self.lock:
            now = monotonic()
            if now < self.expires and kid in self.keys:
                return self.keys[kid]
            if now >= self.next_refresh:
                self.next_refresh = now + 5
                try:
                    async with (
                        asyncio.timeout(5),
                        httpx.AsyncClient(
                            transport=self.transport,
                            trust_env=False,
                            timeout=4,
                            follow_redirects=False,
                        ) as client,
                        client.stream(
                            "GET", self.issuer + "/.well-known/jwks.json"
                        ) as response,
                    ):
                        response.raise_for_status()
                        body = bytearray()
                        async for chunk in response.aiter_bytes(chunk_size=4096):
                            if len(body) + len(chunk) > 32768:
                                raise ValueError("JWKS size limit")
                            body.extend(chunk)
                    keys = jwt.PyJWKSet.from_json(body.decode()).keys
                    replacement = {
                        key.key_id: key
                        for key in keys
                        if key.key_id
                        and key.public_key_use in (None, "sig")
                        and key.algorithm_name in ALGORITHMS
                    }
                    if not replacement or len(replacement) > 20:
                        raise ValueError("Invalid JWKS")
                    self.keys = replacement
                    self.expires = monotonic() + 60
                except (httpx.HTTPError, TimeoutError, ValueError, jwt.PyJWTError):
                    raise ExplorationError(
                        503,
                        "identity_unavailable",
                        "Sign-in verification is unavailable",
                    ) from None
            key = self.keys.get(kid)
            if key is None or monotonic() >= self.expires:
                raise unauthorized()
            return key

    async def subject(self, token: str) -> UUID:
        try:
            if len(token) > 8192:
                raise ValueError("Token size")
            header = jwt.get_unverified_header(token)
            kid = header.get("kid")
            algorithm = header.get("alg")
            if not isinstance(kid, str) or not 1 <= len(kid) <= 128:
                raise ValueError("Key identifier")
            if algorithm not in ALGORITHMS:
                raise ValueError("Algorithm")
            key = await self.key(kid)
            if algorithm != key.algorithm_name:
                raise ValueError("Key algorithm")
            claims = jwt.decode(
                token,
                key,
                algorithms=[key.algorithm_name],
                issuer=self.issuer,
                audience=self.audience,
                options={"require": ["iss", "aud", "exp", "sub"]},
            )
            if type(claims["exp"]) is not int or claims.get("role") != "authenticated":
                raise ValueError("Unexpected claims")
            subject = UUID(claims["sub"])
            if not subject.int or claims.get("is_anonymous") is True:
                raise ValueError("Unexpected subject")
            return subject
        except (ValueError, TypeError, jwt.PyJWTError, RecursionError, OverflowError):
            raise unauthorized() from None


def sessions_for(request: Request) -> async_sessionmaker[AsyncSession]:
    sessions: async_sessionmaker[AsyncSession] | None = (
        request.app.state.database_sessions
    )
    if sessions is None:
        raise ExplorationError(503, "database_unavailable", "Database is unavailable")
    return sessions


async def authenticated(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(bearer)],
) -> UUID:
    tokens: Tokens | None = request.app.state.tokens
    if tokens is None:
        raise hidden()
    if credentials is None:
        raise unauthorized()
    return await tokens.subject(credentials.credentials)


Subject = Annotated[UUID, Depends(authenticated)]


async def protect(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(bearer)],
) -> None:
    if request.app.state.tokens is None:
        return
    subject = await authenticated(request, credentials)
    raw: Any = request.path_params.get("snapshot_id")
    try:
        snapshot_id = UUID(raw) if raw is not None else None
    except ValueError:
        raise hidden() from None
    async with sessions_for(request)() as session:
        access = (
            select(Workspace.id, Workspace.revision)
            .join(SaaSUser)
            .where(Workspace.owner_id == subject, SaaSUser.deleted_at.is_(None))
        )
        if snapshot_id is not None:
            access = access.join(WorkspaceSnapshot).where(
                WorkspaceSnapshot.snapshot_id == snapshot_id
            )
        workspace = (await session.execute(access)).one_or_none()
    if workspace is None:
        raise hidden()
    request.state.workspace = (workspace.id, workspace.revision)


router = APIRouter(prefix="/api/v1/workspace", tags=["Workspace"])


class WorkspaceRepo(BaseModel):
    id: UUID
    repository: str
    commit_sha: str
    snapshot_id: UUID


class WorkspaceView(BaseModel):
    id: UUID
    snapshots: list[WorkspaceRepo]


@router.post("")
async def provision(request: Request, subject: Subject) -> WorkspaceView:
    async with sessions_for(request).begin() as session:
        await session.execute(
            insert(SaaSUser).values(id=subject).on_conflict_do_nothing()
        )
        user = await session.get_one(SaaSUser, subject, with_for_update=True)
        if user.deleted_at is not None:
            raise hidden()
        workspace = await session.scalar(
            select(Workspace.id).where(Workspace.owner_id == subject)
        )
        if workspace is None:
            row = Workspace(owner_id=subject)
            session.add(row)
            await session.flush()
            workspace = row.id
        return WorkspaceView(id=workspace, snapshots=[])


@router.get("")
async def workspace_status(request: Request, subject: Subject) -> WorkspaceView:
    async with sessions_for(request)() as session:
        workspace = await session.scalar(
            select(Workspace.id).where(Workspace.owner_id == subject)
        )
        if workspace is None:
            raise hidden()
        rows = await session.execute(
            select(Repository, RepositorySnapshot)
            .join(RepositorySnapshot, RepositorySnapshot.repository_id == Repository.id)
            .join(
                WorkspaceSnapshot,
                WorkspaceSnapshot.snapshot_id == RepositorySnapshot.id,
            )
            .where(WorkspaceSnapshot.workspace_id == workspace)
            .order_by(Repository.owner, Repository.name, RepositorySnapshot.id)
            .limit(100)
        )
        return WorkspaceView(
            id=workspace,
            snapshots=[
                WorkspaceRepo(
                    id=repo.id,
                    repository=f"{repo.owner}/{repo.name}",
                    commit_sha=snap.commit_sha,
                    snapshot_id=snap.id,
                )
                for repo, snap in rows
            ],
        )


@router.delete("/repositories/{repository_id}", status_code=204)
async def remove_repository(
    request: Request, subject: Subject, repository_id: UUID
) -> None:
    async with sessions_for(request).begin() as session:
        workspace = await session.scalar(
            select(Workspace).where(Workspace.owner_id == subject).with_for_update()
        )
        if workspace is None:
            raise hidden()
        removed = await session.scalar(
            delete(WorkspaceSnapshot)
            .where(
                WorkspaceSnapshot.workspace_id == workspace.id,
                WorkspaceSnapshot.snapshot_id.in_(
                    select(RepositorySnapshot.id).where(
                        RepositorySnapshot.repository_id == repository_id
                    )
                ),
            )
            .returning(WorkspaceSnapshot.snapshot_id)
        )
        if removed is None:
            raise hidden()
        workspace.revision += 1


@router.delete("", status_code=204)
async def remove_workspace(request: Request, subject: Subject) -> None:
    await remove(request, subject, account=False)


@router.delete("/account", status_code=204)
async def remove_account(request: Request, subject: Subject) -> None:
    await remove(request, subject, account=True)


async def remove(request: Request, subject: UUID, *, account: bool) -> None:
    from datetime import UTC, datetime

    async with sessions_for(request).begin() as session:
        if account:
            await session.execute(
                insert(SaaSUser).values(id=subject).on_conflict_do_nothing()
            )
        user = await session.get(SaaSUser, subject, with_for_update=True)
        if user is None:
            raise hidden()
        await session.execute(delete(Workspace).where(Workspace.owner_id == subject))
        if account:
            user.deleted_at = datetime.now(UTC)
