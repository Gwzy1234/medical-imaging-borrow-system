"""数据备份与恢复接口（仅管理员）。"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request, Response

from .. import auth, backup
from ..errors import ConflictError, ValidationError
from ..permissions import require_admin
from .deps import client_ip, get_conn, get_current_user

router = APIRouter(prefix="/backup", tags=["数据备份"])


@router.get("/database", summary="下载数据库备份（仅管理员）")
def download_database(actor=Depends(get_current_user), conn=Depends(get_conn)):
    data = backup.create_backup(conn, actor)
    filename = f"yy_backup_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.db"
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/restore", summary="上传备份并恢复数据库（仅管理员）")
async def restore_database(
    request: Request,
    actor=Depends(get_current_user),
    conn=Depends(get_conn),
):
    # 先鉴权、再读取上传内容，避免非管理员发送大文件占用内存
    require_admin(actor)
    length = request.headers.get("content-length")
    if length:
        try:
            if int(length) > backup.MAX_BACKUP_BYTES:
                raise ValidationError("备份文件不能超过 50 MB")
        except ValueError:
            pass

    state = request.app.state
    if not state.restore_lock.acquire(blocking=False):
        raise ConflictError("另一个数据库恢复操作正在进行，请稍后再试")

    state.restoring = True
    try:
        data = await request.body()
        result = backup.restore_database(
            conn,
            state.db_path,
            data,
            actor,
            state.backup_dir,
        )
        # 恢复后清空所有登录令牌和登录失败计数，避免旧会话/旧限流影响新库
        auth.clear_sessions(store=state.sessions)
        throttle = getattr(state, "login_throttle", None)
        if throttle is not None:
            throttle.clear()
        backup.record_restore(
            conn, actor, result["safety_backup"], ip=client_ip(request)
        )
        return result
    finally:
        state.restoring = False
        state.restore_lock.release()
