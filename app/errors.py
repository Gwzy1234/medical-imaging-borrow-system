"""业务异常。

服务层只抛出这些异常，不把 sqlite3 的底层异常直接暴露给调用方。
每个异常都带 code 和 http_status，下一阶段接 FastAPI 时可以据此映射状态码。
"""


class DomainError(Exception):
    """所有业务异常的基类。"""

    code = "domain_error"
    http_status = 400

    def __init__(self, message):
        super().__init__(message)
        self.message = message


class ValidationError(DomainError):
    """参数不合法，比如用户名为空、角色取值错误。"""

    code = "validation_error"
    http_status = 422


class NotFoundError(DomainError):
    """要操作的记录不存在。"""

    code = "not_found"
    http_status = 404


class ConflictError(DomainError):
    """与当前数据状态冲突，比如重复借阅、重复归还。"""

    code = "conflict"
    http_status = 409


class PermissionDenied(DomainError):
    """当前用户没有执行该操作的权限。"""

    code = "permission_denied"
    http_status = 403


class AuthenticationError(DomainError):
    """未登录、令牌失效或用户名密码错误。"""

    code = "authentication_error"
    http_status = 401


class RateLimited(DomainError):
    """登录失败次数过多，暂时拒绝。"""

    code = "too_many_attempts"
    http_status = 429

    def __init__(self, message, retry_after=0):
        super().__init__(message)
        self.retry_after = retry_after
