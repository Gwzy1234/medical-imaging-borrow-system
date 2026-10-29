"""角色权限。

权限矩阵（与课程设计文档一致）：
    admin  管理用户、管理资料、借阅和归还
    staff  查询资料、借阅和归还
    viewer 只能查询资料和借阅记录

这里的函数只做判断，不做数据库操作。
"""

from .errors import PermissionDenied

ROLES = ("admin", "staff", "viewer")

ROLE_RIGHTS = {
    "admin": "管理用户、管理资料、借阅和归还",
    "staff": "查询资料、借阅和归还",
    "viewer": "只能查询资料和借阅记录",
}


def require_user(actor):
    """确认调用者已登录且账户可用。"""
    if not actor:
        raise PermissionDenied("请先登录")
    if not actor.get("is_active"):
        raise PermissionDenied("账户已停用")
    return actor


def require_admin(actor):
    """只有管理员可以通过。"""
    require_user(actor)
    if actor["role"] != "admin":
        raise PermissionDenied("只有管理员可以执行该操作")
    return actor


def require_staff_or_admin(actor):
    """管理员或工作人员可以通过（借阅、归还）。"""
    require_user(actor)
    if actor["role"] not in ("admin", "staff"):
        raise PermissionDenied("只有管理员或工作人员可以执行该操作")
    return actor
