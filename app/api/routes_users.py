"""用户管理接口。

权限（管理员/本人）由服务层判断，这里只负责转发。
"""

from fastapi import APIRouter, Depends, Query, Request

from .. import audit, auth, users
from .deps import RecordId, client_ip, get_conn, get_current_user
from .schemas import UserCreateRequest, UserRoleUpdateRequest

router = APIRouter(prefix="/users", tags=["用户"])


@router.get("", summary="用户列表（仅管理员）")
def list_users(
    actor=Depends(get_current_user),
    conn=Depends(get_conn),
    limit: int | None = Query(default=None, ge=1, le=500, description="每页条数，不传返回全部"),
    offset: int = Query(default=0, ge=0, description="跳过条数"),
):
    return users.list_users(conn, actor, limit=limit, offset=offset)


@router.post("", status_code=201, summary="创建用户（仅管理员）")
def create_user(
    payload: UserCreateRequest,
    request: Request,
    actor=Depends(get_current_user),
    conn=Depends(get_conn),
):
    result = users.create_user(
        conn,
        username=payload.username,
        password=payload.password,
        role=payload.role,
        actor=actor,
    )
    audit.record(
        conn, actor, "新增用户", "用户", result["id"],
        f"用户名 {result['username']}，角色 {result['role']}",
        ip=client_ip(request),
    )
    return result


@router.get("/{user_id}", summary="查询用户（管理员或本人）")
def get_user(user_id: RecordId, actor=Depends(get_current_user), conn=Depends(get_conn)):
    return users.get_user(conn, user_id, actor)


@router.post("/{user_id}/disable", summary="停用用户（仅管理员，不能停用自己）")
def disable_user(
    user_id: RecordId,
    request: Request,
    actor=Depends(get_current_user),
    conn=Depends(get_conn),
):
    result = users.disable_user(conn, user_id, actor)
    # 停用后立刻吊销该用户的全部令牌，避免重新启用后旧令牌“复活”
    sessions = getattr(request.app.state, "sessions", None)
    auth.revoke_user_sessions(user_id, store=sessions)
    audit.record(
        conn, actor, "停用用户", "用户", result["id"],
        f"用户名 {result['username']}",
        ip=client_ip(request),
    )
    return result


@router.post("/{user_id}/enable", summary="启用用户（仅管理员）")
def enable_user(
    user_id: RecordId,
    request: Request,
    actor=Depends(get_current_user),
    conn=Depends(get_conn),
):
    result = users.enable_user(conn, user_id, actor)
    audit.record(
        conn, actor, "启用用户", "用户", result["id"],
        f"用户名 {result['username']}",
        ip=client_ip(request),
    )
    return result


@router.patch("/{user_id}/role", summary="修改用户角色（仅管理员，不能改自己）")
def change_role(
    user_id: RecordId,
    payload: UserRoleUpdateRequest,
    request: Request,
    actor=Depends(get_current_user),
    conn=Depends(get_conn),
):
    result = users.change_role(conn, user_id, payload.role, actor)
    audit.record(
        conn, actor, "修改角色", "用户", result["id"],
        f"用户名 {result['username']}，新角色 {result['role']}",
        ip=client_ip(request),
    )
    return result
