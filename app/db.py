"""数据库访问层。

只负责三件事：
1. 建立连接，并在每个连接上开启外键约束；
2. 从 queries.sql 加载具名 SQL；
3. 提供事务上下文和查询小工具。

业务规则不要写在这里，放到 users / materials / borrowing 模块。
"""

import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = PROJECT_ROOT / "schema.sql"
QUERIES_PATH = PROJECT_ROOT / "queries.sql"
DEFAULT_DB_PATH = PROJECT_ROOT / "yy.db"

# 匹配 queries.sql 中的 "-- name: create_user" 这样的行
_NAME_LINE = re.compile(r"^--\s*name:\s*([A-Za-z0-9_]+)\s*$")

_queries = None


def load_queries(path=QUERIES_PATH):
    """把 queries.sql 拆成 {名称: SQL 文本}。

    每个 "-- name: xxx" 到下一个 "-- name:" 之间的内容都算这条 SQL，
    其中的中文注释会原样保留（SQLite 会忽略 -- 注释）。
    """
    text = Path(path).read_text(encoding="utf-8")
    result = {}
    current = None
    buffer = []
    for line in text.splitlines():
        match = _NAME_LINE.match(line)
        if match:
            if current is not None:
                result[current] = "\n".join(buffer).strip()
            current = match.group(1)
            buffer = []
        elif current is not None:
            buffer.append(line)
    if current is not None:
        result[current] = "\n".join(buffer).strip()
    return result


def named_sql(name):
    """按名称取出 SQL，第一次调用时加载并缓存。"""
    global _queries
    if _queries is None:
        _queries = load_queries()
    if name not in _queries:
        raise RuntimeError(f"queries.sql 中不存在具名 SQL：{name}")
    return _queries[name]


def connect(db_path=None):
    """打开连接。

    - isolation_level=None：关闭 sqlite3 的隐式事务，改由 transaction() 显式控制
    - PRAGMA foreign_keys=ON：SQLite 默认不检查外键，必须每个连接都打开
    """
    path = Path(db_path) if db_path else DEFAULT_DB_PATH
    # check_same_thread=False 的原因：
    # FastAPI 的同步依赖和同步路由都在线程池里执行，但不保证是同一个线程，
    # 连接在 A 线程创建、在 B 线程使用是正常现象。
    # 本项目每个请求独占一个连接，且请求内部串行使用，不存在同一连接被两个线程同时读写，
    # 因此关闭 sqlite3 的线程绑定检查是安全的。
    conn = sqlite3.connect(
        str(path),
        isolation_level=None,
        timeout=5.0,
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def init_schema(conn):
    """执行 schema.sql 建表。表已存在时不会报错（IF NOT EXISTS）。"""
    try:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        # 兼容旧库：operation_logs 的 ip 字段是后加的，旧表需要补列。
        columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(operation_logs)")
        }
        if "ip" not in columns:
            conn.execute("ALTER TABLE operation_logs ADD COLUMN ip TEXT")
    except sqlite3.IntegrityError as exc:
        raise RuntimeError(
            "建表失败：旧数据里可能存在只差大小写的重复用户名或资料编号，"
            "请先清理重复数据再启动（见 schema.sql 中的检查语句）"
        ) from exc


def table_exists(conn, name="users"):
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
    ).fetchone()
    return row is not None


@contextmanager
def transaction(conn):
    """显式事务。

    用 BEGIN IMMEDIATE 立刻拿到写锁，避免两个连接同时读到“可借阅”
    再各自去改状态。任何异常都会回滚，正常结束才提交。
    """
    if conn.in_transaction:
        raise RuntimeError("不支持嵌套事务：请先提交或回滚外层事务")
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def execute(conn, name, params=()):
    """执行写语句，返回受影响行数。调用方必须检查 rowcount。"""
    cursor = conn.execute(named_sql(name), params)
    return cursor.rowcount


def query_one(conn, name, params=()):
    """执行查询，返回一行（dict）；没有结果返回 None。"""
    row = conn.execute(named_sql(name), params).fetchone()
    return dict(row) if row is not None else None


def query_all(conn, name, params=()):
    """执行查询，返回多行（list[dict]）。"""
    rows = conn.execute(named_sql(name), params).fetchall()
    return [dict(row) for row in rows]


def query_page(conn, name, params=(), limit=None, offset=0):
    """分页查询。

    limit 为 None 且 offset 为 0 时返回全部（保持原有行为）。
    只传 offset 时用 LIMIT -1 表示不限制条数，仍然跳过前 offset 条。
    """
    if limit is None and not offset:
        return query_all(conn, name, params)

    # 具名 SQL 末尾可能跟着下一个小节的注释，这里只取第一条语句
    statement = named_sql(name).split(";", 1)[0].strip()
    if limit is None:
        sql_text = f"{statement} LIMIT -1 OFFSET ?"
        query_params = tuple(params) + (offset,)
    else:
        sql_text = f"{statement} LIMIT ? OFFSET ?"
        query_params = tuple(params) + (limit, offset)

    rows = conn.execute(sql_text, query_params).fetchall()
    return [dict(row) for row in rows]
