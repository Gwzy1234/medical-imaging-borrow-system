"""FastAPI 应用入口。

启动方式（在项目根目录）：
    python scripts/run_api.py --reload
    # 或：python -m uvicorn app.main:app --reload

启动后：
    接口文档  http://127.0.0.1:8000/docs
    健康检查  http://127.0.0.1:8000/health

首次使用请先初始化数据库：python scripts/init_db.py --reset --seed
"""

import logging
import mimetypes
import os
import sqlite3
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import __version__, db
from .api import routes_auth, routes_backup, routes_borrows, routes_logs, routes_materials, routes_users
from .auth import LoginThrottle, SessionStore
from .errors import DomainError

logger = logging.getLogger("yy.api")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = PROJECT_ROOT / "frontend"

# Windows 的 mime 注册表有时会把 .js 识别成 text/plain，
# 那样浏览器会拒绝执行 ES module，这里显式纠正。
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("image/svg+xml", ".svg")

# 默认只放行本地开发页面；生产环境用 YY_CORS_ORIGINS 显式配置，
# 多个来源用英文逗号分隔，例如：
#   YY_CORS_ORIGINS=https://example.com,https://admin.example.com
DEFAULT_CORS_ORIGINS = (
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5500",
    "http://127.0.0.1:5500",
)


def _cors_origins():
    raw = os.environ.get("YY_CORS_ORIGINS")
    if raw is None:
        return list(DEFAULT_CORS_ORIGINS)
    return [item.strip() for item in raw.split(",") if item.strip()]


def create_app(db_path=None, backup_dir=None):
    """创建应用。

    db_path 参数主要给测试用：传入临时数据库路径即可得到独立的应用实例。
    backup_dir 用于保存恢复数据库前的安全备份。
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # 启动时确保表存在（IF NOT EXISTS，不会覆盖已有数据）
        conn = db.connect(app.state.db_path)
        try:
            db.init_schema(conn)
        finally:
            conn.close()
        yield

    app = FastAPI(
        title="医学影像资料借阅管理系统 API",
        version=__version__,
        description=(
            "本科课程设计：医学影像资料借阅管理系统。\n\n"
            "后端使用 FastAPI + 原生 SQLite SQL，不使用 ORM。\n"
            "登录后在右上角 Authorize 里填入令牌即可调试需要登录的接口。"
        ),
        lifespan=lifespan,
    )
    app.state.db_path = Path(db_path) if db_path else db.DEFAULT_DB_PATH
    app.state.backup_dir = Path(backup_dir) if backup_dir else PROJECT_ROOT / "backups"
    app.state.login_throttle = LoginThrottle()
    app.state.sessions = SessionStore()
    app.state.restoring = False
    app.state.restore_lock = threading.Lock()

    # 所有响应带上版本号；开发阶段让 HTML/JS/CSS 不被浏览器长期缓存
    @app.middleware("http")
    async def add_version_and_cache_headers(request: Request, call_next):
        if getattr(request.app.state, "restoring", False):
            path = request.url.path
            api_prefixes = ("/auth/", "/users", "/materials", "/borrows", "/logs", "/backup")
            if path.startswith(api_prefixes) and not (
                path == "/backup/restore" and request.method == "POST"
            ):
                return JSONResponse(
                    status_code=503,
                    content={
                        "code": "database_busy",
                        "message": "数据库正在恢复，请稍后重试",
                    },
                )
        response = await call_next(request)
        response.headers["X-App-Version"] = __version__
        if request.url.path == "/" or request.url.path.startswith(("/js/", "/css/")):
            # 开发阶段避免浏览器继续使用旧的前端脚本
            response.headers["Cache-Control"] = "no-cache, must-revalidate"
        return response

    origins = _cors_origins()
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.exception_handler(DomainError)
    async def handle_domain_error(request: Request, exc: DomainError):
        headers = {}
        retry_after = getattr(exc, "retry_after", 0)
        if retry_after:
            headers["Retry-After"] = str(retry_after)
        return JSONResponse(
            status_code=exc.http_status,
            content={"code": exc.code, "message": exc.message},
            headers=headers or None,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "code": "validation_error",
                "message": "请求参数不合法",
                "errors": jsonable_encoder(exc.errors()),
            },
        )

    @app.exception_handler(sqlite3.OperationalError)
    async def handle_database_busy(request: Request, exc: sqlite3.OperationalError):
        """数据库被长时间占用时返回 503，不把内部异常暴露给调用方。"""
        message = str(exc).lower()
        if "locked" in message or "busy" in message:
            return JSONResponse(
                status_code=503,
                content={"code": "database_busy", "message": "数据库繁忙，请稍后重试"},
            )
        logger.exception("数据库操作失败")
        return JSONResponse(
            status_code=500,
            content={"code": "database_error", "message": "数据库操作失败"},
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(request: Request, exc: StarletteHTTPException):
        """把框架层的 404 / 405 也统一成 {code, message} 结构。"""
        codes = {404: "not_found", 405: "method_not_allowed"}
        code = codes.get(exc.status_code, "http_error")
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": code, "message": str(exc.detail)},
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception):
        """兜底：未预料的异常也返回统一结构，并把堆栈写进服务端日志。"""
        logger.exception("未处理的异常：%s", exc)
        return JSONResponse(
            status_code=500,
            content={"code": "internal_error", "message": "服务器内部错误"},
        )

    @app.get("/health", tags=["系统"], summary="健康检查")
    def health(request: Request):
        conn = db.connect(request.app.state.db_path)
        try:
            conn.execute("SELECT 1").fetchone()
        finally:
            conn.close()
        return {"status": "ok", "version": __version__}

    app.include_router(routes_auth.router)
    app.include_router(routes_users.router)
    app.include_router(routes_materials.router)
    app.include_router(routes_borrows.router)
    app.include_router(routes_logs.router)
    app.include_router(routes_backup.router)

    # 静态前端放在最后挂载：先匹配所有 API 路由，再由 / 提供页面资源。
    if FRONTEND_DIR.is_dir():
        app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

    return app


app = create_app()
