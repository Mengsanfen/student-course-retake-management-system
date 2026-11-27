from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update

from app import models as m
from app.database import transaction
from app.main import create_app
from app.manage import seed_demo, upgrade
from app.security import COOKIE_NAME, hash_token, utcnow

REASON = "因身体不适需就医，申请本门课程缓考并提交相关证明材料。"
PNG = bytes.fromhex("89504e470d0a1a0a") + b"test-only-fixture"


def csrf(client):
    result = client.get("/api/v1/auth/csrf")
    assert result.status_code == 200, result.text
    data = result.json()
    return {data["headerName"]: data["token"]}


def login(client, username="20240001", password="Demo@2026"):
    result = client.post(
        "/api/v1/auth/login",
        data={"username": username, "password": password},
        headers=csrf(client),
    )
    assert result.status_code == 200, result.text
    return client


def upload(client, name="proof.png", content=PNG):
    result = client.post(
        "/api/v1/attachments", files={"file": (name, content, "image/png")}, headers=csrf(client)
    )
    assert result.status_code == 201, result.text
    return result.json()["id"]


def submit(client, enrollment=1, attachment=None):
    if attachment is None:
        attachment = upload(client)
    return client.post(
        "/api/v1/deferrals",
        json={"enrollmentId": enrollment, "attachmentId": attachment, "reason": REASON},
        headers=csrf(client),
    )


def create(client):
    result = submit(client)
    assert result.status_code == 201, result.text
    assert result.headers["location"].endswith(str(result.json()["application"]["id"]))
    return result.json()["application"]["id"]


def review(client, application_id, decision="APPROVE", comment=""):
    return client.post(
        f"/api/v1/deferrals/{application_id}/reviews",
        json={"decision": decision, "comment": comment},
        headers=csrf(client),
    )


def count(engine, table):
    with transaction(engine) as connection:
        return connection.scalar(select(func.count()).select_from(table))


def test_anonymous_cannot_read_protected_data(client):
    for path in ("courses", "auth/me", "deferrals", "notifications"):
        assert client.get(f"/api/v1/{path}").status_code == 401


def test_real_login_rotates_cookie_and_csrf_and_logout_revokes(client):
    old_csrf = csrf(client)
    old_token = client.cookies[COOKIE_NAME]
    login(client)
    assert client.cookies[COOKIE_NAME] != old_token
    assert csrf(client) != old_csrf
    assert client.get("/api/v1/auth/me").json()["role"] == "STUDENT"
    cookie = client.cookies[COOKIE_NAME]
    result = client.post("/api/v1/auth/logout", headers=csrf(client))
    assert result.status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401
    client.cookies.set(COOKIE_NAME, cookie)
    assert client.get("/api/v1/auth/me").status_code == 401


@pytest.mark.parametrize("username,password", [("20240001", "wrong"), ("unknown", "wrong")])
def test_wrong_credentials_have_same_error(client, username, password):
    result = client.post(
        "/api/v1/auth/login",
        data={"username": username, "password": password},
        headers=csrf(client),
    )
    assert result.status_code == 401
    assert result.json() == {"code": "BAD_CREDENTIALS", "message": "账号或密码错误"}


def test_write_requires_csrf_including_login_and_upload(client):
    result = client.post(
        "/api/v1/auth/login", data={"username": "20240001", "password": "Demo@2026"}
    )
    assert result.status_code == 403
    login(client)
    assert client.post("/api/v1/deferrals", json={}).status_code == 403
    assert client.post("/api/v1/attachments", files={"file": ("proof.png", PNG)}).status_code == 403


def test_expired_session_cannot_read_or_write(client, system):
    login(client)
    headers = csrf(client)
    with transaction(system[1], write=True) as connection:
        connection.execute(update(m.sessions).values(expires_at=utcnow() - timedelta(seconds=1)))
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.post("/api/v1/deferrals", json={}, headers=headers).status_code == 403


