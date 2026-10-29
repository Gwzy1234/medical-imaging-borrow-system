"""登录相关接口。"""

from fastapi import APIRouter, Depends, Request

from .. import audit, auth
from ..errors import AuthenticationError, RateLimited
from .deps import bearer_scheme, client_ip, get_conn, get_current_user
from .schemas import LoginRequest

router = APIRouter(prefix="/auth", tags=["登录"])


@router.post("/login", summary="用户名密码登录，返回令牌")
def login(payload: LoginRequest, request: Request, conn=Depends(get_conn)):
    throttle = getattr(request.app.state, "login_throttle", None)
    sessions = getattr(request.app.state, "sessions", None)
    client = request.client.host if request.client else None
    try:
        result = auth.login(
            conn,
            payload.username,
            payload.password,
            store=sessions,
            throttle=throttle,
            client=client,
        )
    except (AuthenticationError, RateLimited) as exc:
        # 登录失败也写入操作日志，方便发现暴力破解
        audit.record(
            conn, None, "登录失败", "用户", None,
            f"用户名 {payload.username}，原因：{exc.message}", ip=client,
        )
        raise
    user = result["user"]
    audit.record(conn, user, "登录", "用户", user["id"], f"用户 {user['username']} 登录", ip=client)
    return result


@router.get("/me", summary="查看当前登录用户")
def me(user: dict = Depends(get_current_user)):
    return user


@router.post("/logout", summary="注销当前令牌")
def logout(
    request: Request,
    credentials=Depends(bearer_scheme),
    user: dict = Depends(get_current_user),
    conn=Depends(get_conn),
):
    if credentials is not None:
        audit.record(
            conn, user, "退出登录", "用户", user["id"],
            f"用户 {user['username']} 退出登录", ip=client_ip(request),
        )
        sessions = getattr(request.app.state, "sessions", None)
        auth.logout(credentials.credentials, store=sessions)
    return {"ok": True}
