import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, File, Form, Header, Query, Request, Response, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import Engine, delete, select, text, update
from sqlalchemy.exc import IntegrityError, OperationalError
from starlette.exceptions import HTTPException

from app import models as m
from app import repository as repo
from app import services
from app.config import Settings
from app.database import make_engine, transaction
from app.errors import BusinessError, missing
from app.schemas import (
    Actor,
    ApiError,
    Application,
    AttachmentResult,
    Course,
    Detail,
    Notice,
    Page,
    Review,
    Submit,
)
from app.security import (
    COOKIE_NAME,
    CSRF_HEADER,
    DUMMY_HASH,
    SecurityMiddleware,
    delete_expired_sessions,
    hash_token,
    load_session,
    new_session,
    require_actor,
    set_cookie,
    verify_password,
)

log = logging.getLogger(__name__)
ActorDependency = Annotated[Actor, Depends(require_actor)]
PageNumber = Annotated[int, Query(ge=1, le=100000)]
PageSize = Annotated[int, Query(ge=1, le=100)]


def csrf_documentation(token: Annotated[str, Header(alias=CSRF_HEADER)]):
    """Validation is performed before body parsing in SecurityMiddleware."""


WRITE = [Depends(csrf_documentation)]


def create_app(settings: Settings | None = None, *, engine: Engine | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    owns_engine = engine is None
    engine = engine or make_engine(settings.database_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        if owns_engine:
            engine.dispose()

    app = FastAPI(
        title="高校学生课程缓考与重修管理系统",
        version="0.3.0",
        lifespan=lifespan,
        description="M1缓考闭环；M2重修申请、双级审核、开班选课、课表及冲突检测。时间为UTC，字段camelCase。",
        responses={
            code: {"model": ApiError} for code in (400, 401, 403, 404, 409, 413, 422, 500, 503)
        },
    )
    app.state.engine, app.state.settings = engine, settings
    app.add_middleware(SecurityMiddleware, engine=engine, settings=settings)

    @app.exception_handler(BusinessError)
    async def business_error(request, error):
        return JSONResponse(
            status_code=error.status, content={"code": error.code, "message": error.message}
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        fields = ", ".join(str(item["loc"][-1]) for item in error.errors()[:4])
        return JSONResponse(
            status_code=400,
            content={
                "code": "VALIDATION_ERROR",
                "message": f"请求字段不正确：{fields}",
            },
        )

    @app.exception_handler(IntegrityError)
    async def integrity_error(request, error):
        return JSONResponse(
            status_code=409,
            content={
                "code": "DATA_CONFLICT",
                "message": "数据已变更或重复，请刷新后重试",
            },
        )

    @app.exception_handler(OperationalError)
    async def database_unavailable(request, error):
        log.error("Database operation failed", exc_info=error)
        return JSONResponse(
            status_code=503,
            content={
                "code": "SERVICE_UNAVAILABLE",
                "message": "数据库暂不可用，请稍后重试",
            },
        )

    @app.exception_handler(HTTPException)
    async def http_error(request, error):
        return JSONResponse(
            status_code=error.status_code,
            content={
                "code": "INVALID_REQUEST",
                "message": "请求格式不正确或资源不存在",
            },
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request, error):
        log.error("Unexpected API error", exc_info=error)
        return JSONResponse(
            status_code=500,
            content={
                "code": "INTERNAL_ERROR",
                "message": "服务暂不可用，请稍后重试",
            },
        )

    @app.get("/api/v1/health", tags=["系统"])
    def health():
        with transaction(engine) as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "UP", "version": "0.3.0", "backend": "FastAPI"}

    @app.get("/api/v1/auth/csrf", tags=["认证"])
    def csrf(request: Request, response: Response):
        session = load_session(engine, request.cookies.get(COOKIE_NAME))
        if session is not None:
            return {"token": session["csrf_token"], "headerName": CSRF_HEADER}
        with transaction(engine, write=True) as connection:
            delete_expired_sessions(connection)
            token, csrf_token = new_session(connection, settings)
        set_cookie(response, token, settings)
        return {"token": csrf_token, "headerName": CSRF_HEADER}

    @app.post("/api/v1/auth/login", tags=["认证"], dependencies=WRITE)
    def login(
        request: Request,
        response: Response,
        username: Annotated[str, Form(min_length=1, max_length=50)],
        password: Annotated[str, Form(min_length=1, max_length=128)],
    ):
        with transaction(engine) as connection:
            account = (
                connection.execute(select(m.users).where(m.users.c.username == username))
                .mappings()
                .first()
            )
        valid = verify_password(password, account["password_hash"] if account else DUMMY_HASH)
        if account is None or not valid:
            raise BusinessError(401, "BAD_CREDENTIALS", "账号或密码错误")
        with transaction(engine, write=True) as connection:
            # Recheck under the write transaction: a concurrent logout/login cannot revive a session.
            old_hash = hash_token(request.cookies.get(COOKIE_NAME, ""))
            old = (
                connection.execute(
                    select(m.sessions).where(m.sessions.c.token_hash == old_hash).with_for_update()
                )
                .mappings()
                .first()
            )
            from app.security import utcnow

            if old is None or old["expires_at"] <= utcnow():
                raise BusinessError(403, "FORBIDDEN", "安全令牌已失效，请刷新重试")
            connection.execute(delete(m.sessions).where(m.sessions.c.token_hash == old_hash))
            token, _ = new_session(connection, settings, account["id"])
        set_cookie(response, token, settings)
        return {"code": "OK", "message": "登录成功"}

    @app.get("/api/v1/auth/me", response_model=Actor, tags=["认证"])
    def me(actor: ActorDependency):
        return actor

    @app.post("/api/v1/auth/logout", tags=["认证"], dependencies=WRITE)
    def logout(request: Request, response: Response, actor: ActorDependency):
        with transaction(engine, write=True) as connection:
            connection.execute(
                delete(m.sessions).where(
                    m.sessions.c.token_hash == hash_token(request.cookies.get(COOKIE_NAME, ""))
                )
            )
        response.delete_cookie(
            COOKIE_NAME, path="/", secure=settings.cookie_secure, httponly=True, samesite="lax"
        )
        return {"code": "OK", "message": "已退出登录"}

    @app.get("/api/v1/courses", response_model=list[Course], tags=["课程"])
    def courses(actor: ActorDependency):
        with transaction(engine) as connection:
            return repo.list_courses(connection, actor)

    @app.get("/api/v1/deferrals", response_model=Page[Application], tags=["缓考"])
    def applications(
        actor: ActorDependency,
        page: PageNumber = 1,
        size: PageSize = 20,
        pending_only: Annotated[bool, Query(alias="pendingOnly")] = False,
    ):
        with transaction(engine) as connection:
            return repo.list_applications(connection, actor, page, size, pending_only)

    @app.get("/api/v1/deferrals/{application_id}", response_model=Detail, tags=["缓考"])
    def detail(application_id: int, actor: ActorDependency):
        with transaction(engine) as connection:
            return repo.detail(connection, actor, application_id)

    @app.post(
        "/api/v1/deferrals",
        response_model=Detail,
        status_code=201,
        tags=["缓考"],
        dependencies=WRITE,
    )
    def submit(body: Submit, actor: ActorDependency, response: Response):
        result = services.submit(engine, settings, actor, body)
        response.headers["Location"] = f"/api/v1/deferrals/{result.application.id}"
        return result

    @app.post(
        "/api/v1/deferrals/{application_id}/reviews",
        response_model=Detail,
        tags=["审核"],
        dependencies=WRITE,
    )
    def review(application_id: int, body: Review, actor: ActorDependency):
        return services.review(engine, actor, application_id, body)

    @app.post(
        "/api/v1/attachments",
        response_model=AttachmentResult,
        status_code=201,
        tags=["材料"],
        dependencies=WRITE,
    )
    def upload(actor: ActorDependency, response: Response, file: Annotated[UploadFile, File()]):
        try:
            result = services.upload(engine, settings, actor, file)
        finally:
            file.file.close()
        response.headers["Location"] = f"/api/v1/attachments/{result.id}"
        return result

    @app.get("/api/v1/attachments/{attachment_id}", tags=["材料"], response_class=FileResponse)
    def download(attachment_id: int, actor: ActorDependency):
        with transaction(engine) as connection:
            attachment = services.accessible_attachment(connection, actor, attachment_id)
        return FileResponse(
            services.require_file(settings, attachment),
            media_type=attachment["media_type"],
            filename=attachment["original_name"],
        )

    @app.get("/api/v1/notifications", response_model=Page[Notice], tags=["通知"])
    def notices(actor: ActorDependency, page: PageNumber = 1, size: PageSize = 20):
        with transaction(engine) as connection:
            return repo.list_notices(connection, actor, page, size)

    @app.post(
        "/api/v1/notifications/{notice_id}/read", status_code=204, tags=["通知"], dependencies=WRITE
    )
    def read_notice(notice_id: int, actor: ActorDependency):
        with transaction(engine, write=True) as connection:
            # A locked existence check also makes repeated reads portable to MySQL rowcount semantics.
            record = connection.execute(
                select(m.notifications.c.id)
                .where(
                    m.notifications.c.id == notice_id, m.notifications.c.recipient_id == actor.id
                )
                .with_for_update()
            ).first()
            if record is None:
                raise missing()
            connection.execute(
                update(m.notifications)
                .where(m.notifications.c.id == notice_id)
                .values(is_read=True)
            )
        return Response(status_code=204)

    from app.retake_api import create_router

    app.include_router(create_router(engine))
    return app


app = create_app()