def test_student_course_scope_and_no_sensitive_fields(client):
    login(client, "20240002")
    result = client.get("/api/v1/courses")
    assert result.status_code == 200
    assert [row["id"] for row in result.json()] == [5]
    assert result.json()[0]["examAt"].endswith("Z")
    assert "password" not in client.get("/api/v1/auth/me").text.lower()
    login(client, "teacher01")
    assert client.get("/api/v1/courses").status_code == 403


def test_three_stage_approval_history_and_notifications(client, system):
    login(client)
    application_id = create(client)
    login(client, "admin")
    assert review(client, application_id).status_code == 409
    for username, next_status in [
        ("teacher01", "DEPARTMENT_REVIEW"),
        ("dept01", "SCHOOL_REVIEW"),
        ("admin", "APPROVED"),
    ]:
        login(client, username)
        result = review(client, application_id, comment="材料核验通过")
        assert result.status_code == 200, result.text
        assert result.json()["application"]["status"] == next_status
        assert review(client, application_id).status_code == 409
    assert len(result.json()["approvals"]) == 3
    with transaction(system[1]) as connection:
        assert (
            connection.scalar(
                select(func.count())
                .select_from(m.notifications)
                .where(m.notifications.c.recipient_id == 1)
            )
            == 4
        )
        assert (
            connection.scalar(
                select(func.count())
                .select_from(m.notifications)
                .where(m.notifications.c.recipient_id == 21)
            )
            == 1
        )


@pytest.mark.parametrize("other", ["20240002", "teacher02", "dept02"])
def test_cross_student_teacher_department_denied(client, other):
    login(client)
    application_id = create(client)
    login(client, other)
    assert client.get(f"/api/v1/deferrals/{application_id}").status_code == 403
    assert review(client, application_id).status_code == 403
    assert client.get("/api/v1/deferrals").json()["total"] == 0


def test_student_cannot_review(client):
    login(client)
    assert review(client, create(client)).status_code == 403


def test_duplicate_active_application_is_rejected(client):
    login(client)
    create(client)
    assert submit(client).status_code == 409


def test_other_students_course_and_material_are_rejected(client):
    login(client, "20240002")
    other_material = upload(client)
    login(client)
    own_material = upload(client)
    assert submit(client, enrollment=5, attachment=own_material).status_code == 403
    assert submit(client, attachment=other_material).status_code == 403


def test_score_and_deadline_preconditions(client, system):
    login(client)
    assert submit(client, enrollment=4).status_code == 422
    with transaction(system[1], write=True) as connection:
        connection.execute(
            update(m.offerings)
            .where(m.offerings.c.id == 1)
            .values(exam_at=utcnow() - timedelta(seconds=1))
        )
    assert submit(client).status_code == 422


def test_rejection_requires_reason_and_allows_fresh_application(client):
    login(client)
    application_id = create(client)
    login(client, "teacher01")
    assert review(client, application_id, "REJECT", " ").status_code == 422
    result = review(client, application_id, "REJECT", "请补充清晰材料")
    assert result.status_code == 200
    assert result.json()["application"]["status"] == "REJECTED"
    login(client, "dept01")
    assert review(client, application_id).status_code == 409
    login(client)
    assert submit(client).status_code == 201


def test_material_privacy_download_headers_and_reuse(client):
    login(client)
    material = upload(client)
    login(client, "admin")
    assert client.get(f"/api/v1/attachments/{material}").status_code == 403
    login(client)
    assert submit(client, attachment=material).status_code == 201
    login(client, "teacher01")
    result = client.get(f"/api/v1/attachments/{material}")
    assert result.status_code == 200
    assert result.content == PNG
    assert result.headers["cache-control"] == "no-store"
    assert result.headers["x-content-type-options"] == "nosniff"
    assert result.headers["content-disposition"].startswith("attachment;")
    login(client, "20240002")
    assert client.get(f"/api/v1/attachments/{material}").status_code == 403
    login(client)
    assert submit(client, enrollment=2, attachment=material).status_code == 409


@pytest.mark.parametrize(
    "name,content", [("fake.pdf", b"<script>"), ("evil.exe", PNG), ("empty.png", b"")]
)
def test_invalid_files_rejected(client, name, content):
    login(client)
    result = client.post(
        "/api/v1/attachments", files={"file": (name, content)}, headers=csrf(client)
    )
    assert result.status_code == 422


