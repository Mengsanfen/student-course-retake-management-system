"""M1 business tables and revocable server-side sessions.

The schema is frozen here. Do not derive historical migrations from app.models.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import DATETIME

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

ID = sa.BigInteger().with_variant(sa.Integer, "sqlite")
TIME = sa.DateTime().with_variant(DATETIME(fsp=6), "mysql")


def upgrade():
    op.create_table(
        "departments",
        sa.Column("id", ID, primary_key=True, autoincrement=False),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
    )
    op.create_table(
        "users",
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
    op.create_table(
        "courses",
        sa.Column("id", ID, primary_key=True, autoincrement=False),
        sa.Column("code", sa.String(30), nullable=False, unique=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("credits", sa.Numeric(3, 1), nullable=False),
    )
    op.create_table(
        "course_offerings",
        sa.Column("id", ID, primary_key=True, autoincrement=False),
        sa.Column("course_id", ID, sa.ForeignKey("courses.id"), nullable=False),
        sa.Column("teacher_id", ID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("term", sa.String(30), nullable=False),
        sa.Column("exam_at", TIME, nullable=False),
    )
    op.create_table(
        "enrollments",
        sa.Column("id", ID, primary_key=True, autoincrement=False),
        sa.Column("student_id", ID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("offering_id", ID, sa.ForeignKey("course_offerings.id"), nullable=False),
        sa.Column("score", sa.Numeric(5, 2)),
        sa.UniqueConstraint("student_id", "offering_id", name="uq_enrollment"),
        sa.CheckConstraint("score IS NULL OR (score>=0 AND score<=100)", name="ck_score"),
    )
    op.create_table(
        "attachments",
        sa.Column("id", ID, primary_key=True),
        sa.Column("owner_id", ID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("storage_name", sa.String(80), nullable=False, unique=True),
        sa.Column("original_name", sa.String(180), nullable=False),
        sa.Column("media_type", sa.String(50), nullable=False),
        sa.Column("size_bytes", sa.BigInteger, nullable=False),
        sa.Column("created_at", TIME, nullable=False),
    )
    op.create_table(
        "deferral_applications",
        sa.Column("id", ID, primary_key=True),
        sa.Column("enrollment_id", ID, sa.ForeignKey("enrollments.id"), nullable=False),
        sa.Column(
            "attachment_id", ID, sa.ForeignKey("attachments.id"), nullable=False, unique=True
        ),
        sa.Column("reason", sa.String(1000), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("created_at", TIME, nullable=False),
        sa.Column("updated_at", TIME, nullable=False),
        sa.CheckConstraint(
            "status IN ('TEACHER_REVIEW','DEPARTMENT_REVIEW','SCHOOL_REVIEW','APPROVED','REJECTED')",
            name="ck_deferral_status",
        ),
    )
    op.create_index("idx_deferral_enrollment", "deferral_applications", ["enrollment_id", "status"])
    op.create_index("idx_deferral_status", "deferral_applications", ["status", "created_at"])
    op.create_table(
        "approval_records",
        sa.Column("id", ID, primary_key=True),
        sa.Column("application_id", ID, sa.ForeignKey("deferral_applications.id"), nullable=False),
        sa.Column("reviewer_id", ID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("stage", sa.String(30), nullable=False),
        sa.Column("decision", sa.String(10), nullable=False),
        sa.Column("comment", sa.String(500), nullable=False),
        sa.Column("created_at", TIME, nullable=False),
        sa.UniqueConstraint("application_id", "stage", name="uq_approval_stage"),
        sa.CheckConstraint("decision IN ('APPROVE','REJECT')", name="ck_decision"),
    )
    op.create_table(
        "notifications",
        sa.Column("id", ID, primary_key=True),
        sa.Column("recipient_id", ID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(100), nullable=False),
        sa.Column("content", sa.String(500), nullable=False),
        sa.Column("application_id", ID, sa.ForeignKey("deferral_applications.id")),
        sa.Column("is_read", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", TIME, nullable=False),
    )
    op.create_index("idx_notification_recipient", "notifications", ["recipient_id", "created_at"])
    op.create_table(
        "auth_sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("user_id", ID, sa.ForeignKey("users.id")),
        sa.Column("csrf_token", sa.String(64), nullable=False),
        sa.Column("expires_at", TIME, nullable=False),
    )
    op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"])


def downgrade():
    for table in [
        "auth_sessions",
        "notifications",
        "approval_records",
        "deferral_applications",
        "attachments",
        "enrollments",
        "course_offerings",
        "courses",
        "users",
        "departments",
    ]:
        op.drop_table(table)
