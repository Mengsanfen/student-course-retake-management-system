"""Add M2 demo records without replacing M1 applications, grades or notifications."""

from sqlalchemy import func, select

from app import models as m
from app.security import utcnow


def seed_retake_demo(connection):
    offering = (
        connection.execute(select(m.offerings).where(m.offerings.c.id == 1)).mappings().first()
    )
    if offering is None or not connection.scalar(select(m.courses.c.id).where(m.courses.c.id == 4)):
        return
    term_id = connection.scalar(
        select(m.academic_terms.c.id).where(m.academic_terms.c.name == offering["term"])
    )
    if term_id is None:
        term_id = connection.execute(
            m.academic_terms.insert().values(name=offering["term"], week_count=20)
        ).inserted_primary_key[0]
    for offering_id, weekday, period, room in [
        (1, 1, 1, "A101"),
        (2, 3, 3, "A102"),
        (3, 4, 5, "A103"),
    ]:
        if not connection.scalar(select(m.offerings.c.id).where(m.offerings.c.id == offering_id)):
            continue
        if not connection.scalar(
            select(func.count())
            .select_from(m.offering_slots)
            .where(m.offering_slots.c.offering_id == offering_id)
        ):
            connection.execute(
                m.offering_slots.insert().values(
                    offering_id=offering_id,
                    start_week=1,
                    end_week=16,
                    weekday=weekday,
                    start_period=period,
                    end_period=period + 1,
                    room=room,
                )
            )
    for name, teacher, weekday, period, room, capacity in [
        ("程序设计基础 · 周一班", 12, 1, 1, "B201", 20),
        ("程序设计基础 · 周六班", 11, 6, 1, "B202", 20),
        ("程序设计基础 · 周日小班", 12, 7, 3, "B203", 1),
    ]:
        if connection.scalar(
            select(m.retake_classes.c.id).where(
                m.retake_classes.c.term_id == term_id, m.retake_classes.c.name == name
            )
        ):
            continue
        class_id = connection.execute(
            m.retake_classes.insert().values(
                name=name,
                course_id=4,
                term_id=term_id,
                teacher_id=teacher,
                capacity=capacity,
                room=room,
                status="OPEN",
                created_by=31,
                created_at=utcnow(),
            )
        ).inserted_primary_key[0]
        connection.execute(
            m.retake_slots.insert().values(
                class_id=class_id,
                start_week=1,
                end_week=16,
                weekday=weekday,
                start_period=period,
                end_period=period + 1,
            )
        )
