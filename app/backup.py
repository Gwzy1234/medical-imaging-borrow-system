"""数据库备份与恢复。

备份使用 SQLite 官方 backup API，生成一致性快照；
恢复前会校验文件完整性、必要表和管理员账号，并自动保存一份“恢复前”安全备份。
恢复失败时自动回滚到恢复前的数据库。
"""

import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from . import audit, db
from .errors import ConflictError, ValidationError
from .permissions import require_admin

# 核心表及字段必须完整；operation_logs 是后加的表，旧备份可能没有，恢复后会自动补建。
REQUIRED_TABLES = {
    "users": {"id", "username", "password_hash", "role", "is_active"},
    "materials": {
        "id", "material_code", "title", "modality", "body_part",
        "material_type", "storage_location", "status", "created_at",
    },
    "borrow_records": {
        "id", "material_id", "borrower_id", "borrowed_at", "due_at", "returned_at",
    },
}
OPTIONAL_TABLES = {
    "operation_logs": {
        "id", "user_id", "username", "role", "action",
        "target_type", "target_id", "detail", "created_at",
    },
}
MAX_BACKUP_BYTES = 50 * 1024 * 1024


def _timestamp():
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")


def create_backup(conn, actor):
    """把当前数据库复制成一份临时文件并返回字节内容。"""
    require_admin(actor)
    handle, path = tempfile.mkstemp(suffix=".db")
    os.close(handle)
    try:
        target = sqlite3.connect(path)
        try:
            conn.backup(target)
        finally:
            target.close()
        return Path(path).read_bytes()
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def _validate_source(source):
    try:
        integrity = source.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise ValidationError("备份文件校验失败：数据库可能已损坏")

        tables = {
            row[0]
            for row in source.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        missing_tables = sorted(set(REQUIRED_TABLES) - tables)
        if missing_tables:
            raise ValidationError(f"备份文件缺少必要的数据表：{'、'.join(missing_tables)}")

        for table, required_columns in REQUIRED_TABLES.items():
            columns = {
                row[1]
                for row in source.execute(f"PRAGMA table_info({table})")
            }
            missing_columns = sorted(required_columns - columns)
            if missing_columns:
                raise ValidationError(
                    f"备份文件的 {table} 表缺少字段：{'、'.join(missing_columns)}"
                )

        # operation_logs 是后加的表：旧备份可以没有；如果有，就必须字段完整。
        if "operation_logs" in tables:
            columns = {
                row[1]
                for row in source.execute("PRAGMA table_info(operation_logs)")
            }
            missing_columns = sorted(OPTIONAL_TABLES["operation_logs"] - columns)
            if missing_columns:
                raise ValidationError(
                    f"备份文件的 operation_logs 表缺少字段：{'、'.join(missing_columns)}"
                )

        foreign_keys = source.execute("PRAGMA foreign_key_check").fetchall()
        if foreign_keys:
            raise ValidationError("备份文件的外键数据不一致，可能不是完整的备份")

        admins = source.execute(
            "SELECT COUNT(*) FROM users WHERE role = 'admin' AND is_active = 1"
        ).fetchone()[0]
        if admins < 1:
            raise ValidationError("备份文件里没有启用的管理员账号，恢复后将无法登录")
    except sqlite3.DatabaseError as exc:
        raise ValidationError("备份文件无法读取或已损坏，请重新选择") from exc


def _copy_safety_backup(conn, backup_dir):
    backup_dir.mkdir(parents=True, exist_ok=True)
    path = backup_dir / f"pre_restore_{_timestamp()}.db"
    target = sqlite3.connect(str(path))
    try:
        conn.backup(target)
    finally:
        target.close()
    return path


def _restore_from_file(source_path, db_path):
    target = sqlite3.connect(str(db_path))
    source = sqlite3.connect(str(source_path))
    try:
        source.backup(target)
    finally:
        source.close()
        target.close()


def restore_database(conn, db_path, data, actor, backup_dir):
    """用上传的 SQLite 备份覆盖当前数据库，失败时自动回滚。"""
    require_admin(actor)
    if not data:
        raise ValidationError("请上传数据库备份文件")
    if len(data) > MAX_BACKUP_BYTES:
        raise ValidationError("备份文件不能超过 50 MB")
    if not data.startswith(b"SQLite format 3\x00"):
        raise ValidationError("上传的文件不是有效的 SQLite 数据库备份")

    handle, upload_path = tempfile.mkstemp(suffix=".db")
    os.close(handle)
    Path(upload_path).write_bytes(data)
    source = None
    safety_path = None
    try:
        source = sqlite3.connect(upload_path)
        _validate_source(source)

        safety_path = _copy_safety_backup(conn, backup_dir)
        try:
            _restore_from_file(upload_path, db_path)
        except sqlite3.DatabaseError as exc:
            _restore_from_file(safety_path, db_path)
            raise ValidationError("备份文件无法恢复，数据库已回滚到恢复前状态") from exc

        # 旧备份可能没有后加的 operation_logs 表或索引，恢复后补建（只增不减）
        try:
            target = sqlite3.connect(str(db_path))
            try:
                db.init_schema(target)
            finally:
                target.close()
        except (RuntimeError, sqlite3.DatabaseError) as exc:
            _restore_from_file(safety_path, db_path)
            raise ValidationError(
                "备份文件无法升级到当前数据库结构，已回滚到恢复前状态"
            ) from exc

        check = sqlite3.connect(str(db_path))
        try:
            integrity = check.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            check.close()
        if integrity != "ok":
            raise ConflictError("恢复后数据库校验失败，已自动回滚")

        return {"status": "ok", "safety_backup": safety_path.name}
    except ConflictError:
        # 恢复出的库损坏：用安全备份回滚
        if safety_path is not None:
            _restore_from_file(safety_path, db_path)
        raise
    except Exception:
        if safety_path is not None:
            try:
                _restore_from_file(safety_path, db_path)
            except Exception:
                pass
        raise
    finally:
        if source is not None:
            source.close()
        try:
            os.unlink(upload_path)
        except OSError:
            pass


def record_restore(conn, actor, safety_name, ip=None):
    """恢复成功后，在恢复出的数据库里写一条审计记录。"""
    audit.record(
        conn, actor, "恢复数据库", "系统", None,
        f"恢复前安全备份：{safety_name}", ip=ip,
    )