def test_oversized_file_rejected_and_no_file_created(client, system):
    login(client)
    result = client.post(
        "/api/v1/attachments",
        files={"file": ("big.png", PNG + b"x" * (5 * 1024 * 1024))},
        headers=csrf(client),
    )
    assert result.status_code == 413
    assert count(system[1], m.attachments) == 0
    assert not list(system[2].upload_dir.glob("*"))


def test_chunked_upload_body_is_bounded(client, system):
    login(client)

    def body():
        for _ in range(7):
            yield b"x" * 1024 * 1024

    result = client.post(
        "/api/v1/attachments",
        content=body(),
        headers={
            **csrf(client),
            "Content-Type": "multipart/form-data; boundary=test",
            "Transfer-Encoding": "chunked",
        },
    )
    assert result.status_code == 413
    assert count(system[1], m.attachments) == 0


def test_filename_path_is_removed(client, system):
    login(client)
    material = upload(client, "../../proof.png")
    with transaction(system[1]) as connection:
        row = (
            connection.execute(select(m.attachments).where(m.attachments.c.id == material))
            .mappings()
            .one()
        )
    assert row["original_name"] == "proof.png"
    assert "/" not in row["storage_name"]
    assert (system[2].upload_dir / row["storage_name"]).exists()


def test_missing_material_file_cannot_be_submitted(client, system):
    login(client)
    material = upload(client)
    for path in system[2].upload_dir.iterdir():
        path.unlink()
    assert submit(client, attachment=material).status_code == 422
    assert count(system[1], m.applications) == 0


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"enrollmentId": 1, "attachmentId": 1, "reason": "短"},
        {"enrollmentId": -1, "attachmentId": 1, "reason": REASON},
    ],
)
def test_bad_payloads_return_consistent_error(client, body):
    login(client)
    result = client.post("/api/v1/deferrals", json=body, headers=csrf(client))
    assert result.status_code == 400
    assert result.json()["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("query", ["size=101", "page=0", "page=100001", "page=abc"])
def test_invalid_pagination_rejected(client, query):
    login(client)
    assert client.get("/api/v1/deferrals?" + query).status_code == 400


def test_notices_are_private_and_read_is_idempotent(client, system):
    login(client)
    create(client)
    notices = client.get("/api/v1/notifications").json()
    notice_id = notices["items"][0]["id"]
    login(client, "20240002")
    assert client.get("/api/v1/notifications").json()["total"] == 0
    assert (
        client.post(f"/api/v1/notifications/{notice_id}/read", headers=csrf(client)).status_code
        == 404
    )
    login(client)
    for _ in range(2):
        assert (
            client.post(f"/api/v1/notifications/{notice_id}/read", headers=csrf(client)).status_code
            == 204
        )
    assert client.get("/api/v1/notifications").json()["items"][0]["isRead"] is True


def test_pending_lists_follow_role_node(client):
    login(client)
    application_id = create(client)
    login(client, "dept01")
    assert client.get("/api/v1/deferrals?pendingOnly=true").json()["total"] == 0
    login(client, "teacher01")
    assert client.get("/api/v1/deferrals?pendingOnly=true").json()["total"] == 1
    assert review(client, application_id).status_code == 200
    login(client, "dept01")
    assert client.get("/api/v1/deferrals?pendingOnly=true").json()["total"] == 1


def test_maximum_rejection_comment_is_preserved(client):
    login(client)
    application_id = create(client)
    login(client, "teacher01")
    comment = "补" * 500
    result = review(client, application_id, "REJECT", comment)
    assert result.status_code == 200
    assert result.json()["approvals"][0]["comment"] == comment


def test_transaction_rolls_back_status_history_and_notifications(client, system, monkeypatch):
    from app import repository

    login(client)
    application_id = create(client)
    login(client, "teacher01")

    def broken(*args, **kwargs):
        raise RuntimeError("simulated notification failure")

    monkeypatch.setattr(repository, "notify", broken)
    with TestClient(system[0], raise_server_exceptions=False) as fault_client:
        fault_client.cookies.update(client.cookies)
        result = review(fault_client, application_id)
    assert result.status_code == 500
    assert "simulated" not in result.text
    with transaction(system[1]) as connection:
        assert (
            connection.scalar(
                select(m.applications.c.status).where(m.applications.c.id == application_id)
            )
            == "TEACHER_REVIEW"
        )
    assert count(system[1], m.approvals) == 0
    assert count(system[1], m.notifications) == 2


def test_concurrent_submissions_only_one_succeeds(system):
    barrier = Barrier(2)

    def run():
        with TestClient(system[0]) as client:
            login(client)
            material = upload(client)
            headers = csrf(client)
            barrier.wait(timeout=15)
            return client.post(
                "/api/v1/deferrals",
                json={"enrollmentId": 1, "attachmentId": material, "reason": REASON},
                headers=headers,
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run) for _ in range(2)]
        assert sorted(f.result(timeout=30) for f in futures) == [201, 409]
    assert count(system[1], m.applications) == 1


