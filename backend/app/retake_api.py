from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Response
from sqlalchemy import func, select, true

from app import models as m
from app import repository as base_repo
from app import retake_repository as repo
from app import retake_service as service
from app.database import transaction
from app.retake_schemas import (
    ClassCreate,
    ClassUpdate,
    ConflictRequest,
    ConflictResult,
    EnrollmentSubmit,
    RetakeApplication,
    RetakeClass,
    RetakeDetail,
    RetakeSubmit,
    TimeSlot,
)
from app.schemas import Actor, Page, Review, Role
from app.security import CSRF_HEADER, require_actor

ActorDependency = Annotated[Actor, Depends(require_actor)]


def csrf_documentation(token: Annotated[str, Header(alias=CSRF_HEADER)]):
    """The security middleware validates this header before body parsing."""


def create_router(engine):
    router = APIRouter(prefix="/api/v1", tags=["重修"])
    write = [Depends(csrf_documentation)]

    @router.get("/retake-meta")
    def meta(actor: ActorDependency):
        with transaction(engine) as connection:
            terms = [
                {"id": row.id, "name": row.name, "weekCount": row.week_count}
                for row in connection.execute(
                    select(m.academic_terms).order_by(m.academic_terms.c.id)
                )
            ]
            eligible = (
                [
                    course.model_dump(by_alias=True, mode="json")
                    for course in base_repo.list_courses(connection, actor)
                    if course.score is not None and course.score < 60
                ]
                if actor.role == Role.STUDENT
                else []
            )
            courses = (
                [
                    {"id": row.id, "name": row.name, "code": row.code}
                    for row in connection.execute(select(m.courses).order_by(m.courses.c.id))
                ]
                if actor.role == Role.SCHOOL_ADMIN
                else []
            )
            teachers = (
                [
                    {"id": row.id, "name": row.display_name}
                    for row in connection.execute(
                        select(m.users.c.id, m.users.c.display_name)
                        .where(m.users.c.role == Role.TEACHER)
                        .order_by(m.users.c.id)
                    )
                ]
                if actor.role == Role.SCHOOL_ADMIN
                else []
            )
            return {
                "terms": terms,
                "eligibleCourses": eligible,
                "courses": courses,
                "teachers": teachers,
            }

    @router.get("/retakes", response_model=Page[RetakeApplication])
    def applications(
        actor: ActorDependency,
        page: Annotated[int, Query(ge=1, le=100000)] = 1,
        size: Annotated[int, Query(ge=1, le=100)] = 20,
        pending_only: Annotated[bool, Query(alias="pendingOnly")] = False,
    ):
        with transaction(engine) as connection:
            return repo.list_applications(connection, actor, page, size, pending_only)

    @router.get("/retakes/{application_id}", response_model=RetakeDetail)
    def detail(application_id: int, actor: ActorDependency):
        with transaction(engine) as connection:
            return repo.detail(connection, actor, application_id)

    @router.post("/retakes", response_model=RetakeDetail, status_code=201, dependencies=write)
    def submit(body: RetakeSubmit, actor: ActorDependency, response: Response):
        result = service.submit(engine, actor, body)
        response.headers["Location"] = f"/api/v1/retakes/{result.application.id}"
        return result

    @router.post(
        "/retakes/{application_id}/reviews", response_model=RetakeDetail, dependencies=write
    )
    def review(application_id: int, body: Review, actor: ActorDependency):
        return service.review(engine, actor, application_id, body)

    @router.get("/retake-classes", response_model=Page[RetakeClass])
    def classes(
        actor: ActorDependency,
        page: Annotated[int, Query(ge=1, le=100000)] = 1,
        size: Annotated[int, Query(ge=1, le=100)] = 20,
        term_id: Annotated[int | None, Query(alias="termId", gt=0)] = None,
        course_id: Annotated[int | None, Query(alias="courseId", gt=0)] = None,
    ):
        condition = (
            m.retake_classes.c.teacher_id == actor.id if actor.role == Role.TEACHER else true()
        )
        if term_id:
            condition &= m.retake_classes.c.term_id == term_id
        if course_id:
            condition &= m.retake_classes.c.course_id == course_id
        with transaction(engine) as connection:
            total = connection.scalar(
                select(func.count()).select_from(m.retake_classes).where(condition)
            )
            rows = repo.classes(connection, condition, limit=size, offset=(page - 1) * size)
            return Page[RetakeClass](items=rows, total=total, page=page, size=size)

    @router.post("/retake-classes", response_model=RetakeClass, status_code=201, dependencies=write)
    def create_class(body: ClassCreate, actor: ActorDependency, response: Response):
        result = service.create_class(engine, actor, body)
        response.headers["Location"] = f"/api/v1/retake-classes/{result.id}"
        return result

    @router.patch("/retake-classes/{class_id}", response_model=RetakeClass, dependencies=write)
    def update_class(class_id: int, body: ClassUpdate, actor: ActorDependency):
        return service.update_class(engine, actor, class_id, body)

    @router.post(
        "/retake-classes/{class_id}/conflict-check",
        response_model=ConflictResult,
        dependencies=write,
    )
    def conflict_check(class_id: int, body: ConflictRequest, actor: ActorDependency):
        return service.conflict_check(engine, actor, body.application_id, class_id)

    @router.post(
        "/retake-enrollments", response_model=RetakeDetail, status_code=201, dependencies=write
    )
    def enroll(body: EnrollmentSubmit, actor: ActorDependency):
        return service.enroll(engine, actor, body)

    @router.get("/retake-classes/{class_id}/students")
    def roster(class_id: int, actor: ActorDependency):
        rows = service.roster(engine, actor, class_id)
        return [
            {
                "id": row["id"],
                "applicationId": row["application_id"],
                "studentName": row["student_name"],
                "studentNumber": row["student_number"],
                "departmentName": row["department_name"],
            }
            for row in rows
        ]

    @router.get("/timetable")
    def timetable(actor: ActorDependency, term_id: Annotated[int, Query(alias="termId", gt=0)]):
        from app.errors import forbidden, missing

        if actor.role != Role.STUDENT:
            raise forbidden()
        with transaction(engine) as connection:
            term = (
                connection.execute(select(m.academic_terms).where(m.academic_terms.c.id == term_id))
                .mappings()
                .first()
            )
            if term is None:
                raise missing()
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
                    m.offerings.c.term == term["name"],
                )
            ).mappings()
            retakes = connection.execute(
                select(
                    m.retake_slots,
                    m.courses.c.name.label("course_name"),
                    m.retake_classes.c.name.label("class_name"),
                    m.retake_classes.c.room,
                )
                .select_from(
                    m.retake_slots.join(m.retake_classes)
                    .join(m.courses, m.courses.c.id == m.retake_classes.c.course_id)
                    .join(
                        m.retake_enrollments,
                        m.retake_enrollments.c.class_id == m.retake_classes.c.id,
                    )
                )
                .where(
                    m.retake_enrollments.c.student_id == actor.id,
                    m.retake_classes.c.term_id == term_id,
                )
            ).mappings()
            return [
                {
                    "source": source,
                    "courseName": row["course_name"],
                    "className": row.get("class_name", row["course_name"]),
                    "room": row["room"],
                    "slot": TimeSlot.model_validate(row).model_dump(by_alias=True),
                }
                for source, rows in [("REGULAR", regular), ("RETAKE", retakes)]
                for row in rows
            ]

    return router
