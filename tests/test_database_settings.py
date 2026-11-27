from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.engine import make_url

from repobrain.settings import Settings


def test_database_url_redacts_password(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    password = uuid4().hex
    monkeypatch.setenv(
        "REPOBRAIN_DATABASE_URL", f"postgresql+asyncpg://user:{password}@db/repobrain"
    )
    assert password not in repr(Settings())

    monkeypatch.setenv(
        "REPOBRAIN_DATABASE_URL", f"postgresql://user:{password}@db/repobrain"
    )
    with pytest.raises(ValidationError, match=r"postgresql\+asyncpg") as error:
        Settings()
    assert password not in str(error.value)


def test_local_database_url_preserves_raw_password(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("REPOBRAIN_DATABASE_URL", raising=False)
    password = f"{uuid4().hex}@:/%?# $[]"
    monkeypatch.setenv("REPOBRAIN_LOCAL_DB_PASSWORD", password)

    settings = Settings()

    assert settings.database_url is not None
    url = make_url(settings.database_url.get_secret_value())
    assert url.drivername == "postgresql+asyncpg"
    assert url.host == "db"
    assert url.username == url.database == "repobrain"
    assert url.password == password
    assert password not in repr(settings)


def test_database_connection_sources_cannot_conflict(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("REPOBRAIN_LOCAL_DB_PASSWORD", uuid4().hex)
    monkeypatch.setenv("REPOBRAIN_DATABASE_URL", "postgresql+asyncpg://example/db")

    with pytest.raises(
        ValidationError, match="set only one database connection source"
    ):
        Settings()
