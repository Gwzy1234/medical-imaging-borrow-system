"""用户业务：创建、查询、停用。

登录逻辑在 auth.py 里，这里只管用户数据本身。
"""

import sqlite3

from . import db, security
from .errors import ConflictError, NotFoundError, PermissionDenied, ValidationError
from .permissions import ROLES, require_admin, require_user

USERNAME_MAX_LENGTH = 50
PASSWORD_MIN_LENGTH = 6


def public_user(row):
    """去掉 password_hash，只保留可以返回给调用方的字段。"""
    return {
        "id": row["id"],
        "username": row["username"],
        "role": row["role"],
        "is_active": row["is_active"],
    }


def _clean_username(username):
    if not isinstance(username, str):
        raise ValidationError("用户名必须是字符串")
    username = username.strip()
    if not username:
        raise ValidationError("用户名不能为空")
    if len(username) > USERNAME_MAX_LENGTH:
        raise ValidationError(f"用户名不能超过 {USERNAME_MAX_LENGTH} 个字符")
    return username


def _validate_password(password):
    if not isinstance(password, str) or len(password) < PASSWORD_MIN_LENGTH:
        raise ValidationError(f"密码至少需要 {PASSWORD_MIN_LENGTH} 个字符")
    return password


def _validate_role(role):
    if role not in ROLES:
        raise ValidationError("角色只能是 admin、staff 或 viewer")
    return role


def create_user(conn, *, username, password, role, actor=None):
    """创建用户。

    actor 为 None 时表示“系统初始化”，只允许在还没有任何用户时
    创建第一个管理员；之后创建用户必须由管理员发起。
    """
    username = _clean_username(username)
    password = _validate_password(password)
    role = _validate_role(role)

    if actor is None:
        if len(db.query_all(conn, "list_users")) > 0:
            raise PermissionDenied("系统已有用户，只有管理员可以创建新用户")
        if role != "admin":
            raise ValidationError("系统第一个用户必须是 admin")
    else:
        require_admin(actor)

    try:
        db.execute(conn, "create_user", (username, security.hash_password(password), role))
    except sqlite3.IntegrityError as exc:
        raise ConflictError(f"用户名已存在：{username}") from exc

    return public_user(db.query_one(conn, "get_user_by_username", (username,)))


def get_user(conn, user_id, actor):
    """按 id 查询用户：管理员可以查任何人，其他人只能查自己。"""
    require_user(actor)
    row = db.query_one(conn, "get_user_by_id", (user_id,))
    if row is None:
        raise NotFoundError(f"用户不存在：{user_id}")
    if actor["id"] != user_id and actor["role"] != "admin":
        raise PermissionDenied("只能查看自己的账户信息")
    return public_user(row)


def list_users(conn, actor, limit=None, offset=0):
    """用户列表，仅管理员可用；limit 为 None 时返回全部。"""
    require_admin(actor)
    rows = db.query_page(conn, "list_users", (), limit=limit, offset=offset)
    return [public_user(row) for row in rows]


def disable_user(conn, user_id, actor):
    """停用用户，仅管理员可用；不能停用自己。"""
    require_admin(actor)
    if actor["id"] == user_id:
        raise ConflictError("不能停用自己的账户")

    row = db.query_one(conn, "get_user_by_id", (user_id,))
    if row is None:
        raise NotFoundError(f"用户不存在：{user_id}")

    affected = db.execute(conn, "disable_user", (user_id,))
    if affected != 1:
        raise ConflictError("该用户已经是停用状态")

    return public_user(db.query_one(conn, "get_user_by_id", (user_id,)))


def enable_user(conn, user_id, actor):
    """启用用户，仅管理员可用。"""
    require_admin(actor)
    row = db.query_one(conn, "get_user_by_id", (user_id,))
    if row is None:
        raise NotFoundError(f"用户不存在：{user_id}")

    affected = db.execute(conn, "enable_user", (user_id,))
    if affected != 1:
        raise ConflictError("该用户已经是启用状态")

    return public_user(db.query_one(conn, "get_user_by_id", (user_id,)))


def change_role(conn, user_id, role, actor):
    """修改用户角色，仅管理员可用；不能修改自己的角色，避免把自己锁在系统外。"""
    require_admin(actor)
    role = _validate_role(role)
    if actor["id"] == user_id:
        raise ConflictError("不能修改自己的角色")

    row = db.query_one(conn, "get_user_by_id", (user_id,))
    if row is None:
        raise NotFoundError(f"用户不存在：{user_id}")
    if row["role"] == role:
        raise ConflictError("该用户已经拥有这个角色")

    db.execute(conn, "update_user_role", (role, user_id))
    return public_user(db.query_one(conn, "get_user_by_id", (user_id,)))
