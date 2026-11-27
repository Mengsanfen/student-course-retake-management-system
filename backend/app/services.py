import re
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy import func, select, update

from app import models as m
from app import repository as repo
from app.config import Settings
from app.database import transaction
from app.errors import BusinessError, conflict, forbidden, invalid, missing
from app.schemas import Actor, AttachmentResult, Decision, Review, Role, Status, Submit
from app.security import utcnow


def require_file(settings: Settings, attachment) -> Path:
    root = settings.upload_dir.resolve()
    path = (root / attachment["storage_name"]).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise invalid("证明材料文件不可用，请重新上传")
    return path


def get_attachment(connection, attachment_id: int, *, lock=False):
    statement = select(m.attachments).where(m.attachments.c.id == attachment_id)
    if lock:
        statement = statement.with_for_update()
    row = connection.execute(statement).mappings().first()
    if row is None:
        raise missing()
    return row


def upload(engine, settings: Settings, actor: Actor, file: UploadFile) -> AttachmentResult:
    if actor.role != Role.STUDENT:
        raise forbidden()
    original = re.sub(
        r"[\x00-\x1f\x7f]", "", (file.filename or "").replace("\\", "/").split("/")[-1]
    )
    if not original or len(original) > 180:
        raise invalid("文件名需为1–180个字符")
    content = file.file.read(settings.max_upload_bytes + 1)
    if len(content) > settings.max_upload_bytes:
        raise BusinessError(413, "FILE_TOO_LARGE", "文件不得超过5 MiB")
    if not content:
        raise invalid("请选择非空证明材料")
    suffix = Path(original).suffix.lower()
    if suffix == ".pdf" and content.startswith(b"%PDF-"):
        mime = "application/pdf"
    elif suffix == ".png" and content.startswith(b"\x89PNG\r\n\x1a\n"):
        mime = "image/png"
    elif suffix in {".jpg", ".jpeg"} and content.startswith(b"\xff\xd8\xff"):
        mime = "image/jpeg"
    else:
        raise invalid("仅支持文件内容与扩展名匹配的PDF、PNG或JPEG材料")
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    storage = str(uuid4())
    path = settings.upload_dir / storage
    try:
        with path.open("xb") as target:
            target.write(content)
        with transaction(engine, write=True) as connection:
            result = connection.execute(
                m.attachments.insert().values(
                    owner_id=actor.id,
                    storage_name=storage,
                    original_name=original,
                    media_type=mime,
                    size_bytes=len(content),
                    created_at=utcnow(),
                )
            )
            attachment_id = result.inserted_primary_key[0]
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return AttachmentResult(id=attachment_id, original_name=original, size_bytes=len(content))


def accessible_attachment(connection, actor: Actor, attachment_id: int):
    attachment = get_attachment(connection, attachment_id)
    if attachment["owner_id"] == actor.id:
        return attachment
    application_id = connection.scalar(
        select(m.applications.c.id).where(m.applications.c.attachment_id == attachment_id)
    )
    if application_id is None:
        raise forbidden()
    repo.get_application(connection, actor, application_id)
    return attachment


