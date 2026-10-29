"""接口层依赖：数据库连接和当前登录用户。"""

from typing import Annotated

from fastapi import Depends, Path, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .. import auth, db
from ..errors import AuthenticationError

# SQLite 的 INTEGER 最大是 2^63-1，超过它的 Python int 绑定参数时会抛 OverflowError。
# 路径参数统一用这个类型约束，超界直接返回 422，避免变成 500。
SQL_INTEGER_MAX = 9223372036854775807

RecordId = Annotated[
    int,
    Path(ge=1, le=SQL_INTEGER_MAX, description="记录 id，正整数"),
]

# auto_error=False：没带令牌时返回 None，由我们自己抛出统一格式的 401
bearer_scheme = HTTPBearer(auto_error=False)


def get_conn(request: Request):
    """每个请求拿一个独立连接，请求结束自动关闭。

    同一个请求内多处 Depends(get_conn) 会被 FastAPI 缓存，只会真正建一次连接。
    """
    conn = db.connect(request.app.state.db_path)
    try:
        yield conn
    finally:
        conn.close()


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    conn=Depends(get_conn),
):
    """从 Authorization: Bearer <token> 解析当前用户。"""
    if credentials is None or not credentials.credentials:
        raise AuthenticationError("缺少登录令牌，请先调用 /auth/login")
    sessions = getattr(request.app.state, "sessions", None)
    return auth.current_user(conn, credentials.credentials, store=sessions)


def client_ip(request: Request):
    """取客户端 IP，用于操作日志。"""
    return request.client.host if request.client else None
