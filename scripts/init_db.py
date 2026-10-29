"""初始化 SQLite 数据库。

用法（在项目根目录执行）：
    python scripts/init_db.py                  # 只建表
    python scripts/init_db.py --reset --seed    # 删库重建并写入演示数据
"""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app import db, materials, users  # noqa: E402

DEMO_ACCOUNTS = (
    ("admin", "admin123", "admin"),
    ("staff", "staff123", "staff"),
    ("viewer", "viewer123", "viewer"),
)

DEMO_MATERIALS = (
    dict(material_code="IMG-CT-001", title="胸部 CT 平扫", modality="CT",
         body_part="胸部", material_type="胶片", storage_location="一号库 A-01"),
    dict(material_code="IMG-MR-001", title="头颅 MRI 增强", modality="MR",
         body_part="头部", material_type="光盘", storage_location="一号库 B-02"),
    dict(material_code="IMG-DR-001", title="膝关节 DR 正侧位", modality="DR",
         body_part="膝关节", material_type="纸质报告", storage_location="二号库 C-03"),
    dict(material_code="IMG-US-001", title="腹部超声检查", modality="US",
         body_part="腹部", material_type="光盘", storage_location="二号库 D-04"),
)


def main():
    parser = argparse.ArgumentParser(description="创建数据库并可选写入演示数据")
    parser.add_argument("--db", default=str(db.DEFAULT_DB_PATH), help="数据库文件路径")
    parser.add_argument("--reset", action="store_true", help="先删除已有数据库文件")
    parser.add_argument("--seed", action="store_true", help="写入演示用户和资料")
    args = parser.parse_args()

    db_path = Path(args.db)
    if args.reset and db_path.exists():
        db_path.unlink()
        print(f"已删除旧数据库：{db_path}")

    conn = db.connect(db_path)
    try:
        db.init_schema(conn)
        print(f"表结构创建完成：{db_path}")
        if args.seed:
            _seed(conn)
    finally:
        conn.close()

    print("完成。下一步可以运行：python scripts/demo.py")
    return 0


def _seed(conn):
    existing = db.query_all(conn, "list_users")
    if existing:
        print(f"数据库里已有 {len(existing)} 个用户，跳过演示数据")
        return

    # 第一个用户由系统初始化创建，之后必须由管理员创建
    admin = users.create_user(conn, username="admin", password="admin123", role="admin")
    for username, password, role in DEMO_ACCOUNTS[1:]:
        users.create_user(conn, username=username, password=password, role=role, actor=admin)
    for item in DEMO_MATERIALS:
        materials.create_material(conn, actor=admin, **item)

    print(f"已写入 {len(DEMO_ACCOUNTS)} 个用户、{len(DEMO_MATERIALS)} 份资料")
    print("演示账号：admin/admin123，staff/staff123，viewer/viewer123")


if __name__ == "__main__":
    raise SystemExit(main())
