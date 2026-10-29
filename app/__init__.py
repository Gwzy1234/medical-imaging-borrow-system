"""医学影像资料借阅管理系统 —— Python 业务后端。

本包只使用 Python 标准库（sqlite3、hashlib、secrets），不使用 ORM。
SQL 全部来自项目根目录的 schema.sql 与 queries.sql。

分层：
    db.py          连接数据库、加载具名 SQL、事务
    security.py    密码哈希、令牌生成
    timeutil.py    UTC 时间与 SQLite 文本格式互转
    permissions.py 角色权限判断
    auth.py        登录、令牌、当前用户
    users.py       用户业务
    materials.py   资料业务
    borrowing.py   借阅与归还业务

业务层不依赖 Web 框架；接口层在 app/api/ 与 app/main.py，
只负责把 HTTP 请求转成对这里业务函数的调用。
"""

__version__ = "0.9.1"
