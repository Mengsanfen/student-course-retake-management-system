"""One-time, insert-only import from a consistent SQLite backup to a migrated empty DB."""

import argparse
import hashlib
import json
import sqlite3
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select

from app import models as m
from app.config import BACKEND_ROOT, Settings
from app.database import make_engine, transaction
from app.manage import upgrade


def backup_sqlite(source: Path, destination: Path):
    if destination.exists():
        raise RuntimeError("Backup already exists; refusing to replace it.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True) as original:
        with sqlite3.connect(destination) as backup:
            original.backup(backup)


def digest(rows):
    def normalize(value):
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, Decimal):
            return str(value)
        raise TypeError(type(value).__name__)

    return hashlib.sha256(
        json.dumps(rows, default=normalize, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def sync_empty_database(source, target, upload_dir: Path):
    if source.url == target.url:
        raise RuntimeError("Source and target must be different databases.")
    tables = list(m.metadata.sorted_tables)
    # Explicit BEGIN is required for a consistent read snapshot with SQLite's legacy driver.
    with source.connect() as source_connection:
        if source.dialect.name == "sqlite":
            source_connection.exec_driver_sql("BEGIN")
        snapshot = {
            table.name: [
                dict(row)
                for row in source_connection.execute(
                    select(table).order_by(*table.primary_key.columns)
                ).mappings()
            ]
            for table in tables
        }
        source_connection.rollback()
    for file in snapshot["attachments"]:
        root = upload_dir.resolve()
        path = (root / file["storage_name"]).resolve()
        if (
            not path.is_relative_to(root)
            or not path.is_file()
            or path.stat().st_size != file["size_bytes"]
        ):
            raise RuntimeError(f"Missing or inconsistent attachment #{file['id']}; import stopped.")
    with transaction(target, write=True) as connection:
        for table in tables:
            if connection.scalar(select(func.count()).select_from(table)):
                raise RuntimeError(f"Target table {table.name} is not empty; no rows overwritten.")
        for table in tables:
            rows = snapshot[table.name]
            if rows:
                connection.execute(table.insert(), rows)
        report = {}
        for table in tables:
            target_rows = [
                dict(row)
                for row in connection.execute(
                    select(table).order_by(*table.primary_key.columns)
                ).mappings()
            ]
            if digest(target_rows) != digest(snapshot[table.name]):
                raise RuntimeError(f"Content mismatch for {table.name}; import rolled back.")
            report[table.name] = {"rows": len(target_rows), "allColumnsMatch": True}
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=BACKEND_ROOT / ".data" / "retake.sqlite3")
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    settings = Settings.from_env()
    if not settings.database_url.startswith("mysql+pymysql://"):
        raise RuntimeError("Configure a MySQL target in DATABASE_URL before importing.")
    backup_sqlite(args.source, args.backup)
    source = make_engine(f"sqlite:///{args.backup.resolve().as_posix()}")
    target = make_engine(settings.database_url)
    try:
        upgrade(target)
        result = sync_empty_database(source, target, settings.upload_dir)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False))
    finally:
        source.dispose()
        target.dispose()


if __name__ == "__main__":
    main()
