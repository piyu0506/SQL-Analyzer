import pytest

from analyzer import workspace_db


@pytest.fixture(autouse=True)
def isolated_playground_database(tmp_path, monkeypatch):
    monkeypatch.setattr(
        workspace_db,
        "WORKSPACE_DB_PATH",
        tmp_path / "playground.sqlite3",
    )
    workspace_db._initialise_workspace()
