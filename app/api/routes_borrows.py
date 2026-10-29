"""借阅与归还接口。"""

from fastapi import APIRouter, Depends, Query, Request

from .. import audit, borrowing
from .deps import RecordId, client_ip, get_conn, get_current_user
from .schemas import BorrowRequest

router = APIRouter(prefix="/borrows", tags=["借阅"])


@router.get("/active", summary="全部未归还记录")
def list_active(
    actor=Depends(get_current_user),
    conn=Depends(get_conn),
    limit: int | None = Query(default=None, ge=1, le=500, description="每页条数，不传返回全部"),
    offset: int = Query(default=0, ge=0, description="跳过条数"),
):
    return borrowing.list_active_borrows(conn, actor, limit=limit, offset=offset)


@router.get("/history", summary="借阅历史（含已归还）")
def list_history(
    actor=Depends(get_current_user),
    conn=Depends(get_conn),
    limit: int | None = Query(default=None, ge=1, le=500, description="每页条数，不传返回全部"),
    offset: int = Query(default=0, ge=0, description="跳过条数"),
):
    return borrowing.list_borrow_history(conn, actor, limit=limit, offset=offset)


@router.get("/overdue", summary="逾期未归还记录")
def list_overdue(
    actor=Depends(get_current_user),
    conn=Depends(get_conn),
    limit: int | None = Query(default=None, ge=1, le=500, description="每页条数，不传返回全部"),
    offset: int = Query(default=0, ge=0, description="跳过条数"),
):
    return borrowing.list_overdue_borrows(conn, actor, limit=limit, offset=offset)


# 同样要注意顺序：/{material_id} 放在三个固定路径后面
@router.get("/{material_id}", summary="某份资料当前未归还的借阅记录")
def get_active(material_id: RecordId, actor=Depends(get_current_user), conn=Depends(get_conn)):
    return borrowing.get_active_borrow(conn, material_id, actor)


@router.post("", summary="借阅资料（管理员或工作人员）")
def borrow(
    payload: BorrowRequest,
    request: Request,
    actor=Depends(get_current_user),
    conn=Depends(get_conn),
):
    result = borrowing.borrow_material(
        conn,
        material_id=payload.material_id,
        actor=actor,
        due_at=payload.due_at,
    )
    audit.record(
        conn, actor, "借阅资料", "资料", payload.material_id,
        f"借阅记录 #{result['id']}，应还时间 {result['due_at']}",
        ip=client_ip(request),
    )
    return result


@router.post("/{material_id}/return", summary="归还资料（管理员或工作人员）")
def give_back(
    material_id: RecordId,
    request: Request,
    actor=Depends(get_current_user),
    conn=Depends(get_conn),
):
    result = borrowing.return_material(conn, material_id=material_id, actor=actor)
    audit.record(
        conn, actor, "归还资料", "资料", material_id,
        f"归还借阅记录 #{result['record_id']}",
        ip=client_ip(request),
    )
    return result
