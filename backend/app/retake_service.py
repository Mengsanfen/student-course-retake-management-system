from sqlalchemy import or_, select, update

from app import models as m
from app import retake_repository as repo
from app.database import transaction
from app.errors import conflict, forbidden, invalid, missing
from app.retake_schemas import ClassCreate, ConflictItem, ConflictResult, TimeSlot
from app.schemas import Role
from app.security import utcnow


def overlap(left, right):
    return (
        left.weekday == right.weekday
        and left.start_week <= right.end_week
        and right.start_week <= left.end_week
        and left.start_period <= right.end_period
        and right.start_period <= left.end_period
    )


def slot_label(slot):
    return f"第{slot.start_week}–{slot.end_week}周，周{'一二三四五六日'[slot.weekday - 1]}第{slot.start_period}–{slot.end_period}节"


def lock_student(connection, student_id):
    connection.execute(
        select(m.users.c.id).where(m.users.c.id == student_id).with_for_update()
    ).one()


def submit(engine, actor, body):
    if actor.role != Role.STUDENT:
        raise forbidden()
    if len(body.reason.strip()) < 10:
        raise invalid("申请理由需填写10–1000字有效内容")
    with transaction(engine, write=True) as connection:
        lock_student(connection, actor.id)
        enrollment = (
            connection.execute(
                select(m.enrollments, m.offerings.c.course_id)
                .join(m.offerings)
                .where(m.enrollments.c.id == body.enrollment_id)
            )
            .mappings()
            .first()
        )
        if enrollment is None:
            raise missing()
        if enrollment["student_id"] != actor.id:
            raise forbidden()
        if enrollment["score"] is None or enrollment["score"] >= 60:
            raise invalid("仅已有不及格成绩的本人课程可申请重修")
        if not connection.scalar(
            select(m.academic_terms.c.id).where(m.academic_terms.c.id == body.term_id)
        ):
            raise invalid("目标学期不存在")
        if connection.scalar(
            select(m.retakes.c.id).where(
                m.retakes.c.student_id == actor.id,
                m.retakes.c.course_id == enrollment["course_id"],
                m.retakes.c.term_id == body.term_id,
                m.retakes.c.is_active.is_(True),
            )
        ):
            raise conflict("同一课程在该学期已有有效重修申请")
        now = utcnow()
        application_id = connection.execute(
            m.retakes.insert().values(
                student_id=actor.id,
                enrollment_id=body.enrollment_id,
                course_id=enrollment["course_id"],
                term_id=body.term_id,
                reason=body.reason.strip(),
                status="DEPARTMENT_REVIEW",
                is_active=True,
                created_at=now,
                updated_at=now,
            )
        ).inserted_primary_key[0]
        repo.notify(
            connection,
            actor.id,
            "重修申请已提交",
            "申请已进入院系审核，请关注办理进度。",
            application_id,
            now,
        )
        for recipient in connection.scalars(
            select(m.users.c.id).where(
                m.users.c.role == Role.DEPARTMENT_ADMIN,
                m.users.c.department_id == actor.department_id,
            )
        ):
            repo.notify(
                connection,
                recipient,
                "新的重修审核待办",
                f"{actor.display_name}提交了重修申请。",
                application_id,
                now,
            )
        return repo.detail(connection, actor, application_id)


def review(engine, actor, application_id, body):
    expected = {Role.DEPARTMENT_ADMIN: "DEPARTMENT_REVIEW", Role.SCHOOL_ADMIN: "SCHOOL_REVIEW"}.get(
        actor.role
    )
    if expected is None:
        raise forbidden()
    if body.decision == "REJECT" and not body.comment.strip():
        raise invalid("驳回时必须填写原因")
    with transaction(engine, write=True) as connection:
        initial = repo.get_application(connection, actor, application_id)
        lock_student(connection, initial["student_id"])
        connection.execute(
            select(m.retakes.c.id).where(m.retakes.c.id == application_id).with_for_update()
        ).one()
        row = repo.get_application(connection, actor, application_id)
        if row["status"] != expected:
            raise conflict("当前申请不在您的审核节点，请刷新列表")
        next_status = (
            "REJECTED"
            if body.decision == "REJECT"
            else "SCHOOL_REVIEW"
            if expected == "DEPARTMENT_REVIEW"
            else "APPROVED"
        )
        now = utcnow()
        result = connection.execute(
            update(m.retakes)
            .where(m.retakes.c.id == application_id, m.retakes.c.status == expected)
            .values(
                status=next_status,
                is_active=None if next_status == "REJECTED" else True,
                updated_at=now,
            )
        )
        if result.rowcount != 1:
            raise conflict("申请已被处理，请刷新")
        connection.execute(
            m.retake_approvals.insert().values(
                application_id=application_id,
                reviewer_id=actor.id,
                stage=expected,
                decision=body.decision,
                comment=body.comment.strip(),
                created_at=now,
            )
        )
        message = (
            "申请已驳回，请查看完整审核意见。"
            if next_status == "REJECTED"
            else "审核已通过，可以选择重修班级。"
            if next_status == "APPROVED"
            else "院系审核通过，已进入校教务终审。"
        )
        repo.notify(connection, row["student_id"], "重修申请进度更新", message, application_id, now)
        if next_status == "SCHOOL_REVIEW":
            for recipient in connection.scalars(
                select(m.users.c.id).where(m.users.c.role == Role.SCHOOL_ADMIN)
            ):
                repo.notify(
                    connection,
                    recipient,
                    "新的重修审核待办",
                    f"重修申请 #{application_id}待终审。",
                    application_id,
                    now,
                )
        return repo.detail(connection, actor, application_id)


