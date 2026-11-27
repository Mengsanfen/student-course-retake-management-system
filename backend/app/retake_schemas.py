from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, PositiveInt, model_validator

from app.schemas import DTO, Approval


class TimeSlot(DTO):
    start_week: Annotated[int, Field(ge=1, le=30)]
    end_week: Annotated[int, Field(ge=1, le=30)]
    weekday: Annotated[int, Field(ge=1, le=7)]
    start_period: Annotated[int, Field(ge=1, le=12)]
    end_period: Annotated[int, Field(ge=1, le=12)]

    @model_validator(mode="after")
    def ordered(self):
        if self.end_week < self.start_week or self.end_period < self.start_period:
            raise ValueError("End must not precede start")
        return self


class RetakeSubmit(DTO):
    enrollment_id: PositiveInt
    term_id: PositiveInt
    reason: Annotated[str, Field(min_length=10, max_length=1000)]


class ClassCreate(DTO):
    name: Annotated[str, Field(min_length=2, max_length=80)]
    course_id: PositiveInt
    term_id: PositiveInt
    teacher_id: PositiveInt
    capacity: Annotated[int, Field(ge=1, le=200)]
    room: Annotated[str, Field(min_length=1, max_length=60)]
    slots: Annotated[list[TimeSlot], Field(min_length=1, max_length=8)]


class ClassUpdate(DTO):
    status: Literal["OPEN", "CLOSED"]
    capacity: Annotated[int, Field(ge=1, le=200)]


class RetakeApplication(DTO):
    id: int
    student_id: int
    enrollment_id: int
    course_id: int
    course_name: str
    course_code: str
    score: float
    student_name: str
    student_number: str
    department_name: str
    term_id: int
    term: str
    reason: str
    status: Literal["DEPARTMENT_REVIEW", "SCHOOL_REVIEW", "APPROVED", "REJECTED", "ENROLLED"]
    class_id: int | None
    class_name: str | None
    created_at: datetime
    updated_at: datetime


class RetakeDetail(DTO):
    application: RetakeApplication
    approvals: list[Approval]


class RetakeClass(DTO):
    id: int
    name: str
    course_id: int
    course_name: str
    course_code: str
    term_id: int
    term: str
    teacher_id: int
    teacher_name: str
    capacity: int
    enrolled_count: int
    room: str
    status: Literal["OPEN", "CLOSED"]
    slots: list[TimeSlot]


class EnrollmentSubmit(DTO):
    application_id: PositiveInt
    class_id: PositiveInt


class ConflictRequest(DTO):
    application_id: PositiveInt


class ConflictItem(DTO):
    source: Literal["REGULAR", "RETAKE"]
    course_name: str
    class_name: str
    existing_slot: TimeSlot
    requested_slot: TimeSlot
    explanation: str


class ConflictResult(DTO):
    allowed: bool
    reasons: list[str]
    conflicts: list[ConflictItem]
    alternatives: list[RetakeClass]
