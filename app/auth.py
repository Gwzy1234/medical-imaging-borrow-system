"""登录、令牌与“当前用户”。

课程作业采用最简单的方案：登录后发一个随机令牌，保存在进程内存里，
服务重启后全部失效。生产环境应换成签名令牌或数据库会话表。
"""

import time

from . import db, security
from .errors import AuthenticationError, RateLimited
from .users import public_user

SESSION_TTL_SECONDS = 8 * 3600
LOGIN_MAX_FAILURES = 5
LOGIN_WINDOW_SECONDS = 300


class SessionStore:
    """令牌 -> (用户 id, 过期时间) 的内存映射。"""

    def __init__(self, ttl_seconds=SESSION_TTL_SECONDS):
        self._ttl = ttl_seconds
        self._tokens = {}

    def create(self, user_id):
        token = security.new_token()
        self._tokens[token] = (user_id, time.monotonic() + self._ttl)
        return token

    def resolve(self, token):
        item = self._tokens.get(token)
        if item is None:
            return None
        user_id, expires_at = item
        if time.monotonic() >= expires_at:
            self._tokens.pop(token, None)
            return None
        return user_id

    def revoke(self, token):
        self._tokens.pop(token, None)

    def revoke_user(self, user_id):
        """吊销某个用户的全部令牌（停用账号时使用）。"""
        for token, (owner_id, _) in list(self._tokens.items()):
            if owner_id == user_id:
                self._tokens.pop(token, None)

    def clear(self):
        """清空全部令牌（恢复数据库后使用）。"""
        self._tokens.clear()


DEFAULT_SESSIONS = SessionStore()


class LoginThrottle:
    """登录失败限流。

    按 (用户名, 客户端) 统计失败次数：窗口内失败达到上限后拒绝登录，
    登录成功立即清零，所以不会影响正常用户反复正确登录。
    """

    def __init__(self, max_failures=LOGIN_MAX_FAILURES, window_seconds=LOGIN_WINDOW_SECONDS):
        self._max = max_failures
        self._window = window_seconds
        self._failures = {}

    def _recent_failures(self, key):
        now = time.monotonic()
        recent = [t for t in self._failures.get(key, []) if now - t < self._window]
        if recent:
            self._failures[key] = recent
        else:
            self._failures.pop(key, None)
        return recent

    def check(self, key):
        """失败次数已达上限时抛 RateLimited。"""
        recent = self._recent_failures(key)
        if len(recent) >= self._max:
            retry_after = max(1, int(self._window - (time.monotonic() - recent[0])))
            raise RateLimited(
                f"登录失败次数过多，请 {retry_after} 秒后再试",
                retry_after=retry_after,
            )

    def record_failure(self, key):
        self._recent_failures(key)
        self._failures.setdefault(key, []).append(time.monotonic())

    def reset(self, key):
        self._failures.pop(key, None)

    def clear(self):
        """清空全部失败记录（恢复数据库后使用）。"""
        self._failures.clear()


DEFAULT_THROTTLE = LoginThrottle()


def _throttle_key(username, client):
    return f"{(username or '').strip().lower()}|{client or '-'}"


def login(conn, username, password, store=None, throttle=None, client=None):
    """校验用户名密码，成功返回 {"token": ..., "user": ...}。

    throttle 不为 None 时启用失败限流（HTTP 接口会传入应用级的实例）。
    """
    store = store or DEFAULT_SESSIONS
    key = _throttle_key(username, client)
    if throttle is not None:
        throttle.check(key)

    if not isinstance(username, str) or not username.strip():
        if throttle is not None:
            throttle.record_failure(key)
        raise AuthenticationError("用户名或密码错误")

    row = db.query_one(conn, "get_user_by_username", (username.strip(),))
    if row is None or not security.verify_password(password, row["password_hash"]):
        # 用户不存在和密码错误返回同一句话，避免泄露账号是否存在
        if throttle is not None:
            throttle.record_failure(key)
        raise AuthenticationError("用户名或密码错误")
    if not row["is_active"]:
        if throttle is not None:
            throttle.record_failure(key)
        raise AuthenticationError("该账户已停用，请联系管理员")

    if throttle is not None:
        throttle.reset(key)
    return {"token": store.create(row["id"]), "user": public_user(row)}


def current_user(conn, token, store=None):
    """根据令牌查出当前用户；令牌无效或用户已停用时抛 AuthenticationError。"""
    store = store or DEFAULT_SESSIONS
    user_id = store.resolve(token or "")
    if user_id is None:
        raise AuthenticationError("登录已失效，请重新登录")

    row = db.query_one(conn, "get_user_by_id", (user_id,))
    if row is None or not row["is_active"]:
        raise AuthenticationError("登录已失效，请重新登录")
    return public_user(row)


def logout(token, store=None):
    """注销令牌。"""
    (store or DEFAULT_SESSIONS).revoke(token)


def revoke_user_sessions(user_id, store=None):
    """吊销某个用户的全部登录令牌。"""
    (store or DEFAULT_SESSIONS).revoke_user(user_id)


def clear_sessions(store=None):
    """清空所有登录令牌（数据库恢复后强制重新登录）。"""
    (store or DEFAULT_SESSIONS).clear()
