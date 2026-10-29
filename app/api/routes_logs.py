"""操作日志接口：管理员筛选、导出与归档。"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Request, Response

from .. import audit
from .deps import client_ip, get_conn, get_current_user
from .schemas import LogArchiveRequest

router = APIRouter(prefix="/logs", tags=["操作日志"])


def _filter_params(
    username: str | None = Query(default=None, max_length=50, description="按操作人筛选"),
    action: str | None = Query(default=None, max_length=50, description="按动作筛选"),
    start: str | None = Query(default=None, max_length=32, description="起始时间 UTC，YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS"),
    end: str | None = Query(default=None, max_length=32, description="结束时间 UTC，YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS"),
):
    return {"username": username, "action": action, "start": start, "end": end}


@router.get("", summary="操作日志列表（仅管理员，支持筛选）")
def list_logs(
    filters=Depends(_filter_params),
    actor=Depends(get_current_user),
    conn=Depends(get_conn),
    limit: int | None = Query(default=None, ge=1, le=500, description="每页条数，不传返回全部"),
    offset: int = Query(default=0, ge=0, description="跳过条数"),
):
    return {
        "total": audit.count_logs(conn, actor, **filters),
        "items": audit.list_logs(conn, actor, limit=limit, offset=offset, **filters),
    }


@router.get("/export.csv", summary="导出筛选后的操作日志 CSV（仅管理员）")
def export_logs(
    filters=Depends(_filter_params),
    actor=Depends(get_current_user),
    conn=Depends(get_conn),
):
    content = audit.export_csv(conn, actor, **filters)
    filename = f"operation_logs_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        content=content.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/archive", summary="归档并清理截止时间之前的日志（仅管理员）")
def archive_logs(
    payload: LogArchiveRequest,
    request: Request,
    actor=Depends(get_current_user),
    conn=Depends(get_conn),
):
    return audit.archive_logs(
        conn,
        actor,
        payload.before,
        request.app.state.backup_dir,
        ip=client_ip(request),
    )
