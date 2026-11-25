from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

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
