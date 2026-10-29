"""借阅流程演示（不涉及 HTTP，直接调用业务函数）。

运行前先初始化数据库：
    python scripts/init_db.py --reset --seed
    python scripts/demo.py
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app import auth, borrowing, db, materials  # noqa: E402
from app.errors import DomainError  # noqa: E402


def main():
    conn = db.connect()
    try:
        if not db.table_exists(conn, "users"):
            print("数据库还没有初始化，请先运行：python scripts/init_db.py --reset --seed")
            return 1
        return run_demo(conn)
    finally:
        conn.close()


def run_demo(conn):
    session = auth.login(conn, "staff", "staff123")
    staff = session["user"]
    print(f"staff 登录成功，令牌前 8 位：{session['token'][:8]}…")

    available = materials.list_available_materials(conn, staff)
    if not available:
        print("没有可借阅的资料，请重新初始化：python scripts/init_db.py --reset --seed")
        return 1

    target = available[0]
    print(f"选中资料：{target['material_code']} {target['title']}")

    record = borrowing.borrow_material(conn, material_id=target["id"], actor=staff)
    print(f"借阅成功：记录 #{record['id']}，应还时间 {record['due_at']}（UTC）")

    try:
        borrowing.borrow_material(conn, material_id=target["id"], actor=staff)
        print("异常：同一份资料被重复借阅了")
        return 1
    except DomainError as exc:
        print(f"重复借阅被拒绝（符合预期）：{exc.message}")

    result = borrowing.return_material(conn, material_id=target["id"], actor=staff)
    print(f"归还成功：记录 #{result['record_id']}，资料状态 {result['status']}")

    borrowing.borrow_material(conn, material_id=target["id"], actor=staff)
    print("归还后再次借阅成功（符合预期）")

    history = borrowing.list_borrow_history(conn, staff)
    active = sum(1 for row in history if row["returned_at"] is None)
    print(f"借阅历史共 {len(history)} 条，其中未归还 {active} 条")

    viewer = auth.login(conn, "viewer", "viewer123")["user"]
    try:
        borrowing.borrow_material(conn, material_id=target["id"], actor=viewer)
    except DomainError as exc:
        print(f"viewer 借阅被拒绝（符合预期）：{exc.message}")

    borrowing.return_material(conn, material_id=target["id"], actor=staff)
    print("演示结束，资料已恢复为可借阅状态。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