def submit(engine, settings: Settings, actor: Actor, body: Submit):
    if actor.role != Role.STUDENT:
        raise forbidden()
    reason = body.reason.strip()
    if len(reason) < 10:
        raise invalid("申请理由需填写10–1000字有效内容")
    with transaction(engine, write=True) as connection:
        enrollment = (
            connection.execute(
                select(m.enrollments)
                .where(m.enrollments.c.id == body.enrollment_id)
                .with_for_update()
            )
            .mappings()
            .first()
        )
        if enrollment is None:
            raise missing()
        if enrollment["student_id"] != actor.id:
            raise forbidden()
        offering = (
            connection.execute(
                select(m.offerings).where(m.offerings.c.id == enrollment["offering_id"])
            )
            .mappings()
            .one()
        )
        now = utcnow()
        if enrollment["score"] is not None:
            raise invalid("该课程已出分，不能申请缓考")
        if now >= offering["exam_at"]:
            raise invalid("已超过本课程的缓考申请截止时间")
        active = connection.scalar(
            select(func.count())
            .select_from(m.applications)
            .where(
                m.applications.c.enrollment_id == body.enrollment_id,
                m.applications.c.status != Status.REJECTED,
            )
        )
        if active:
            raise conflict("该课程已有有效缓考申请，请勿重复提交")
        attachment = get_attachment(connection, body.attachment_id, lock=True)
        if attachment["owner_id"] != actor.id:
            raise forbidden()
        if connection.scalar(
            select(m.applications.c.id).where(m.applications.c.attachment_id == body.attachment_id)
        ):
            raise conflict("该材料已用于其他申请，请重新上传")
        require_file(settings, attachment)
        result = connection.execute(
            m.applications.insert().values(
                enrollment_id=body.enrollment_id,
                attachment_id=body.attachment_id,
                reason=reason,
                status=Status.TEACHER_REVIEW,
                created_at=now,
                updated_at=now,
            )
        )
        application_id = result.inserted_primary_key[0]
        repo.notify(
            connection,
            actor.id,
            "缓考申请已提交",
            "申请已进入任课教师审核，请关注办理进度。",
            application_id,
            now,
        )
        repo.notify(
            connection,
            offering["teacher_id"],
            "新的缓考审核待办",
            f"{actor.display_name}提交了缓考申请，请及时处理。",
            application_id,
            now,
        )
        return repo.detail(connection, actor, application_id)


def review(engine, actor: Actor, application_id: int, body: Review):
    expected = repo.stage_for(actor)
    comment = body.comment.strip()
    if body.decision == Decision.REJECT and not comment:
        raise invalid("驳回时必须填写原因")
    with transaction(engine, write=True) as connection:
        # Lock only the application, then resolve joined permission context.
        connection.execute(
            select(m.applications.c.id)
            .where(m.applications.c.id == application_id)
            .with_for_update()
        ).first()
        row = repo.get_application(connection, actor, application_id)
        if row["status"] != expected:
            raise conflict("当前申请不在您的审核节点，请刷新列表")
        if body.decision == Decision.REJECT:
            next_status = Status.REJECTED
        else:
            next_status = {
                Status.TEACHER_REVIEW: Status.DEPARTMENT_REVIEW,
                Status.DEPARTMENT_REVIEW: Status.SCHOOL_REVIEW,
                Status.SCHOOL_REVIEW: Status.APPROVED,
            }[expected]
        now = utcnow()
        result = connection.execute(
            update(m.applications)
            .where(
                m.applications.c.id == application_id,
                m.applications.c.status == expected,
            )
            .values(status=next_status, updated_at=now)
        )
        if result.rowcount != 1:
            raise conflict("申请已被处理，请刷新后查看")
        connection.execute(
            m.approvals.insert().values(
                application_id=application_id,
                reviewer_id=actor.id,
                stage=expected,
                decision=body.decision,
                comment=comment,
                created_at=now,
            )
        )
        if next_status == Status.REJECTED:
            message = "申请已被驳回，请查看详情中的完整审核意见。"
        elif next_status == Status.APPROVED:
            message = "审核已全部通过，请等待缓考安排。"
        else:
            message = "本级审核已通过，已进入下一审核节点。"
        repo.notify(connection, row["student_id"], "缓考申请进度更新", message, application_id, now)
        if next_status in {Status.DEPARTMENT_REVIEW, Status.SCHOOL_REVIEW}:
            role = (
                Role.DEPARTMENT_ADMIN
                if next_status == Status.DEPARTMENT_REVIEW
                else Role.SCHOOL_ADMIN
            )
            condition = m.users.c.role == role
            if role == Role.DEPARTMENT_ADMIN:
                condition &= m.users.c.department_id == row["department_id"]
            for recipient in connection.scalars(select(m.users.c.id).where(condition)):
                repo.notify(
                    connection,
                    recipient,
                    "新的缓考审核待办",
                    f"申请 #{application_id}已流转到您的审核节点。",
                    application_id,
                    now,
                )
        return repo.detail(connection, actor, application_id)