def test_concurrent_reviews_only_one_succeeds(client, system):
    login(client)
    application_id = create(client)
    barrier = Barrier(2)

    def run():
        with TestClient(system[0]) as reviewer:
            login(reviewer, "teacher01")
            headers = csrf(reviewer)
            barrier.wait(timeout=15)
            return reviewer.post(
                f"/api/v1/deferrals/{application_id}/reviews",
                json={"decision": "APPROVE", "comment": "通过"},
                headers=headers,
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run) for _ in range(2)]
        assert sorted(f.result(timeout=30) for f in futures) == [200, 409]
    assert count(system[1], m.approvals) == 1


def test_database_and_sessions_survive_application_recreation(client, system):
    login(client)
    application_id = create(client)
    with TestClient(create_app(system[2], engine=system[1])) as recreated:
        recreated.cookies.update(client.cookies)
        assert recreated.get(f"/api/v1/deferrals/{application_id}").status_code == 200


def test_migration_is_repeatable_and_matches_metadata(system):
    upgrade(system[1])
    with system[1].connect() as connection:
        context = MigrationContext.configure(connection, opts={"compare_type": True})
        assert compare_metadata(context, m.metadata) == []


def test_seed_requires_demo_mode_and_does_not_duplicate(system, changed_settings):
    with pytest.raises(RuntimeError):
        seed_demo(system[1], changed_settings(demo_mode=False))
    seed_demo(system[1], system[2])
    assert count(system[1], m.users) == 8


def test_openapi_and_health_identify_fastapi(client):
    schema = client.get("/openapi.json").json()
    assert schema["info"]["version"] == "0.2.0"
    assert "enrollmentId" in schema["components"]["schemas"]["Submit"]["properties"]
    parameters = schema["paths"]["/api/v1/deferrals"]["post"]["parameters"]
    assert any(p["name"] == "X-CSRF-TOKEN" and p["required"] for p in parameters)
    assert client.get("/api/v1/health").json()["backend"] == "FastAPI"


def test_cookies_are_http_only_same_site(client):
    result = client.get("/api/v1/auth/csrf")
    cookie = result.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie


def test_database_failure_during_csrf_returns_503_without_mutation(client, system, monkeypatch):
    from sqlalchemy.exc import OperationalError

    from app import security

    login(client)
    headers = csrf(client)

    def broken(*args, **kwargs):
        raise OperationalError("SELECT secret_session", {}, RuntimeError("database offline"))

    monkeypatch.setattr(security, "load_session", broken)
    result = client.post("/api/v1/deferrals", json={}, headers=headers)
    assert result.status_code == 503
    assert result.json()["code"] == "SERVICE_UNAVAILABLE"
    assert "secret_session" not in result.text
    assert count(system[1], m.applications) == 0


def test_authenticated_session_is_stored_as_hash(client, system):
    login(client)
    token = client.cookies[COOKIE_NAME]
    with transaction(system[1]) as connection:
        hashes = connection.scalars(select(m.sessions.c.token_hash)).all()
    assert token not in hashes
    assert hash_token(token) in hashes
