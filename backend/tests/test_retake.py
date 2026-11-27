from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update

from app import models as m
from app.database import transaction
from app.retake_schemas import TimeSlot
from app.retake_service import overlap
from tests.test_workflow import csrf, login

REASON = "本门课程原成绩未达及格标准，现申请参加本学期重修学习。"


def meta(client):
    result = client.get("/api/v1/retake-meta")
    assert result.status_code == 200, result.text
    return result.json()


def apply(client, enrollment=4, term=None):
    term = term or meta(client)["terms"][0]["id"]
    return client.post(
        "/api/v1/retakes",
        json={"enrollmentId": enrollment, "termId": term, "reason": REASON},
        headers=csrf(client),
    )


def create_application(client, enrollment=4):
    result = apply(client, enrollment)
    assert result.status_code == 201, result.text
    return result.json()["application"]["id"]


def review(client, application_id, decision="APPROVE", comment=""):
    return client.post(
        f"/api/v1/retakes/{application_id}/reviews",
        json={"decision": decision, "comment": comment},
        headers=csrf(client),
    )


def approved(client, username="20240001", enrollment=4):
    login(client, username)
    application_id = create_application(client, enrollment)
    for account in ("dept01", "admin"):
        login(client, account)
        result = review(client, application_id)
        assert result.status_code == 200, result.text
    login(client, username)
    return application_id


def classes(client):
    result = client.get("/api/v1/retake-classes?size=100")
    assert result.status_code == 200, result.text
    return result.json()["items"]


def class_on(client, weekday):
    return next(row for row in classes(client) if row["slots"][0]["weekday"] == weekday)


def enroll(client, application_id, class_id):
    return client.post(
        "/api/v1/retake-enrollments",
        json={"applicationId": application_id, "classId": class_id},
        headers=csrf(client),
    )


def check(client, application_id, class_id):
    return client.post(
        f"/api/v1/retake-classes/{class_id}/conflict-check",
        json={"applicationId": application_id},
        headers=csrf(client),
    )


def class_body(client, **updates):
    body = {
        "name": "程序设计基础 · 新开班",
        "courseId": 4,
        "termId": meta(client)["terms"][0]["id"],
        "teacherId": 11,
        "capacity": 20,
        "room": "C301",
        "slots": [{"startWeek": 1, "endWeek": 16, "weekday": 2, "startPeriod": 7, "endPeriod": 8}],
    }
    body.update(updates)
    return body


def create_class(client, **updates):
    return client.post(
        "/api/v1/retake-classes", json=class_body(client, **updates), headers=csrf(client)
    )


def test_meta_only_offers_failed_owned_courses(client):
    login(client)
    data = meta(client)
    assert [row["id"] for row in data["eligibleCourses"]] == [4]
    assert data["courses"] == [] and data["teachers"] == []
    login(client, "admin")
    assert len(meta(client)["teachers"]) == 2


def test_two_stage_review_and_notice_links(client):
    login(client)
    application_id = create_application(client)
    assert (
        client.get(f"/api/v1/retakes/{application_id}").json()["application"]["status"]
        == "DEPARTMENT_REVIEW"
    )
    notices = client.get("/api/v1/notifications").json()["items"]
    assert (
        notices[0]["retakeApplicationId"] == application_id and notices[0]["applicationId"] is None
    )
    login(client, "admin")
    assert review(client, application_id).status_code == 409
    login(client, "dept01")
    result = review(client, application_id, comment="资格符合")
    assert result.status_code == 200 and result.json()["application"]["status"] == "SCHOOL_REVIEW"
    assert review(client, application_id).status_code == 409
    login(client, "admin")
    result = review(client, application_id)
    assert result.json()["application"]["status"] == "APPROVED"
    assert len(result.json()["approvals"]) == 2


@pytest.mark.parametrize("other", ["20240002", "teacher01", "dept02"])
def test_retake_scope_and_unauthorized_reviews(client, other):
    login(client)
    application_id = create_application(client)
    login(client, other)
    assert client.get(f"/api/v1/retakes/{application_id}").status_code == 403
    assert review(client, application_id).status_code == 403
    assert client.get("/api/v1/retakes").json()["total"] == 0


@pytest.mark.parametrize("score", [None, 60, 100])
def test_nonfailed_courses_cannot_apply(client, system, score):
    login(client)
    with transaction(system[1], write=True) as connection:
        connection.execute(update(m.enrollments).where(m.enrollments.c.id == 4).values(score=score))
    assert apply(client).status_code == 422


