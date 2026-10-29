"""并发与线程安全回归测试。

背景：FastAPI 的同步依赖和同步路由都由线程池执行，不保证是同一个线程，
所以 SQLite 连接必须允许跨线程使用（db.connect 里的 check_same_thread=False）。
这条测试用来防止以后有人把参数改回去。
"""

import threading
import unittest

from helpers import DatabaseTest
from app import borrowing, db
from app.errors import ConflictError


class ConcurrencyTests(DatabaseTest):
    def test_connection_usable_from_another_thread(self):
        conn = db.connect(self.db_path)
        result = {}

        def work():
            result["value"] = conn.execute("SELECT 1").fetchone()[0]

        thread = threading.Thread(target=work)
        thread.start()
        thread.join()
        conn.close()

        self.assertEqual(result.get("value"), 1)

    def test_concurrent_borrow_only_one_succeeds(self):
        outcomes = []
        start = threading.Barrier(2)

        def attempt():
            start.wait()
            conn = db.connect(self.db_path)
            try:
                borrowing.borrow_material(conn, material_id=self.material["id"], actor=self.staff)
                outcomes.append("ok")
            except ConflictError:
                outcomes.append("conflict")
            except Exception as exc:  # 出现其它异常说明还有问题
                outcomes.append(f"error:{type(exc).__name__}")
            finally:
                conn.close()

        threads = [threading.Thread(target=attempt) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(sorted(outcomes), ["conflict", "ok"])
        self.assertEqual(len(db.query_all(self.conn, "list_borrow_history")), 1)
