from datetime import UTC

import sqlalchemy as sa
from sqlalchemy.dialects.mysql import DATETIME
from sqlalchemy.types import TypeDecorator

metadata = sa.MetaData()
ID = sa.BigInteger().with_variant(sa.Integer, "sqlite")


class UTCDateTime(TypeDecorator):
    """Persist naive UTC, expose aware UTC, including when the DB has no TZ type."""

    impl = sa.DateTime
    cache_ok = True

    def load_dialect_impl(self, dialect):
        return dialect.type_descriptor(
            DATETIME(fsp=6) if dialect.name == "mysql" else sa.DateTime()
        )

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Timezone-aware datetime required")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        return value.replace(tzinfo=UTC) if value is not None else None


departments = sa.Table(
    "departments",
    metadata,
    sa.Column("id", ID, primary_key=True, autoincrement=False),
    sa.Column("name", sa.String(100), nullable=False, unique=True),
)
users = sa.Table(
    "users",
    metadata,
    sa.Column("id", ID, primary_key=True, autoincrement=False),
    sa.Column("username", sa.String(50), nullable=False, unique=True),
    sa.Column("password_hash", sa.String(100), nullable=False),
    sa.Column("display_name", sa.String(50), nullable=False),
    sa.Column("role", sa.String(30), nullable=False),
    sa.Column("department_id", ID, sa.ForeignKey("departments.id"), nullable=False),
    sa.CheckConstraint(
        "role IN ('STUDENT','TEACHER','DEPARTMENT_ADMIN','SCHOOL_ADMIN')", name="ck_user_role"
    ),
)
courses = sa.Table(
    "courses",
    metadata,
    sa.Column("id", ID, primary_key=True, autoincrement=False),
    sa.Column("code", sa.String(30), nullable=False, unique=True),
    sa.Column("name", sa.String(100), nullable=False),
    sa.Column("credits", sa.Numeric(3, 1), nullable=False),
)
offerings = sa.Table(
    "course_offerings",
    metadata,
    sa.Column("id", ID, primary_key=True, autoincrement=False),
    sa.Column("course_id", ID, sa.ForeignKey("courses.id"), nullable=False),
    sa.Column("teacher_id", ID, sa.ForeignKey("users.id"), nullable=False),
    sa.Column("term", sa.String(30), nullable=False),
    sa.Column("exam_at", UTCDateTime(), nullable=False),
)
enrollments = sa.Table(
    "enrollments",
    metadata,
    sa.Column("id", ID, primary_key=True, autoincrement=False),
    sa.Column("student_id", ID, sa.ForeignKey("users.id"), nullable=False),
    sa.Column("offering_id", ID, sa.ForeignKey("course_offerings.id"), nullable=False),
    sa.Column("score", sa.Numeric(5, 2)),
    sa.UniqueConstraint("student_id", "offering_id", name="uq_enrollment"),
    sa.CheckConstraint("score IS NULL OR (score>=0 AND score<=100)", name="ck_score"),
)
attachments = sa.Table(
    "attachments",
    metadata,
    sa.Column("id", ID, primary_key=True),
    sa.Column("owner_id", ID, sa.ForeignKey("users.id"), nullable=False),
    sa.Column("storage_name", sa.String(80), nullable=False, unique=True),
    sa.Column("original_name", sa.String(180), nullable=False),
    sa.Column("media_type", sa.String(50), nullable=False),
    sa.Column("size_bytes", sa.BigInteger, nullable=False),
    sa.Column("created_at", UTCDateTime(), nullable=False),
)
applications = sa.Table(
    "deferral_applications",
    metadata,
    sa.Column("id", ID, primary_key=True),
    sa.Column("enrollment_id", ID, sa.ForeignKey("enrollments.id"), nullable=False),
    sa.Column("attachment_id", ID, sa.ForeignKey("attachments.id"), nullable=False, unique=True),
    sa.Column("reason", sa.String(1000), nullable=False),
    sa.Column("status", sa.String(30), nullable=False),
    sa.Column("created_at", UTCDateTime(), nullable=False),
    sa.Column("updated_at", UTCDateTime(), nullable=False),
    sa.CheckConstraint(
        "status IN ('TEACHER_REVIEW','DEPARTMENT_REVIEW','SCHOOL_REVIEW','APPROVED','REJECTED')",
        name="ck_deferral_status",
    ),
    sa.Index("idx_deferral_enrollment", "enrollment_id", "status"),
    sa.Index("idx_deferral_status", "status", "created_at"),
)
approvals = sa.Table(
    "approval_records",
    metadata,
    sa.Column("id", ID, primary_key=True),
    sa.Column("application_id", ID, sa.ForeignKey("deferral_applications.id"), nullable=False),
    sa.Column("reviewer_id", ID, sa.ForeignKey("users.id"), nullable=False),
    sa.Column("stage", sa.String(30), nullable=False),
    sa.Column("decision", sa.String(10), nullable=False),
    sa.Column("comment", sa.String(500), nullable=False),
    sa.Column("created_at", UTCDateTime(), nullable=False),
    sa.UniqueConstraint("application_id", "stage", name="uq_approval_stage"),
    sa.CheckConstraint("decision IN ('APPROVE','REJECT')", name="ck_decision"),
)
notifications = sa.Table(
    "notifications",
    metadata,
    sa.Column("id", ID, primary_key=True),
    sa.Column("recipient_id", ID, sa.ForeignKey("users.id"), nullable=False),
    sa.Column("title", sa.String(100), nullable=False),
    sa.Column("content", sa.String(500), nullable=False),
    sa.Column("application_id", ID, sa.ForeignKey("deferral_applications.id")),
    sa.Column("is_read", sa.Boolean, nullable=False, server_default=sa.false()),
    sa.Column("created_at", UTCDateTime(), nullable=False),
    sa.Index("idx_notification_recipient", "recipient_id", "created_at"),
)
sessions = sa.Table(
    "auth_sessions",
    metadata,
    sa.Column("token_hash", sa.String(64), primary_key=True),
    sa.Column("user_id", ID, sa.ForeignKey("users.id")),
    sa.Column("csrf_token", sa.String(64), nullable=False),
    sa.Column("expires_at", UTCDateTime(), nullable=False, index=True),
)