def test_other_student_and_invalid_term_rejected(client):
    login(client, "20240002")
    assert apply(client, 4).status_code == 403
    login(client)
    assert apply(client, term=999999).status_code == 422


def test_duplicate_active_and_rejection_resubmission(client):
    login(client)
    application_id = create_application(client)
    assert apply(client).status_code == 409
    login(client, "dept01")
    assert review(client, application_id, "REJECT", " ").status_code == 422
    assert review(client, application_id, "REJECT", "请核对重修学期").status_code == 200
    login(client)
    assert apply(client).status_code == 201


def test_student_and_teacher_cannot_create_or_update_classes(client):
    for username in ("20240001", "teacher01", "dept01"):
        login(client, username)
        body = {
            "name": "非法开班",
            "courseId": 4,
            "termId": meta(client)["terms"][0]["id"],
            "teacherId": 11,
            "capacity": 20,
            "room": "X1",
            "slots": [
                {"startWeek": 1, "endWeek": 2, "weekday": 2, "startPeriod": 1, "endPeriod": 2}
            ],
        }
        assert (
            client.post("/api/v1/retake-classes", json=body, headers=csrf(client)).status_code
            == 403
        )
        assert (
            client.patch(
                "/api/v1/retake-classes/1",
                json={"status": "CLOSED", "capacity": 10},
                headers=csrf(client),
            ).status_code
            == 403
        )


def test_school_can_create_class_and_teacher_only_sees_own(client):
    login(client, "admin")
    result = create_class(client)
    assert result.status_code == 201, result.text
    class_id = result.json()["id"]
    assert result.json()["enrolledCount"] == 0 and len(result.json()["slots"]) == 1
    login(client, "teacher01")
    assert class_id in [row["id"] for row in classes(client)]
    login(client, "teacher02")
    assert class_id not in [row["id"] for row in classes(client)]


@pytest.mark.parametrize(
    "slot",
    [
        {"startWeek": 3, "endWeek": 2, "weekday": 2, "startPeriod": 1, "endPeriod": 2},
        {"startWeek": 1, "endWeek": 16, "weekday": 8, "startPeriod": 1, "endPeriod": 2},
        {"startWeek": 1, "endWeek": 16, "weekday": 2, "startPeriod": 3, "endPeriod": 2},
    ],
)
def test_invalid_time_ranges_return_400(client, slot):
    login(client, "admin")
    assert create_class(client, slots=[slot]).status_code == 400


def test_term_week_limit_internal_overlap_and_invalid_teacher(client):
    login(client, "admin")
    body = class_body(client)
    slot = dict(body["slots"][0], endWeek=25)
    assert create_class(client, slots=[slot]).status_code == 422
    assert create_class(client, slots=body["slots"] * 2).status_code == 422
    assert create_class(client, teacherId=1).status_code == 422
    assert create_class(client, courseId=999999).status_code == 422


def test_teacher_and_room_conflicts_block_opening(client):
    login(client, "admin")
    monday = {"startWeek": 1, "endWeek": 16, "weekday": 1, "startPeriod": 1, "endPeriod": 2}
    assert create_class(client, teacherId=11, room="C399", slots=[monday]).status_code == 409
    assert create_class(client, teacherId=12, room="A101", slots=[monday]).status_code == 409


def test_regular_conflict_explains_and_offers_alternatives(client):
    application_id = approved(client)
    result = check(client, application_id, class_on(client, 1)["id"])
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["allowed"] is False
    assert body["conflicts"][0]["source"] == "REGULAR"
    assert body["conflicts"][0]["courseName"] == "数据结构"
    assert "周一" in body["conflicts"][0]["explanation"]
    assert any(row["slots"][0]["weekday"] == 6 for row in body["alternatives"])
    assert enroll(client, application_id, class_on(client, 1)["id"]).status_code == 409


def test_approved_enrollment_roster_timetable_and_duplicate(client):
    application_id = approved(client)
    target = class_on(client, 6)
    assert check(client, application_id, target["id"]).json()["allowed"] is True
    result = enroll(client, application_id, target["id"])
    assert result.status_code == 201, result.text
    assert result.json()["application"]["status"] == "ENROLLED"
    assert result.json()["application"]["classId"] == target["id"]
    assert enroll(client, application_id, target["id"]).status_code == 409
    term_id = target["termId"]
    assert len(client.get(f"/api/v1/timetable?termId={term_id}").json()) == 4
    assert client.get(f"/api/v1/retake-classes/{target['id']}/students").status_code == 403
    login(client, "teacher01")
    assert len(client.get(f"/api/v1/retake-classes/{target['id']}/students").json()) == 1
    assert client.get(f"/api/v1/retakes/{application_id}").status_code == 200
    login(client, "teacher02")
    assert client.get(f"/api/v1/retake-classes/{target['id']}/students").status_code == 403
    login(client, "dept02")
    assert client.get(f"/api/v1/retake-classes/{target['id']}/students").json() == []


