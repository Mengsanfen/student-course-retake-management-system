from sqlalchemy import Connection, and_, func, select, true

from app import models as m
from app.errors import forbidden, missing
from app.schemas import Actor, Application, Approval, Course, Detail, Notice, Page, Role, Status

student = m.users.alias("student")
application_from = (
    m.applications.join(m.enrollments)
    .join(m.offerings)
    .join(m.courses)
    .join(student, student.c.id == m.enrollments.c.student_id)
    .join(m.departments, m.departments.c.id == student.c.department_id)
    .join(m.attachments, m.attachments.c.id == m.applications.c.attachment_id)
)
application_select = select(
    m.applications,
    m.attachments.c.original_name.label("attachment_name"),
    m.courses.c.name.label("course_name"),
    m.courses.c.code.label("course_code"),
    student.c.display_name.label("student_name"),
    student.c.username.label("student_number"),
    m.departments.c.name.label("department_name"),
    m.offerings.c.term,
    m.enrollments.c.student_id,
    m.offerings.c.teacher_id,
    student.c.department_id,
).select_from(application_from)


def scope(actor: Actor):
    match actor.role:
        case Role.STUDENT:
            return m.enrollments.c.student_id == actor.id
        case Role.TEACHER:
            return m.offerings.c.teacher_id == actor.id
        case Role.DEPARTMENT_ADMIN:
            return student.c.department_id == actor.department_id
        case Role.SCHOOL_ADMIN:
            return true()
    raise forbidden()


def check_scope(actor: Actor, row):
    allowed = (
        actor.role == Role.SCHOOL_ADMIN
        or actor.role == Role.STUDENT
        and row["student_id"] == actor.id
        or actor.role == Role.TEACHER
        and row["teacher_id"] == actor.id
        or actor.role == Role.DEPARTMENT_ADMIN
        and row["department_id"] == actor.department_id
    )
    if not allowed:
        raise forbidden()


def get_application(connection: Connection, actor: Actor, application_id: int):
    row = (
        connection.execute(application_select.where(m.applications.c.id == application_id))
        .mappings()
        .first()
    )
    if row is None:
        raise missing()
    check_scope(actor, row)
    return row


def detail(connection: Connection, actor: Actor, application_id: int) -> Detail:
    row = get_application(connection, actor, application_id)
    history = connection.execute(
        select(
            m.approvals,
            m.users.c.display_name.label("reviewer_name"),
        )
        .join(m.users)
        .where(m.approvals.c.application_id == application_id)
        .order_by(m.approvals.c.id)
    ).mappings()
    return Detail(
        application=Application.model_validate(row),
        approvals=[Approval.model_validate(item) for item in history],
    )


def stage_for(actor: Actor) -> Status:
    match actor.role:
        case Role.TEACHER:
            return Status.TEACHER_REVIEW
        case Role.DEPARTMENT_ADMIN:
            return Status.DEPARTMENT_REVIEW
        case Role.SCHOOL_ADMIN:
            return Status.SCHOOL_REVIEW
    raise forbidden()


def list_applications(connection, actor: Actor, page: int, size: int, pending: bool):
    condition = scope(actor)
    if pending:
        stage = Status.TEACHER_REVIEW if actor.role == Role.STUDENT else stage_for(actor)
        condition = and_(condition, m.applications.c.status == stage)
    total = connection.scalar(select(func.count()).select_from(application_from).where(condition))
    rows = connection.execute(
        application_select.where(condition)
        .order_by(
            m.applications.c.created_at.desc(),
            m.applications.c.id.desc(),
        )
        .limit(size)
        .offset((page - 1) * size)
    ).mappings()
    return Page[Application](
        items=[Application.model_validate(r) for r in rows], page=page, size=size, total=total
    )


def list_courses(connection, actor: Actor):
    if actor.role != Role.STUDENT:
        raise forbidden()
    rows = connection.execute(
        select(
            m.enrollments.c.id,
            m.courses.c.name.label("course_name"),
            m.courses.c.code.label("course_code"),
            m.offerings.c.term,
            m.courses.c.credits,
            m.users.c.display_name.label("teacher_name"),
            m.offerings.c.exam_at,
            m.enrollments.c.score,
        )
        .select_from(
            m.enrollments.join(m.offerings)
            .join(m.courses)
            .join(m.users, m.users.c.id == m.offerings.c.teacher_id)
        )
        .where(m.enrollments.c.student_id == actor.id)
        .order_by(m.enrollments.c.id)
    ).mappings()
    return [Course.model_validate(row) for row in rows]


def list_notices(connection, actor: Actor, page: int, size: int):
    condition = m.notifications.c.recipient_id == actor.id
    total = connection.scalar(select(func.count()).select_from(m.notifications).where(condition))
    rows = connection.execute(
        select(m.notifications)
        .where(condition)
        .order_by(m.notifications.c.id.desc())
        .limit(size)
        .offset((page - 1) * size)
    ).mappings()
    return Page[Notice](
        items=[Notice.model_validate(r) for r in rows], page=page, size=size, total=total
    )


def notify(connection, recipient_id: int, title: str, content: str, application_id: int, now):
    connection.execute(
        m.notifications.insert().values(
            recipient_id=recipient_id,
            title=title,
            content=content,
            application_id=application_id,
            is_read=False,
            created_at=now,
        )
    )
