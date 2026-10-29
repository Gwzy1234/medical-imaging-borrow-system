"""资料业务：新增、查询、修改、停用。

查询类操作所有已登录用户都可用；增改停只有管理员可用。
"""

import sqlite3

from . import db
from .errors import ConflictError, NotFoundError, ValidationError
from .permissions import require_admin, require_user

MATERIAL_TEXT_MAX_LENGTH = 100

_TEXT_FIELDS = {
    "material_code": "资料编号",
    "title": "资料名称",
    "modality": "影像检查类型",
    "body_part": "检查部位",
    "material_type": "资料载体",
    "storage_location": "存放位置",
}


def _clean_text(field, value):
    label = _TEXT_FIELDS[field]
    if not isinstance(value, str):
        raise ValidationError(f"{label}必须是字符串")
    value = value.strip()
    if not value:
        raise ValidationError(f"{label}不能为空")
    if len(value) > MATERIAL_TEXT_MAX_LENGTH:
        raise ValidationError(f"{label}不能超过 {MATERIAL_TEXT_MAX_LENGTH} 个字符")
    return value


def create_material(
    conn,
    *,
    material_code,
    title,
    modality,
    body_part,
    material_type,
    storage_location,
    actor,
):
    """新增资料，仅管理员可用。"""
    require_admin(actor)
    params = (
        _clean_text("material_code", material_code),
        _clean_text("title", title),
        _clean_text("modality", modality),
        _clean_text("body_part", body_part),
        _clean_text("material_type", material_type),
        _clean_text("storage_location", storage_location),
    )
    try:
        db.execute(conn, "create_material", params)
    except sqlite3.IntegrityError as exc:
        raise ConflictError(f"资料编号已存在：{params[0]}") from exc

    return db.query_one(conn, "get_material_by_code", (params[0],))


def get_material(conn, material_id, actor):
    """按 id 查询资料。"""
    require_user(actor)
    row = db.query_one(conn, "get_material_by_id", (material_id,))
    if row is None:
        raise NotFoundError(f"资料不存在：{material_id}")
    return row


def get_material_by_code(conn, material_code, actor):
    """按资料编号查询。"""
    require_user(actor)
    if not isinstance(material_code, str) or not material_code.strip():
        raise ValidationError("资料编号不能为空")
    row = db.query_one(conn, "get_material_by_code", (material_code.strip(),))
    if row is None:
        raise NotFoundError(f"资料不存在：{material_code}")
    return row


def list_materials(conn, actor, limit=None, offset=0):
    """全部资料（含已停用、已借出）；limit 为 None 时返回全部。"""
    require_user(actor)
    return db.query_page(conn, "list_materials", (), limit=limit, offset=offset)


def list_available_materials(conn, actor, limit=None, offset=0):
    """只查可借阅的资料；limit 为 None 时返回全部。"""
    require_user(actor)
    return db.query_page(conn, "list_available_materials", (), limit=limit, offset=offset)


def update_material(
    conn,
    material_id,
    *,
    title=None,
    modality=None,
    body_part=None,
    material_type=None,
    storage_location=None,
    actor,
):
    """修改资料基本信息，仅管理员可用；只传需要改的字段，其余保持原值。"""
    require_admin(actor)
    existing = db.query_one(conn, "get_material_by_id", (material_id,))
    if existing is None:
        raise NotFoundError(f"资料不存在：{material_id}")

    current = {
        "title": title if title is not None else existing["title"],
        "modality": modality if modality is not None else existing["modality"],
        "body_part": body_part if body_part is not None else existing["body_part"],
        "material_type": material_type if material_type is not None else existing["material_type"],
        "storage_location": storage_location if storage_location is not None else existing["storage_location"],
    }
    values = tuple(_clean_text(field, current[field]) for field in
                   ("title", "modality", "body_part", "material_type", "storage_location"))

    db.execute(conn, "update_material", values + (material_id,))
    return db.query_one(conn, "get_material_by_id", (material_id,))


def disable_material(conn, material_id, actor):
    """停用资料，仅管理员可用；只能停用处于 available 状态的资料。"""
    require_admin(actor)
    existing = db.query_one(conn, "get_material_by_id", (material_id,))
    if existing is None:
        raise NotFoundError(f"资料不存在：{material_id}")
    if existing["status"] != "available":
        raise ConflictError("只有可借阅状态的资料才能停用")

    affected = db.execute(conn, "disable_material", (material_id,))
    if affected != 1:
        raise ConflictError("停用失败：资料状态已被其他操作修改")

    return db.query_one(conn, "get_material_by_id", (material_id,))


def enable_material(conn, material_id, actor):
    """启用资料，仅管理员可用；只能把已停用的资料恢复为可借阅。"""
    require_admin(actor)
    existing = db.query_one(conn, "get_material_by_id", (material_id,))
    if existing is None:
        raise NotFoundError(f"资料不存在：{material_id}")
    if existing["status"] != "disabled":
        raise ConflictError("只有已停用的资料才能启用")

    affected = db.execute(conn, "enable_material", (material_id,))
    if affected != 1:
        raise ConflictError("启用失败：资料状态已被其他操作修改")

    return db.query_one(conn, "get_material_by_id", (material_id,))


def delete_material(conn, material_id, actor, force=False):
    """删除资料。

    默认只允许删除没有借阅记录的资料；force=True 时连同借阅历史一起删除。
    """
    require_admin(actor)
    existing = db.query_one(conn, "get_material_by_id", (material_id,))
    if existing is None:
        raise NotFoundError(f"资料不存在：{material_id}")

    deleted_records = 0
    with db.transaction(conn):
        records = db.query_one(conn, "count_borrow_records_by_material", (material_id,))
        if records and records["total"]:
            if not force:
                raise ConflictError(
                    "该资料存在借阅记录，不能直接删除；请使用停用，或确认后强制删除（会同时删除借阅历史）"
                )
            deleted_records = db.execute(
                conn, "delete_borrow_records_by_material", (material_id,)
            )

        try:
            affected = db.execute(conn, "delete_material", (material_id,))
        except sqlite3.IntegrityError as exc:
            raise ConflictError("该资料仍被借阅记录引用，不能删除") from exc
        if affected != 1:
            raise ConflictError("删除失败：资料状态已被其他操作修改")

    return {"material": existing, "deleted_records": deleted_records}