def student_conflicts(connection, actor, target):
    regular = connection.execute(
        select(m.offering_slots, m.courses.c.name.label("course_name"))
        .select_from(
            m.offering_slots.join(m.offerings)
            .join(m.courses)
            .join(m.enrollments, m.enrollments.c.offering_id == m.offerings.c.id)
        )
        .where(
            m.enrollments.c.student_id == actor.id,
            m.enrollments.c.score.is_(None),
            m.offerings.c.term == target.term,
        )
    ).mappings()
    others = connection.execute(
        select(
            m.retake_slots,
            m.retake_classes.c.name.label("class_name"),
            m.courses.c.name.label("course_name"),
        )
        .select_from(
            m.retake_slots.join(m.retake_classes)
            .join(m.courses, m.courses.c.id == m.retake_classes.c.course_id)
            .join(m.retake_enrollments, m.retake_enrollments.c.class_id == m.retake_classes.c.id)
        )
        .where(
            m.retake_enrollments.c.student_id == actor.id,
            m.retake_classes.c.term_id == target.term_id,
            m.retake_classes.c.id != target.id,
        )
    ).mappings()
    conflicts = []
    for source, rows in [("REGULAR", regular), ("RETAKE", others)]:
        for row in rows:
            existing = TimeSlot.model_validate(row)
            for requested in target.slots:
                if overlap(existing, requested):
                    conflicts.append(
                        ConflictItem(
                            source=source,
                            course_name=row["course_name"],
                            class_name=row.get("class_name", row["course_name"]),
                            existing_slot=existing,
                            requested_slot=requested,
                            explanation=f"与{row['course_name']}（{slot_label(existing)}）重叠；所选班级为{slot_label(requested)}",
                        )
                    )
    return conflicts


def check_selection(connection, actor, row, target):
    if actor.role != Role.STUDENT or row["student_id"] != actor.id:
        raise forbidden()
    if row["status"] != "APPROVED":
        raise conflict("重修申请须审核通过且尚未选课")
    if row["course_id"] != target.course_id or row["term_id"] != target.term_id:
        raise invalid("所选班级的课程或学期与申请不一致")
    reasons = []
    if target.status != "OPEN":
        reasons.append("班级已暂停选课")
    if target.enrolled_count >= target.capacity:
        reasons.append("班级已满员")
    conflicts = student_conflicts(connection, actor, target)
    if conflicts:
        reasons.append("上课时间与已有课程冲突")
    return reasons, conflicts


def conflict_check(engine, actor, application_id, class_id):
    with transaction(engine) as connection:
        row = repo.get_application(connection, actor, application_id)
        target = repo.get_class(connection, class_id)
        reasons, conflicts = check_selection(connection, actor, row, target)
        alternatives = []
        if reasons:
            for other in repo.classes(
                connection,
                (m.retake_classes.c.course_id == target.course_id)
                & (m.retake_classes.c.term_id == target.term_id)
                & (m.retake_classes.c.id != target.id),
            ):
                if (
                    other.status == "OPEN"
                    and other.enrolled_count < other.capacity
                    and not student_conflicts(connection, actor, other)
                ):
                    alternatives.append(other)
        return ConflictResult(
            allowed=not reasons, reasons=reasons, conflicts=conflicts, alternatives=alternatives
        )


def enroll(engine, actor, body):
    if actor.role != Role.STUDENT:
        raise forbidden()
    with transaction(engine, write=True) as connection:
        lock_student(connection, actor.id)
        connection.execute(
            select(m.retake_classes.c.id)
            .where(m.retake_classes.c.id == body.class_id)
            .with_for_update()
        ).first()
        connection.execute(
            select(m.retakes.c.id).where(m.retakes.c.id == body.application_id).with_for_update()
        ).first()
        row = repo.get_application(connection, actor, body.application_id)
        target = repo.get_class(connection, body.class_id)
        reasons, conflicts = check_selection(connection, actor, row, target)
        if reasons:
            explanation = conflicts[0].explanation if conflicts else reasons[0]
            raise conflict(explanation)
        now = utcnow()
        connection.execute(
            m.retake_enrollments.insert().values(
                application_id=body.application_id,
                student_id=actor.id,
                class_id=body.class_id,
                created_at=now,
            )
        )
        result = connection.execute(
            update(m.retakes)
            .where(m.retakes.c.id == body.application_id, m.retakes.c.status == "APPROVED")
            .values(status="ENROLLED", updated_at=now)
        )
        if result.rowcount != 1:
            raise conflict("申请已被处理，请刷新")
        repo.notify(
            connection,
            actor.id,
            "重修选课成功",
            f"已加入{target.name}，请按课表上课。",
            body.application_id,
            now,
        )
        repo.notify(
            connection,
            target.teacher_id,
            "重修班级新增学生",
            f"{target.name}新增学生，请查看班级名单。",
            body.application_id,
            now,
        )
        return repo.detail(connection, actor, body.application_id)


