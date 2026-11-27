from sqlalchemy import and_, func, select, true

from app import models as m
from app.errors import forbidden, missing
from app.retake_schemas import RetakeApplication, RetakeClass, RetakeDetail, TimeSlot
from app.schemas import Actor, Approval, Page, Role

student = m.users.alias("retake_student")
teacher = m.users.alias("class_teacher")
application_from = (
    m.retakes.join(student, student.c.id == m.retakes.c.student_id)
    .join(m.departments, m.departments.c.id == student.c.department_id)
    .join(m.courses, m.courses.c.id == m.retakes.c.course_id)
    .join(m.enrollments, m.enrollments.c.id == m.retakes.c.enrollment_id)
    .join(m.academic_terms, m.academic_terms.c.id == m.retakes.c.term_id)
    .outerjoin(m.retake_enrollments, m.retake_enrollments.c.application_id == m.retakes.c.id)
    .outerjoin(m.retake_classes, m.retake_classes.c.id == m.retake_enrollments.c.class_id)
)
application_select = select(
    m.retakes,
    m.courses.c.name.label("course_name"),
    m.courses.c.code.label("course_code"),
    m.enrollments.c.score,
    student.c.display_name.label("student_name"),
    student.c.username.label("student_number"),
    student.c.department_id,
    m.departments.c.name.label("department_name"),
    m.academic_terms.c.name.label("term"),
    m.retake_classes.c.id.label("class_id"),
    m.retake_classes.c.name.label("class_name"),
    m.retake_classes.c.teacher_id,
).select_from(application_from)


def scope(actor: Actor):
    match actor.role:
        case Role.STUDENT:
            return m.retakes.c.student_id == actor.id
        case Role.DEPARTMENT_ADMIN:
            return student.c.department_id == actor.department_id
        case Role.SCHOOL_ADMIN:
            return true()
        case Role.TEACHER:
            return m.retake_classes.c.teacher_id == actor.id
    raise forbidden()


def get_application(connection, actor, application_id):
    row = (
        connection.execute(application_select.where(m.retakes.c.id == application_id))
        .mappings()
        .first()
    )
    if row is None:
        raise missing()
    permitted = (
        actor.role == Role.SCHOOL_ADMIN
        or actor.role == Role.STUDENT
        and row["student_id"] == actor.id
        or actor.role == Role.DEPARTMENT_ADMIN
        and row["department_id"] == actor.department_id
        or actor.role == Role.TEACHER
        and row["teacher_id"] == actor.id
    )
    if not permitted:
        raise forbidden()
    return row


def detail(connection, actor, application_id):
    row = get_application(connection, actor, application_id)
    history = connection.execute(
        select(m.retake_approvals, m.users.c.display_name.label("reviewer_name"))
        .join(m.users, m.users.c.id == m.retake_approvals.c.reviewer_id)
        .where(m.retake_approvals.c.application_id == application_id)
        .order_by(m.retake_approvals.c.id)
    ).mappings()
    return RetakeDetail(
        application=RetakeApplication.model_validate(row),
        approvals=[Approval.model_validate(r) for r in history],
    )


def list_applications(connection, actor, page, size, pending):
    condition = scope(actor)
    if pending:
        stage = {
            Role.DEPARTMENT_ADMIN: "DEPARTMENT_REVIEW",
            Role.SCHOOL_ADMIN: "SCHOOL_REVIEW",
        }.get(actor.role)
        condition = (
            and_(condition, m.retakes.c.status == stage)
            if stage
            else and_(condition, m.retakes.c.status.in_(["DEPARTMENT_REVIEW", "SCHOOL_REVIEW"]))
        )
    total = connection.scalar(select(func.count()).select_from(application_from).where(condition))
    rows = connection.execute(
        application_select.where(condition)
        .order_by(m.retakes.c.created_at.desc(), m.retakes.c.id.desc())
        .limit(size)
        .offset((page - 1) * size)
    ).mappings()
    return Page[RetakeApplication](
        items=[RetakeApplication.model_validate(r) for r in rows], total=total, page=page, size=size
    )


def notify(connection, recipient, title, content, application_id, now):
    connection.execute(
        m.notifications.insert().values(
            recipient_id=recipient,
            title=title,
            content=content,
            retake_application_id=application_id,
            application_id=None,
            is_read=False,
            created_at=now,
        )
    )


def class_statement():
    count = (
        select(func.count())
        .select_from(m.retake_enrollments)
        .where(m.retake_enrollments.c.class_id == m.retake_classes.c.id)
        .correlate(m.retake_classes)
        .scalar_subquery()
    )
    return select(
        m.retake_classes,
        m.courses.c.name.label("course_name"),
        m.courses.c.code.label("course_code"),
        m.academic_terms.c.name.label("term"),
        teacher.c.display_name.label("teacher_name"),
        count.label("enrolled_count"),
    )


class_from = (
    m.retake_classes.join(m.courses, m.courses.c.id == m.retake_classes.c.course_id)
    .join(m.academic_terms, m.academic_terms.c.id == m.retake_classes.c.term_id)
    .join(teacher, teacher.c.id == m.retake_classes.c.teacher_id)
)


def classes(connection, condition=true(), *, limit=None, offset=0):
    statement = (
        class_statement().select_from(class_from).where(condition).order_by(m.retake_classes.c.id)
    )
    if limit is not None:
        statement = statement.limit(limit).offset(offset)
    rows = list(connection.execute(statement).mappings())
    if not rows:
        return []
    slots = connection.execute(
        select(m.retake_slots)
        .where(m.retake_slots.c.class_id.in_([r["id"] for r in rows]))
        .order_by(m.retake_slots.c.id)
    ).mappings()
    grouped = {}
    for slot in slots:
        grouped.setdefault(slot["class_id"], []).append(TimeSlot.model_validate(slot))
    return [
        RetakeClass.model_validate({**row, "slots": grouped.get(row["id"], [])}) for row in rows
    ]


def get_class(connection, class_id):
    result = classes(connection, m.retake_classes.c.id == class_id)
    if not result:
        raise missing()
    return result[0]
