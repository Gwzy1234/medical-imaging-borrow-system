"""FastAPI 接口层。

路由只做三件事：接收参数、调用 app 下的业务函数、返回结果。
业务规则、事务和权限判断全部留在 app/ 的服务层，接口层不重复实现。
"""

from . import (
    routes_auth,
    routes_backup,
    routes_borrows,
    routes_logs,
    routes_materials,
    routes_users,
)

__all__ = [
    "routes_auth",
    "routes_backup",
    "routes_borrows",
    "routes_logs",
    "routes_materials",
    "routes_users",
]
