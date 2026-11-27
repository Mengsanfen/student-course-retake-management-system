import os
from dataclasses import replace

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.engine import make_url

from app import models as m
from app.config import BACKEND_ROOT, Settings
from app.database import make_engine, transaction
from app.main import create_app
from app.manage import seed_demo, upgrade


def pytest_addoption(parser):
    parser.addoption("--database", choices=("sqlite", "mysql"), default="sqlite")


@pytest.fixture
def system(tmp_path, request):
    database_url = f"sqlite:///{(tmp_path / 'test.sqlite3').as_posix()}"
    if request.config.getoption("--database") == "mysql":
        load_dotenv(BACKEND_ROOT / ".env.mysql-test", override=False)
        database_url = os.environ.get("MYSQL_TEST_DATABASE_URL", "")
        parsed = make_url(database_url)
        if (
            parsed.drivername != "mysql+pymysql"
            or parsed.database != "retake_management_test"
            or parsed.host not in {"127.0.0.1", "localhost"}
        ):
            raise RuntimeError("MySQL tests may only use the local retake_management_test schema.")
    settings = Settings(
        database_url=database_url,
        upload_dir=tmp_path / "uploads",
        demo_mode=True,
    )
    engine = make_engine(settings.database_url)
    upgrade(engine)
    if engine.dialect.name == "mysql":
        with transaction(engine, write=True) as connection:
            for table in reversed(m.metadata.sorted_tables):
                connection.execute(delete(table))
    seed_demo(engine, settings)
    app = create_app(settings, engine=engine)
    try:
        yield app, engine, settings
    finally:
        if engine.dialect.name == "mysql":
            with transaction(engine, write=True) as connection:
                for table in reversed(m.metadata.sorted_tables):
                    connection.execute(delete(table))
        engine.dispose()


@pytest.fixture
def client(system):
    with TestClient(system[0]) as client:
        yield client


@pytest.fixture
def changed_settings(system):
    return lambda **kwargs: replace(system[2], **kwargs)
