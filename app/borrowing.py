"""借阅与归还业务。

核心要求：
- 借阅、归还都必须在一个事务里完成；
- UPDATE 语句自带状态条件，并用 rowcount 确认真的改到了 1 行；
- 数据库里的部分唯一索引（uq_borrow_records_active_material）是最后一道保险。
"""

import sqlite3

from . import db, timeutil
from .errors import ConflictError, NotFoundError, ValidationError
from .permissions import require_staff_or_admin, require_user

DEFAULT_LOAN_DAYS = 14


def borrow_material(conn, *, material_id, actor, due_at=None):
    """借阅资料：改资料状态 + 写借阅记录，全部在一个事务里。"""
    require_staff_or_admin(actor)

    material = db.query_one(conn, "get_material_by_id", (material_id,))
    if material is None:
        raise NotFoundError(f"资料不存在：{material_id}")

    due = timeutil.default_due_at(DEFAULT_LOAN_DAYS) if due_at is None else timeutil.to_sql_time(due_at)
    if timeutil.parse_sql_time(due) <= timeutil.utc_now():
        raise ValidationError("预计归还时间必须晚于当前时间")

    with db.transaction(conn):
        # 第 1 步：把 available 改成 borrowed，改到 0 行说明资料不可借
        affected = db.execute(conn, "mark_material_borrowed", (material_id,))
        if affected != 1:
            raise ConflictError("该资料当前不是可借阅状态，无法借阅")

        # 第 2 步：写借阅记录；唯一索引会兜住并发下的重复插入
        try:
            db.execute(conn, "create_borrow_record", (material_id, actor["id"], due))
        except sqlite3.IntegrityError as exc:
            raise ConflictError("该资料已经存在未归还的借阅记录") from exc

    return db.query_one(conn, "get_active_borrow_by_material", (material_id,))


def return_material(conn, *, material_id, actor):
    """归还资料：先写归还时间，再把资料状态改回 available，同一个事务。"""
    require_staff_or_admin(actor)

    with db.transaction(conn):
        # 第 1 步：找到这条资料当前未归还的记录
        record = db.query_one(conn, "get_active_borrow_by_material", (material_id,))
        if record is None:
            raise ConflictError("该资料当前没有未归还的借阅记录，无法归还")

        # 第 2 步：记录归还时间（WHERE returned_at IS NULL 防重复归还）
        affected = db.execute(conn, "return_borrow_record", (record["id"],))
        if affected != 1:
            raise ConflictError("归还失败：借阅记录已被其他操作修改")

        # 第 3 步：资料恢复可借阅（WHERE status = 'borrowed' 防状态错乱）
        affected = db.execute(conn, "mark_material_available", (material_id,))
        if affected != 1:
            raise ConflictError("归还失败：资料状态已被其他操作修改")

    return {
        "material_id": material_id,
        "record_id": record["id"],
        "borrowed_at": record["borrowed_at"],
        "status": "available",
    }


def get_active_borrow(conn, material_id, actor):
    """查询某份资料当前未归还的记录，没有则抛 NotFound。"""
    require_user(actor)
    material = db.query_one(conn, "get_material_by_id", (material_id,))
    if material is None:
        raise NotFoundError(f"资料不存在：{material_id}")
    record = db.query_one(conn, "get_active_borrow_by_material", (material_id,))
    if record is None:
        raise NotFoundError("该资料当前没有未归还的借阅记录")
    return record


def list_active_borrows(conn, actor, limit=None, offset=0):
    """全部未归还记录，已登录即可查看；limit 为 None 时返回全部。"""
    require_user(actor)
    return db.query_page(conn, "list_active_borrows", (), limit=limit, offset=offset)


def list_borrow_history(conn, actor, limit=None, offset=0):
    """全部借阅历史（含已归还），最新的在前；limit 为 None 时返回全部。"""
    require_user(actor)
    return db.query_page(conn, "list_borrow_history", (), limit=limit, offset=offset)


def list_overdue_borrows(conn, actor, limit=None, offset=0):
    """逾期未归还记录；limit 为 None 时返回全部。"""
    require_user(actor)
    return db.query_page(conn, "list_overdue_borrows", (), limit=limit, offset=offset)