def test_pending_application_cannot_enroll_or_use_other_students_application(client):
    login(client)
    application_id = create_application(client)
    target = class_on(client, 6)
    assert enroll(client, application_id, target["id"]).status_code == 409
    login(client, "20240002")
    assert enroll(client, application_id, target["id"]).status_code == 403
    assert check(client, application_id, target["id"]).status_code == 403


def test_wrong_course_or_term_class_cannot_be_selected(client):
    application_id = approved(client)
    login(client, "admin")
    result = create_class(client, courseId=2)
    assert result.status_code == 201
    login(client)
    assert enroll(client, application_id, result.json()["id"]).status_code == 422


def test_close_reopen_and_capacity_never_below_enrolled(client):
    application_id = approved(client)
    target = class_on(client, 6)
    login(client, "admin")
    path = f"/api/v1/retake-classes/{target['id']}"
    assert (
        client.patch(
            path, json={"status": "CLOSED", "capacity": 20}, headers=csrf(client)
        ).status_code
        == 200
    )
    login(client)
    assert enroll(client, application_id, target["id"]).status_code == 409
    login(client, "admin")
    assert (
        client.patch(path, json={"status": "OPEN", "capacity": 1}, headers=csrf(client)).status_code
        == 200
    )
    login(client)
    assert enroll(client, application_id, target["id"]).status_code == 201
    login(client, "admin")
    assert (
        client.patch(
            path, json={"status": "CLOSED", "capacity": 0}, headers=csrf(client)
        ).status_code
        == 400
    )
    assert len(client.get(f"/api/v1/retake-classes/{target['id']}/students").json()) == 1


def test_concurrent_last_seat_cannot_overfill(system, client):
    with transaction(system[1], write=True) as connection:
        connection.execute(
            m.enrollments.insert().values(id=7, student_id=2, offering_id=4, score=40)
        )
    first = approved(client)
    second = approved(client, "20240002", 7)
    target = class_on(client, 7)
    barrier = Barrier(2)

    def run(username, application_id):
        with TestClient(system[0]) as participant:
            login(participant, username)
            headers = csrf(participant)
            barrier.wait(timeout=15)
            return participant.post(
                "/api/v1/retake-enrollments",
                json={"applicationId": application_id, "classId": target["id"]},
                headers=headers,
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run, "20240001", first), pool.submit(run, "20240002", second)]
        assert sorted(f.result(timeout=30) for f in futures) == [201, 409]
    with transaction(system[1]) as connection:
        assert connection.scalar(select(func.count()).select_from(m.retake_enrollments)) == 1


def test_concurrent_same_student_conflicting_classes_cannot_bypass_check(system, client):
    with transaction(system[1], write=True) as connection:
        connection.execute(update(m.enrollments).where(m.enrollments.c.id == 2).values(score=40))
    first = approved(client)
    second = approved(client, enrollment=2)
    target = class_on(client, 7)
    login(client, "admin")
    result = create_class(
        client,
        name="数据库原理 · 周日班",
        courseId=2,
        teacherId=11,
        slots=target["slots"],
        room="C499",
    )
    assert result.status_code == 201, result.text
    other_class = result.json()["id"]
    barrier = Barrier(2)

    def run(application_id, class_id):
        with TestClient(system[0]) as participant:
            login(participant)
            headers = csrf(participant)
            barrier.wait(timeout=15)
            return participant.post(
                "/api/v1/retake-enrollments",
                json={"applicationId": application_id, "classId": class_id},
                headers=headers,
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run, first, target["id"]), pool.submit(run, second, other_class)]
        assert sorted(f.result(timeout=30) for f in futures) == [201, 409]
    with transaction(system[1]) as connection:
        assert connection.scalar(select(func.count()).select_from(m.retake_enrollments)) == 1


def test_enrollment_notification_failure_rolls_back(system, client, monkeypatch):
    from app import retake_repository

    application_id = approved(client)
    target = class_on(client, 6)

    def broken(*args, **kwargs):
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(retake_repository, "notify", broken)
    with TestClient(system[0], raise_server_exceptions=False) as fault_client:
        fault_client.cookies.update(client.cookies)
        assert enroll(fault_client, application_id, target["id"]).status_code == 500
    assert (
        client.get(f"/api/v1/retakes/{application_id}").json()["application"]["status"]
        == "APPROVED"
    )
    with transaction(system[1]) as connection:
        assert connection.scalar(select(func.count()).select_from(m.retake_enrollments)) == 0