def create_class(engine, actor, body: ClassCreate):
    if actor.role != Role.SCHOOL_ADMIN:
        raise forbidden()
    name, room = body.name.strip(), body.room.strip()
    if len(name) < 2 or not room:
        raise invalid("班级名称和教室不能为空")
    with transaction(engine, write=True) as connection:
        term = (
            connection.execute(
                select(m.academic_terms)
                .where(m.academic_terms.c.id == body.term_id)
                .with_for_update()
            )
            .mappings()
            .first()
        )
        if term is None:
            raise invalid("学期不存在")
        teacher = (
            connection.execute(select(m.users).where(m.users.c.id == body.teacher_id))
            .mappings()
            .first()
        )
        if teacher is None or teacher["role"] != Role.TEACHER:
            raise invalid("请选择有效授课教师")
        if not connection.scalar(select(m.courses.c.id).where(m.courses.c.id == body.course_id)):
            raise invalid("课程不存在")
        if any(s.end_week > term["week_count"] for s in body.slots):
            raise invalid("上课周次超出该学期范围")
        for index, slot in enumerate(body.slots):
            if any(overlap(slot, other) for other in body.slots[index + 1 :]):
                raise invalid("同一班级的上课时间段不能互相重叠")
        regular = connection.execute(
            select(m.offering_slots, m.courses.c.name.label("label"))
            .select_from(m.offering_slots.join(m.offerings).join(m.courses))
            .where(
                m.offerings.c.term == term["name"],
                or_(m.offerings.c.teacher_id == body.teacher_id, m.offering_slots.c.room == room),
            )
        ).mappings()
        existing = connection.execute(
            select(m.retake_slots, m.retake_classes.c.name.label("label"))
            .join(m.retake_classes)
            .where(
                m.retake_classes.c.term_id == body.term_id,
                or_(
                    m.retake_classes.c.teacher_id == body.teacher_id,
                    m.retake_classes.c.room == room,
                ),
            )
        ).mappings()
        for rows in (regular, existing):
            for row in rows:
                slot = TimeSlot.model_validate(row)
                if any(overlap(slot, requested) for requested in body.slots):
                    raise conflict(f"教师或教室与{row['label']}的{slot_label(slot)}冲突")
        class_id = connection.execute(
            m.retake_classes.insert().values(
                name=name,
                room=room,
                course_id=body.course_id,
                term_id=body.term_id,
                teacher_id=body.teacher_id,
                capacity=body.capacity,
                status="OPEN",
                created_by=actor.id,
                created_at=utcnow(),
            )
        ).inserted_primary_key[0]
        connection.execute(
            m.retake_slots.insert(),
            [dict(class_id=class_id, **slot.model_dump()) for slot in body.slots],
        )
        return repo.get_class(connection, class_id)


def update_class(engine, actor, class_id, body):
    if actor.role != Role.SCHOOL_ADMIN:
        raise forbidden()
    with transaction(engine, write=True) as connection:
        if not connection.execute(
            select(m.retake_classes.c.id).where(m.retake_classes.c.id == class_id).with_for_update()
        ).first():
            raise missing()
        current = repo.get_class(connection, class_id)
        if body.capacity < current.enrolled_count:
            raise invalid("容量不能小于已选人数")
        connection.execute(
            update(m.retake_classes)
            .where(m.retake_classes.c.id == class_id)
            .values(status=body.status, capacity=body.capacity)
        )
        return repo.get_class(connection, class_id)


def roster(engine, actor, class_id):
    if actor.role == Role.STUDENT:
        raise forbidden()
    with transaction(engine) as connection:
        target = repo.get_class(connection, class_id)
        if actor.role == Role.TEACHER and target.teacher_id != actor.id:
            raise forbidden()
        condition = m.retake_enrollments.c.class_id == class_id
        if actor.role == Role.DEPARTMENT_ADMIN:
            condition &= m.users.c.department_id == actor.department_id
        rows = connection.execute(
            select(
                m.retake_enrollments.c.id,
                m.retake_enrollments.c.application_id,
                m.users.c.display_name.label("student_name"),
                m.users.c.username.label("student_number"),
                m.departments.c.name.label("department_name"),
            )
            .select_from(
                m.retake_enrollments.join(
                    m.users, m.users.c.id == m.retake_enrollments.c.student_id
                ).join(m.departments, m.departments.c.id == m.users.c.department_id)
            )
            .where(condition)
            .order_by(m.users.c.username)
        ).mappings()
        return [dict(row) for row in rows]
