"""Provision only the two local project schemas; never store the root password."""

import getpass
import secrets

import pymysql
from sqlalchemy.engine import URL

from app.config import BACKEND_ROOT

DATABASE = "retake_management"
TEST_DATABASE = "retake_management_test"
APP_USER = "retake_app"


def main():
    env_path = BACKEND_ROOT / ".env"
    test_env = BACKEND_ROOT / ".env.mysql-test"
    if env_path.exists() or test_env.exists():
        raise RuntimeError("Local environment files already exist; refusing to overwrite them.")
    password = getpass.getpass("Local MySQL root password: ")
    connection = pymysql.connect(
        host="127.0.0.1",
        port=3306,
        user="root",
        password=password,
        charset="utf8mb4",
        connect_timeout=5,
        autocommit=True,
    )
    password = None
    app_password = secrets.token_urlsafe(32)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM mysql.user WHERE User=%s AND Host=%s", (APP_USER, "127.0.0.1")
            )
            if cursor.fetchone():
                raise RuntimeError(
                    "Project MySQL account already exists; its credentials were not changed."
                )
            for name in (DATABASE, TEST_DATABASE):
                cursor.execute(
                    "SELECT 1 FROM information_schema.SCHEMATA WHERE SCHEMA_NAME=%s", (name,)
                )
                if cursor.fetchone():
                    raise RuntimeError(f"Schema {name} already exists; refusing to overwrite it.")
            for name in (DATABASE, TEST_DATABASE):
                # Names are fixed application constants, never user-provided SQL.
                cursor.execute(
                    f"CREATE DATABASE `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_as_cs"
                )
            cursor.execute(
                "CREATE USER %s@%s IDENTIFIED BY %s", (APP_USER, "127.0.0.1", app_password)
            )
            for name in (DATABASE, TEST_DATABASE):
                cursor.execute(
                    f"GRANT ALL PRIVILEGES ON `{name}`.* TO %s@%s", (APP_USER, "127.0.0.1")
                )

        def url(database):
            return URL.create(
                "mysql+pymysql",
                username=APP_USER,
                password=app_password,
                host="127.0.0.1",
                port=3306,
                database=database,
                query={"charset": "utf8mb4"},
            ).render_as_string(hide_password=False)

        env_path.write_text(
            f"DATABASE_URL={url(DATABASE)}\nDEMO_MODE=true\nCOOKIE_SECURE=false\nSESSION_MINUTES=30\n",
            encoding="utf-8",
        )
        test_env.write_text(f"MYSQL_TEST_DATABASE_URL={url(TEST_DATABASE)}\n", encoding="utf-8")
        print(f"Created {DATABASE} and {TEST_DATABASE}; localhost-only project account configured.")
        print("Credentials saved only in ignored local environment files; root password not saved.")
    finally:
        connection.close()


if __name__ == "__main__":
    main()
