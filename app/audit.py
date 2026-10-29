"""操作日志：记录、筛选、CSV 导出与归档清理。

日志由接口层在业务操作成功后写入，记录操作人、动作、对象、IP 和当时的用户名/角色快照。
"""

import csv
import io
from datetime import datetime, timezone
from pathlib import Path

from . import db, timeutil
from .errors import ValidationError
from .permissions import require_admin

ROLE_LABELS = {"admin": "管理员", "staff": "工作人员", "viewer": "访客"}
CSV_HEADERS = ["时间(UTC)", "操作人", "角色", "动作", "对象类型", "对象ID", "详情", "客户端IP"]


def record(conn, actor, action, target_type=None, target_id=None, detail=None, ip=None):
    """写入一条操作日志；actor 允许为空（例如登录失败）。"""
    db.execute(
        conn,
        "create_operation_log",
        (
            actor["id"] if actor else None,
            actor["username"] if actor else None,
            actor["role"] if actor else None,
            action,
            target_type,
            target_id,
            detail,
            ip,
        ),
    )


def _normalize_time(value, end_of_day=False):
    text = str(value).strip()
    if len(text) == 10:
        text += " 23:59:59" if end_of_day else " 00:00:00"
    return timeutil.to_sql_time(text)


def _filters(username=None, action=None, start=None, end=None):
    """构造日志筛选条件；列名固定，值全部参数化。"""
    clauses = []
    params = []
    if username and str(username).strip():
        clauses.append("username = ?")
        params.append(str(username).strip())
    if action and str(action).strip():
        clauses.append("action = ?")
        params.append(str(action).strip())

    start_norm = _normalize_time(start) if start else None
    end_norm = _normalize_time(end, end_of_day=True) if end else None
    if start_norm and end_norm and start_norm > end_norm:
        raise ValidationError("开始时间不能晚于结束时间")
    if start_norm:
        clauses.append("created_at >= ?")
        params.append(start_norm)
    if end_norm:
        clauses.append("created_at <= ?")
        params.append(end_norm)

    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    return where, params


def _select_logs(conn, where, params, limit=None, offset=0):
    sql = (
        "SELECT id, user_id, username, role, action, target_type, target_id, "
        "detail, ip, created_at FROM operation_logs"
        + where
        + " ORDER BY id DESC"
    )
    args = list(params)
    if limit is not None:
        sql += " LIMIT ? OFFSET ?"
        args.extend([limit, offset])
    elif offset:
        sql += " LIMIT -1 OFFSET ?"
        args.append(offset)
    return [dict(row) for row in conn.execute(sql, args)]


def list_logs(conn, actor, limit=None, offset=0, username=None, action=None, start=None, end=None):
    """分页查询操作日志，仅管理员可用；支持操作人、动作和时间范围筛选。"""
    require_admin(actor)
    where, params = _filters(username, action, start, end)
    return _select_logs(conn, where, params, limit=limit, offset=offset)


def count_logs(conn, actor, username=None, action=None, start=None, end=None):
    """按筛选条件统计操作日志数量，仅管理员可用。"""
    require_admin(actor)
    where, params = _filters(username, action, start, end)
    row = conn.execute(
        f"SELECT COUNT(*) AS total FROM operation_logs{where}", params
    ).fetchone()
    return row["total"] if row else 0


def _csv_safe(value):
    """避免 CSV 公式注入：以 = + - @ 开头的单元格前加单引号。"""
    text = "" if value is None else str(value)
    if text[:1] in ("=", "+", "-", "@"):
        return "'" + text
    return text


def _csv_text(rows):
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(CSV_HEADERS)
    for row in rows:
        writer.writerow(
            [
                _csv_safe(row["created_at"]),
                _csv_safe(row["username"] or "—"),
                _csv_safe(ROLE_LABELS.get(row["role"], row["role"] or "—")),
                _csv_safe(row["action"]),
                _csv_safe(row["target_type"]),
                _csv_safe(row["target_id"]),
                _csv_safe(row["detail"]),
                _csv_safe(row["ip"]),
            ]
        )
    return "\ufeff" + buffer.getvalue()


def export_csv(conn, actor, username=None, action=None, start=None, end=None):
    """把筛选后的操作日志导出为 CSV 文本（带 UTF-8 BOM）。"""
    require_admin(actor)
    where, params = _filters(username, action, start, end)
    rows = _select_logs(conn, where, params)
    return _csv_text(rows)


def archive_logs(conn, actor, before, backup_dir, ip=None):
    """把截止时间之前的日志导出到 CSV，然后从数据库删除。"""
    require_admin(actor)
    cutoff = _normalize_time(before, end_of_day=True)
    rows = _select_logs(
        conn, " WHERE created_at < ?", [cutoff]
    )
    if not rows:
        return {"archived_count": 0, "file": None}

    backup_dir = Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    filename = (
        "operation_logs_archive_"
        + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        + ".csv"
    )
    path = backup_dir / filename
    path.write_text(_csv_text(rows), encoding="utf-8")

    with db.transaction(conn):
        deleted = db.execute(conn, "delete_operation_logs_before", (cutoff,))
    record(
        conn, actor, "归档操作日志", "操作日志", None,
        f"归档 {deleted} 条到 {filename}", ip=ip,
    )
    return {"archived_count": deleted, "file": filename}
