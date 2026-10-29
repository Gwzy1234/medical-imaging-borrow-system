"""批量导入资料。

CSV 由前端解析成行数据后提交；这里逐行校验并导入，
允许部分成功，返回每一行的失败原因。
"""

from . import db, materials
from .errors import DomainError
from .permissions import require_admin


def import_materials(conn, rows, actor):
    require_admin(actor)
    created = []
    errors = []

    # 整个批次放在一个事务里：任一时刻失败只回滚该批次，不会留下半条脏数据；
    # 单行校验失败只记录错误，不影响其它合法行。
    with db.transaction(conn):
        for index, raw in enumerate(rows, start=1):
            data = {
                "material_code": (raw.get("material_code") or "").strip(),
                "title": (raw.get("title") or "").strip(),
                "modality": (raw.get("modality") or "").strip(),
                "body_part": (raw.get("body_part") or "").strip(),
                "material_type": (raw.get("material_type") or "").strip(),
                "storage_location": (raw.get("storage_location") or "").strip(),
            }
            try:
                row = materials.create_material(conn, actor=actor, **data)
                created.append(
                    {
                        "row": index,
                        "id": row["id"],
                        "material_code": row["material_code"],
                    }
                )
            except DomainError as exc:
                errors.append(
                    {
                        "row": index,
                        "material_code": data["material_code"],
                        "message": exc.message,
                    }
                )

    return {
        "success_count": len(created),
        "failed_count": len(errors),
        "created": created,
        "errors": errors,
    }
