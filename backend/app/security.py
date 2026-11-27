import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta

import bcrypt
from fastapi import Request, Response
from sqlalchemy import Engine, delete, select
from sqlalchemy.exc import OperationalError
from starlette.responses import JSONResponse

from app import models as m
from app.config import Settings
from app.database import transaction
from app.errors import BusinessError
from app.schemas import Actor

COOKIE_NAME = "retake_session"
CSRF_HEADER = "X-CSRF-TOKEN"
log = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(UTC)


def hash_token(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def hash_password(value: str) -> str:
    return bcrypt.hashpw(value.encode(), bcrypt.gensalt()).decode()


def verify_password(value: str, password_hash: str) -> bool:
    # bcrypt accepts at most 72 bytes; reject rather than truncate a password.
    if len(value.encode()) > 72:
        return False
    try:
        return bcrypt.checkpw(value.encode(), password_hash.encode())
    except ValueError:
        return False


# Unknown usernames still perform a password hash check.
DUMMY_HASH = hash_password(secrets.token_urlsafe(24))


def load_session(engine: Engine, token: str | None):
    if not token or len(token) > 100:
        return None
    with transaction(engine) as connection:
        return (
            connection.execute(
                select(m.sessions).where(
                    m.sessions.c.token_hash == hash_token(token), m.sessions.c.expires_at > utcnow()
                )
            )
            .mappings()
            .first()
        )


def new_session(connection, settings: Settings, user_id: int | None = None):
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    connection.execute(
        m.sessions.insert().values(
            token_hash=hash_token(token),
            user_id=user_id,
            csrf_token=csrf,
            expires_at=utcnow() + timedelta(minutes=settings.session_minutes),
        )
    )
    return token, csrf


def set_cookie(response: Response, token: str, settings: Settings):
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=settings.session_minutes * 60,
        path="/",
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )


def require_actor(request: Request) -> Actor:
    session = load_session(request.app.state.engine, request.cookies.get(COOKIE_NAME))
    if session is None or session["user_id"] is None:
        raise BusinessError(401, "UNAUTHENTICATED", "请先登录")
    with transaction(request.app.state.engine) as connection:
        row = (
            connection.execute(
                select(
                    m.users.c.id,
                    m.users.c.username,
                    m.users.c.display_name,
                    m.users.c.role,
                    m.users.c.department_id,
                    m.departments.c.name.label("department_name"),
                )
                .join(m.departments)
                .where(m.users.c.id == session["user_id"])
            )
            .mappings()
            .first()
        )
    if row is None:
        raise BusinessError(401, "UNAUTHENTICATED", "请先登录")
    return Actor.model_validate(row)


class SecurityMiddleware:
    """CSRF before parsing request bodies; sessions remain revocable on the server."""

    def __init__(self, app, engine: Engine, settings: Settings):
        self.app, self.engine, self.settings = app, engine, settings

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        request = Request(scope)

        async def send_secure(message):
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                headers.extend(
                    [
                        (b"x-content-type-options", b"nosniff"),
                        (b"x-frame-options", b"DENY"),
                        (b"referrer-policy", b"same-origin"),
                        (b"cache-control", b"no-store"),
                    ]
                )
            await send(message)

        if request.method not in {"GET", "HEAD", "OPTIONS"} and request.url.path.startswith(
            "/api/"
        ):
            # Keep the synchronous database driver outside the ASGI event loop.
            from starlette.concurrency import run_in_threadpool

            try:
                session = await run_in_threadpool(
                    load_session, self.engine, request.cookies.get(COOKIE_NAME)
                )
            except OperationalError:
                log.exception("Session database temporarily unavailable")
                return await JSONResponse(
                    status_code=503,
                    content={
                        "code": "SERVICE_UNAVAILABLE",
                        "message": "数据库暂不可用，请稍后重试",
                    },
                )(scope, receive, send_secure)
            token = request.headers.get(CSRF_HEADER, "")
            if session is None or not secrets.compare_digest(
                token.encode(), session["csrf_token"].encode()
            ):
                return await JSONResponse(
                    status_code=403,
                    content={"code": "FORBIDDEN", "message": "安全令牌已失效，请刷新重试"},
                )(scope, receive, send_secure)

        if request.url.path == "/api/v1/attachments" and request.method == "POST":
            limit = self.settings.max_upload_bytes + 1024 * 1024
            try:
                length = int(request.headers.get("content-length", "0"))
            except ValueError:
                length = -1
            if length < 0:
                return await JSONResponse(
                    status_code=400,
                    content={
                        "code": "INVALID_REQUEST",
                        "message": "请求长度不正确",
                    },
                )(scope, receive, send_secure)
            if length > limit:
                return await JSONResponse(
                    status_code=413,
                    content={
                        "code": "FILE_TOO_LARGE",
                        "message": "文件不得超过5 MiB",
                    },
                )(scope, receive, send_secure)
            # Bound chunked bodies too, before multipart parsing can spool them to disk.
            chunks, count = [], 0
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                count += len(message.get("body", b""))
                if count > limit:
                    return await JSONResponse(
                        status_code=413,
                        content={
                            "code": "FILE_TOO_LARGE",
                            "message": "文件不得超过5 MiB",
                        },
                    )(scope, receive, send_secure)
                chunks.append(message)
                if not message.get("more_body", False):
                    break
            iterator = iter(chunks)

            async def replay():
                return next(iterator, {"type": "http.request", "body": b"", "more_body": False})

            return await self.app(scope, replay, send_secure)
        await self.app(scope, receive, send_secure)


def delete_expired_sessions(connection):
    connection.execute(delete(m.sessions).where(m.sessions.c.expires_at <= utcnow()))
