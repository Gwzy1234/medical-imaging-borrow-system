"""时间工具。

数据库里所有时间都是 TEXT，格式 "YYYY-MM-DD HH:MM:SS"，并且是 UTC。
SQLite 的 CURRENT_TIMESTAMP 本身就是 UTC，所以 Python 这边也必须用 UTC，
否则文本比较（比如逾期判断）会整体错几个小时。
"""

from datetime import datetime, timedelta, timezone

from .errors import ValidationError

SQL_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def utc_now():
    """当前 UTC 时间，精确到秒（和 CURRENT_TIMESTAMP 对齐）。"""
    return datetime.now(timezone.utc).replace(microsecond=0)


def to_sql_time(value):
    """把 datetime 或字符串统一成库里的文本格式。"""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            # 没带时区的时间一律按 UTC 理解，避免混入本地时间
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).strftime(SQL_TIME_FORMAT)
    if isinstance(value, str):
        return parse_sql_time(value).strftime(SQL_TIME_FORMAT)
    raise ValidationError("时间必须是 datetime 或 'YYYY-MM-DD HH:MM:SS' 字符串")


def parse_sql_time(text):
    """把库里的文本时间解析成带 UTC 时区的 datetime。"""
    if not isinstance(text, str):
        raise ValidationError("时间必须是 'YYYY-MM-DD HH:MM:SS' 字符串")
    try:
        parsed = datetime.strptime(text.strip(), SQL_TIME_FORMAT)
    except ValueError as exc:
        raise ValidationError("时间格式应为 'YYYY-MM-DD HH:MM:SS'") from exc
    return parsed.replace(tzinfo=timezone.utc)


def default_due_at(days=14):
    """默认应还时间：从现在起若干天。"""
    return to_sql_time(utc_now() + timedelta(days=days))
