"""资料管理接口。"""

from fastapi import APIRouter, Depends, Query, Request

from .. import audit, materials
from .. import imports as imports_service
from .deps import RecordId, client_ip, get_conn, get_current_user
from .schemas import MaterialCreateRequest, MaterialImportRequest, MaterialUpdateRequest

router = APIRouter(prefix="/materials", tags=["资料"])


@router.get("", summary="全部资料")
def list_materials(
    actor=Depends(get_current_user),
    conn=Depends(get_conn),
    limit: int | None = Query(default=None, ge=1, le=500, description="每页条数，不传返回全部"),
    offset: int = Query(default=0, ge=0, description="跳过条数"),
):
    return materials.list_materials(conn, actor, limit=limit, offset=offset)


# 注意：/available 必须写在 /{material_id} 前面，否则会被当成 material_id 解析
@router.get("/available", summary="可借阅资料")
def list_available(
    actor=Depends(get_current_user),
    conn=Depends(get_conn),
    limit: int | None = Query(default=None, ge=1, le=500, description="每页条数，不传返回全部"),
    offset: int = Query(default=0, ge=0, description="跳过条数"),
):
    return materials.list_available_materials(conn, actor, limit=limit, offset=offset)


@router.post("", status_code=201, summary="新增资料（仅管理员）")
def create_material(
    payload: MaterialCreateRequest,
    request: Request,
    actor=Depends(get_current_user),
    conn=Depends(get_conn),
):
    result = materials.create_material(conn, actor=actor, **payload.model_dump())
    audit.record(
        conn, actor, "新增资料", "资料", result["id"],
        f"{result['material_code']} {result['title']}",
        ip=client_ip(request),
    )
    return result


@router.post("/import", summary="批量导入资料（仅管理员，CSV 解析后提交）")
def import_materials(
    payload: MaterialImportRequest,
    request: Request,
    actor=Depends(get_current_user),
    conn=Depends(get_conn),
):
    result = imports_service.import_materials(
        conn,
        [row.model_dump() for row in payload.rows],
        actor,
    )
    audit.record(
        conn,
        actor,
        "批量导入资料",
        "资料",
        None,
        f"成功 {result['success_count']} 条，失败 {result['failed_count']} 条",
        ip=client_ip(request),
    )
    return result


@router.get("/{material_id}", summary="按 id 查询资料")
def get_material(material_id: RecordId, actor=Depends(get_current_user), conn=Depends(get_conn)):
    return materials.get_material(conn, material_id, actor)


@router.patch("/{material_id}", summary="修改资料基本信息（仅管理员）")
def update_material(
    material_id: RecordId,
    payload: MaterialUpdateRequest,
    request: Request,
    actor=Depends(get_current_user),
    conn=Depends(get_conn),
):
    result = materials.update_material(conn, material_id, actor=actor, **payload.model_dump())
    audit.record(
        conn, actor, "修改资料", "资料", result["id"],
        f"{result['material_code']} {result['title']}",
        ip=client_ip(request),
    )
    return result


@router.post("/{material_id}/disable", summary="停用资料（仅管理员）")
def disable_material(
    material_id: RecordId,
    request: Request,
    actor=Depends(get_current_user),
    conn=Depends(get_conn),
):
    result = materials.disable_material(conn, material_id, actor)
    audit.record(
        conn, actor, "停用资料", "资料", result["id"],
        f"{result['material_code']} {result['title']}",
        ip=client_ip(request),
    )
    return result


@router.post("/{material_id}/enable", summary="启用已停用的资料（仅管理员）")
def enable_material(
    material_id: RecordId,
    request: Request,
    actor=Depends(get_current_user),
    conn=Depends(get_conn),
):
    result = materials.enable_material(conn, material_id, actor)
    audit.record(
        conn, actor, "启用资料", "资料", result["id"],
        f"{result['material_code']} {result['title']}",
        ip=client_ip(request),
    )
    return result


@router.delete("/{material_id}", summary="删除资料（仅管理员；可选强制删除借阅历史）")
def delete_material(
    material_id: RecordId,
    request: Request,
    force: bool = Query(default=False, description="为 true 时连同借阅历史一起删除"),
    actor=Depends(get_current_user),
    conn=Depends(get_conn),
):
    result = materials.delete_material(conn, material_id, actor, force=force)
    material = result["material"]
    detail = f"{material['material_code']} {material['title']}"
    if result["deleted_records"]:
        detail += f"，同时删除 {result['deleted_records']} 条借阅记录"
    audit.record(
        conn, actor, "删除资料", "资料", material["id"], detail,
        ip=client_ip(request),
    )
    return {
        "deleted": True,
        "id": material["id"],
        "material_code": material["material_code"],
        "title": material["title"],
        "deleted_records": result["deleted_records"],
    }
