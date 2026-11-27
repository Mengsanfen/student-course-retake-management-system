import sqlite3

import pytest
from sqlalchemy import func, select, update

from app import models as m
from app.database import make_engine, transaction
from app.manage import seed_demo, upgrade
from app.sync_database import backup_sqlite, sync_empty_database


def test_snapshot_import_preserves_values_and_ids(system, client, tmp_path):
    # Include a real anonymous CSRF session as well as seeded users, scores and UTC timestamps.
    assert client.get("/api/v1/auth/csrf").status_code == 200
    target = make_engine(f"sqlite:///{(tmp_path / 'destination.sqlite3').as_posix()}")
    try:
        upgrade(target)
        result = sync_empty_database(system[1], target, system[2].upload_dir)
        assert result["users"] == {"rows": 8, "allColumnsMatch": True}
        assert result["auth_sessions"] == {"rows": 1, "allColumnsMatch": True}
        assert all(item["allColumnsMatch"] for item in result.values())
        with transaction(target) as connection:
            assert (
                connection.scalar(select(m.enrollments.c.score).where(m.enrollments.c.id == 4))
                == 52
            )
    finally:
        target.dispose()


def test_snapshot_import_never_overwrites_nonempty_target(system, tmp_path):
    target = make_engine(f"sqlite:///{(tmp_path / 'existing.sqlite3').as_posix()}")
    try:
        upgrade(target)
        seed_demo(target, system[2])
        with transaction(target, write=True) as connection:
            connection.execute(
                update(m.users).where(m.users.c.id == 1).values(display_name="保留目标数据")
            )
        with pytest.raises(RuntimeError, match="not empty"):
            sync_empty_database(system[1], target, system[2].upload_dir)
        with transaction(target) as connection:
            assert (
                connection.scalar(select(m.users.c.display_name).where(m.users.c.id == 1))
                == "保留目标数据"
            )
            assert connection.scalar(select(func.count()).select_from(m.users)) == 8
    finally:
        target.dispose()


def test_sqlite_backup_includes_wal_and_refuses_to_replace_backup(tmp_path):
    source, destination = tmp_path / "live.sqlite3", tmp_path / "backup.sqlite3"
    with sqlite3.connect(source) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("CREATE TABLE example(id INTEGER PRIMARY KEY, label TEXT)")
        connection.execute("INSERT INTO example VALUES(1,'最新记录')")
        connection.commit()
        backup_sqlite(source, destination)
    with sqlite3.connect(destination) as backup:
        assert backup.execute("SELECT label FROM example WHERE id=1").fetchone()[0] == "最新记录"
    with pytest.raises(RuntimeError, match="already exists"):
        backup_sqlite(source, destination)


def test_snapshot_import_requires_matching_migration_versions(system, tmp_path):
    from sqlalchemy import text

    target = make_engine(f"sqlite:///{(tmp_path / 'old-revision.sqlite3').as_posix()}")
    try:
        upgrade(target)
        with target.begin() as connection:
            connection.execute(text("UPDATE alembic_version SET version_num='0001'"))
        with pytest.raises(RuntimeError, match="Schema revisions differ"):
            sync_empty_database(system[1], target, system[2].upload_dir)
        with target.connect() as connection:
            assert connection.scalar(select(func.count()).select_from(m.users)) == 0
    finally:
        target.dispose()