@pytest.mark.parametrize(
    "changes,expected",
    [
        ({"weekday": 2}, False),
        ({"start_week": 17, "end_week": 20}, False),
        ({"start_period": 3, "end_period": 4}, False),
        ({"start_period": 2, "end_period": 3}, True),
        ({"start_week": 16, "end_week": 20}, True),
        ({}, True),
    ],
)
def test_overlap_boundaries(changes, expected):
    original = TimeSlot(start_week=1, end_week=16, weekday=1, start_period=1, end_period=2)
    other = TimeSlot.model_validate({**original.model_dump(), **changes})
    assert overlap(original, other) is expected


def test_concurrent_retake_submissions_only_one_active(system):
    barrier = Barrier(2)

    def run():
        with TestClient(system[0]) as client:
            login(client)
            term_id = meta(client)["terms"][0]["id"]
            headers = csrf(client)
            barrier.wait(timeout=15)
            return client.post(
                "/api/v1/retakes",
                json={"enrollmentId": 4, "termId": term_id, "reason": REASON},
                headers=headers,
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run) for _ in range(2)]
        assert sorted(f.result(timeout=30) for f in futures) == [201, 409]
    with transaction(system[1]) as connection:
        assert connection.scalar(select(func.count()).select_from(m.retakes)) == 1


def test_concurrent_retake_reviews_only_one_history(system, client):
    login(client)
    application_id = create_application(client)
    barrier = Barrier(2)

    def run():
        with TestClient(system[0]) as reviewer:
            login(reviewer, "dept01")
            headers = csrf(reviewer)
            barrier.wait(timeout=15)
            return reviewer.post(
                f"/api/v1/retakes/{application_id}/reviews",
                json={"decision": "APPROVE", "comment": "通过"},
                headers=headers,
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run) for _ in range(2)]
        assert sorted(f.result(timeout=30) for f in futures) == [200, 409]
    with transaction(system[1]) as connection:
        assert connection.scalar(select(func.count()).select_from(m.retake_approvals)) == 1


def test_capacity_cannot_shrink_below_two_enrolled_students(system, client):
    with transaction(system[1], write=True) as connection:
        connection.execute(
            m.enrollments.insert().values(id=7, student_id=2, offering_id=4, score=45)
        )
    first = approved(client)
    target = class_on(client, 6)
    assert enroll(client, first, target["id"]).status_code == 201
    second = approved(client, "20240002", 7)
    assert enroll(client, second, target["id"]).status_code == 201
    login(client, "admin")
    path = f"/api/v1/retake-classes/{target['id']}"
    assert (
        client.patch(path, json={"capacity": 1, "status": "OPEN"}, headers=csrf(client)).status_code
        == 422
    )
    assert (
        client.patch(
            path, json={"capacity": 2, "status": "CLOSED"}, headers=csrf(client)
        ).status_code
        == 200
    )
    assert len(client.get(path + "/students").json()) == 2
    login(client)
    assert len(client.get(f"/api/v1/timetable?termId={target['termId']}").json()) == 4


def test_conflict_result_identifies_an_existing_retake(system, client):
    with transaction(system[1], write=True) as connection:
        connection.execute(update(m.enrollments).where(m.enrollments.c.id == 2).values(score=40))
    first = approved(client)
    target = class_on(client, 7)
    assert enroll(client, first, target["id"]).status_code == 201
    second = approved(client, enrollment=2)
    login(client, "admin")
    result = create_class(
        client,
        name="数据库原理 · 冲突验证",
        courseId=2,
        teacherId=11,
        room="C499",
        slots=target["slots"],
    )
    assert result.status_code == 201
    login(client)
    result = check(client, second, result.json()["id"])
    assert result.status_code == 200
    assert result.json()["allowed"] is False
    assert result.json()["conflicts"][0]["source"] == "RETAKE"


def test_class_in_another_term_cannot_be_selected(system, client):
    application_id = approved(client)
    with transaction(system[1], write=True) as connection:
        term = connection.execute(
            m.academic_terms.insert().values(name="下一学期", week_count=20)
        ).inserted_primary_key[0]
    login(client, "admin")
    result = create_class(client, termId=term)
    assert result.status_code == 201
    login(client)
    assert enroll(client, application_id, result.json()["id"]).status_code == 422
