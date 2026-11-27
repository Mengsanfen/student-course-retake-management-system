from datetime import datetime
from enum import StrEnum
from typing import Annotated, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, PositiveInt
from pydantic.alias_generators import to_camel


class DTO(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class Role(StrEnum):
    STUDENT = "STUDENT"
    TEACHER = "TEACHER"
    DEPARTMENT_ADMIN = "DEPARTMENT_ADMIN"
    SCHOOL_ADMIN = "SCHOOL_ADMIN"


class Status(StrEnum):
    TEACHER_REVIEW = "TEACHER_REVIEW"
    DEPARTMENT_REVIEW = "DEPARTMENT_REVIEW"
    SCHOOL_REVIEW = "SCHOOL_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class Decision(StrEnum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"


class Actor(DTO):
    id: int
    username: str
    display_name: str
    role: Role
    department_id: int
    department_name: str


class Submit(DTO):
    enrollment_id: PositiveInt
    attachment_id: PositiveInt
    reason: Annotated[str, Field(min_length=10, max_length=1000)]


class Review(DTO):
    decision: Decision
    comment: Annotated[str, Field(max_length=500)] = ""


class Course(DTO):
    id: int
    course_name: str
    course_code: str
    term: str
    credits: float
    teacher_name: str
    exam_at: datetime
    score: float | None


class Application(DTO):
    id: int
    enrollment_id: int
    attachment_id: int
    attachment_name: str
    course_name: str
    course_code: str
    student_name: str
    student_number: str
    department_name: str
    term: str
    reason: str
    status: Status
    created_at: datetime
    updated_at: datetime


class Approval(DTO):
    id: int
    stage: Status
    reviewer_name: str
    decision: Decision
    comment: str
    created_at: datetime


class Detail(DTO):
    application: Application
    approvals: list[Approval]


T = TypeVar("T")


class Page(DTO, Generic[T]):
    items: list[T]
    page: int
    size: int
    total: int


class Notice(DTO):
    id: int
    title: str
    content: str
    application_id: int | None
    is_read: bool
    created_at: datetime


class AttachmentResult(DTO):
    id: int
    original_name: str
    size_bytes: int


class ApiError(DTO):
    code: str
    message: str
