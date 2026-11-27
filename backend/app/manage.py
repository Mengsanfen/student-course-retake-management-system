import argparse
from datetime import timedelta
from decimal import Decimal

from alembic import command
from alembic.config import Config
from sqlalchemy import func, select

from app import models as m
from app.config import BACKEND_ROOT, Settings
from app.database import make_engine, transaction
from app.demo_retake import seed_retake_demo
from app.security import hash_password, utcnow


def upgrade(engine):
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")


def seed_demo(engine, settings: Settings):
    if not settings.demo_mode:
        raise RuntimeError("Demo seeding requires DEMO_MODE=true")
    if not 8 <= len(settings.demo_password.encode()) <= 72:
        raise ValueError("DEMO_PASSWORD must be 8-72 UTF-8 bytes")
    with transaction(engine, write=True) as connection:
        if connection.scalar(select(func.count()).select_from(m.users)):
            seed_retake_demo(connection)
            return
        connection.execute(
            m.departments.insert(),
            [
                {"id": 1, "name": "计算机与信息工程学院"},
                {"id": 2, "name": "经济管理学院"},
            ],
        )
        password = hash_password(settings.demo_password)
        rows = [
            (1, "20240001", "高同学", "STUDENT", 1),
            (2, "20240002", "林同学", "STUDENT", 1),
            (3, "20240003", "周同学", "STUDENT", 2),
            (11, "teacher01", "陈老师", "TEACHER", 1),
            (12, "teacher02", "吴老师", "TEACHER", 1),
            (21, "dept01", "王老师", "DEPARTMENT_ADMIN", 1),
            (22, "dept02", "赵老师", "DEPARTMENT_ADMIN", 2),
            (31, "admin", "教务管理员", "SCHOOL_ADMIN", 1),
        ]
        connection.execute(
            m.users.insert(),
            [
                dict(
                    id=i,
                    username=u,
                    display_name=n,
                    role=r,
                    department_id=d,
                    password_hash=password,
                )
                for i, u, n, r, d in rows
            ],
        )
        connection.execute(
            m.courses.insert(),
            [
                {"id": i, "code": code, "name": name, "credits": Decimal(credits)}
                for i, code, name, credits in [
                    (1, "CS201", "数据结构", "4"),
                    (2, "CS203", "数据库原理", "3.5"),
                    (3, "CS205", "计算机网络", "3"),
                    (4, "CS101", "程序设计基础", "4"),
                ]
            ],
        )
        connection.execute(
            m.offerings.insert(),
            [
                dict(
                    id=i,
                    course_id=i,
                    teacher_id=12 if i == 3 else 11,
                    term="2026—2027 学年 · 第一学期",
                    exam_at=utcnow() + timedelta(days=30 + i),
                )
                for i in range(1, 5)
            ],
        )
        connection.execute(
            m.enrollments.insert(),
            [
                dict(id=i, student_id=s, offering_id=o, score=score)
                for i, s, o, score in [
                    (1, 1, 1, None),
                    (2, 1, 2, None),
                    (3, 1, 3, None),
                    (4, 1, 4, 52),
                    (5, 2, 1, None),
                    (6, 3, 1, None),
                ]
            ],
        )
        seed_retake_demo(connection)


def main():
    parser = argparse.ArgumentParser(description="Database migration and demo data management")
    parser.add_argument("action", choices=["upgrade", "seed-demo"])
    args = parser.parse_args()
    settings = Settings.from_env()
    engine = make_engine(settings.database_url)
    try:
        if args.action == "upgrade":
            upgrade(engine)
        else:
            seed_demo(engine, settings)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
