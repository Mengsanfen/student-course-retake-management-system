"""M2 retake applications, classes, schedules and enrollment."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import DATETIME

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None
ID = sa.BigInteger().with_variant(sa.Integer, "sqlite")
TIME = sa.DateTime().with_variant(DATETIME(fsp=6), "mysql")


def slot_columns():
    return [
        sa.Column("start_week", sa.Integer, nullable=False),
        sa.Column("end_week", sa.Integer, nullable=False),
        sa.Column("weekday", sa.Integer, nullable=False),
        sa.Column("start_period", sa.Integer, nullable=False),
        sa.Column("end_period", sa.Integer, nullable=False),
    ]


SLOT_RULE = "start_week>=1 AND end_week>=start_week AND end_week<=30 AND weekday BETWEEN 1 AND 7 AND start_period>=1 AND end_period>=start_period AND end_period<=12"


def upgrade():
    op.create_table(
        "academic_terms",
        sa.Column("id", ID, primary_key=True),
        sa.Column("name", sa.String(60), nullable=False, unique=True),
        sa.Column("week_count", sa.Integer, nullable=False),
        sa.CheckConstraint("week_count BETWEEN 1 AND 30", name="ck_term_weeks"),
    )
    op.create_table(
        "offering_time_slots",
        sa.Column("id", ID, primary_key=True),
        sa.Column("offering_id", ID, sa.ForeignKey("course_offerings.id"), nullable=False),
        *slot_columns(),
        sa.Column("room", sa.String(60), nullable=False),
        sa.CheckConstraint(SLOT_RULE, name="ck_offering_slot"),
    )
    op.create_table(
        "retake_applications",
        sa.Column("id", ID, primary_key=True),
        sa.Column("student_id", ID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("enrollment_id", ID, sa.ForeignKey("enrollments.id"), nullable=False),
        sa.Column("course_id", ID, sa.ForeignKey("courses.id"), nullable=False),
        sa.Column("term_id", ID, sa.ForeignKey("academic_terms.id"), nullable=False),
        sa.Column("reason", sa.String(1000), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=True),
        sa.Column("created_at", TIME, nullable=False),
        sa.Column("updated_at", TIME, nullable=False),
        sa.UniqueConstraint(
            "student_id", "course_id", "term_id", "is_active", name="uq_active_retake"
        ),
        sa.CheckConstraint(
            "status IN ('DEPARTMENT_REVIEW','SCHOOL_REVIEW','APPROVED','REJECTED','ENROLLED')",
            name="ck_retake_status",
        ),
        sa.CheckConstraint(
            "(status='REJECTED' AND is_active IS NULL) OR (status<>'REJECTED' AND is_active IS NOT NULL AND is_active=1)",
            name="ck_retake_active",
        ),
    )
    op.create_index("idx_retake_status", "retake_applications", ["status", "created_at"])
    op.create_table(
        "retake_approval_records",
        sa.Column("id", ID, primary_key=True),
        sa.Column("application_id", ID, sa.ForeignKey("retake_applications.id"), nullable=False),
        sa.Column("reviewer_id", ID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("stage", sa.String(30), nullable=False),
        sa.Column("decision", sa.String(10), nullable=False),
        sa.Column("comment", sa.String(500), nullable=False),
        sa.Column("created_at", TIME, nullable=False),
        sa.UniqueConstraint("application_id", "stage", name="uq_retake_approval_stage"),
        sa.CheckConstraint(
            "stage IN ('DEPARTMENT_REVIEW','SCHOOL_REVIEW')", name="ck_retake_stage"
        ),
        sa.CheckConstraint("decision IN ('APPROVE','REJECT')", name="ck_retake_decision"),
    )
    op.create_table(
        "retake_classes",
        sa.Column("id", ID, primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("course_id", ID, sa.ForeignKey("courses.id"), nullable=False),
        sa.Column("term_id", ID, sa.ForeignKey("academic_terms.id"), nullable=False),
        sa.Column("teacher_id", ID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("capacity", sa.Integer, nullable=False),
        sa.Column("room", sa.String(60), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("created_by", ID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", TIME, nullable=False),
        sa.UniqueConstraint("term_id", "name", name="uq_retake_class_name"),
        sa.CheckConstraint("capacity BETWEEN 1 AND 200", name="ck_class_capacity"),
        sa.CheckConstraint("status IN ('OPEN','CLOSED')", name="ck_class_status"),
    )
    op.create_table(
        "retake_class_time_slots",
        sa.Column("id", ID, primary_key=True),
        sa.Column("class_id", ID, sa.ForeignKey("retake_classes.id"), nullable=False),
        *slot_columns(),
        sa.CheckConstraint(SLOT_RULE, name="ck_retake_slot"),
    )
    op.create_table(
        "retake_enrollments",
        sa.Column("id", ID, primary_key=True),
        sa.Column(
            "application_id",
            ID,
            sa.ForeignKey("retake_applications.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("student_id", ID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("class_id", ID, sa.ForeignKey("retake_classes.id"), nullable=False),
        sa.Column("created_at", TIME, nullable=False),
        sa.UniqueConstraint("student_id", "class_id", name="uq_student_retake_class"),
    )
    with op.batch_alter_table("notifications") as batch:
        batch.add_column(sa.Column("retake_application_id", ID, nullable=True))
        batch.create_foreign_key(
            "fk_notification_retake", "retake_applications", ["retake_application_id"], ["id"]
        )


def downgrade():
    with op.batch_alter_table("notifications") as batch:
        batch.drop_constraint("fk_notification_retake", type_="foreignkey")
        batch.drop_column("retake_application_id")
    for name in [
        "retake_enrollments",
        "retake_class_time_slots",
        "retake_classes",
        "retake_approval_records",
        "retake_applications",
        "offering_time_slots",
        "academic_terms",
    ]:
        op.drop_table(name)
