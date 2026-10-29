-- =============================================================
-- 医学影像资料借阅管理系统 —— 数据库结构（schema.sql）
-- 数据库：SQLite 3
-- 说明：本文件只负责建表、约束和索引，不包含业务数据操作。
--
-- 【外键开关】
-- SQLite 的外键约束默认是关闭的，而且只对当前连接生效。
-- 使用 Python sqlite3 时，必须在每个新连接上启用：
--     conn.execute("PRAGMA foreign_keys = ON")
-- 否则 borrow_records 上的外键不会真正拦截非法数据。
--
-- Python 建库示例：
--     with open("schema.sql", encoding="utf-8") as f:
--         conn.executescript(f.read())
--
-- 【时间格式约定】
-- 所有时间字段统一保存为 TEXT，格式为 "YYYY-MM-DD HH:MM:SS"
-- （即 CURRENT_TIMESTAMP 的格式，UTC 时间）。
-- 只有格式统一，文本比较（如 due_at < CURRENT_TIMESTAMP）
-- 和 CHECK 约束才能得到正确结果。
-- =============================================================

PRAGMA foreign_keys = ON;

-- -------------------------------------------------------------
-- 1. users：用户表
-- role 决定权限，具体鉴权由后续 Python 后端实现：
--   admin  管理用户、资料、借阅和归还
--   staff  查询资料、借阅和归还
--   viewer 查询资料和借阅记录
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT    NOT NULL UNIQUE,
    password_hash TEXT    NOT NULL,
    role          TEXT    NOT NULL CHECK (role IN ('admin', 'staff', 'viewer')),
    is_active     INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);

-- -------------------------------------------------------------
-- 2. materials：医学影像资料表
-- 每条记录代表一份可以独立借阅的实体资料。
-- status 的合法取值：
--   available  可借阅
--   borrowed   已借出
--   disabled   已停用
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS materials (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    material_code    TEXT    NOT NULL UNIQUE,
    title            TEXT    NOT NULL,
    modality         TEXT    NOT NULL,
    body_part        TEXT    NOT NULL,
    material_type    TEXT    NOT NULL,
    storage_location TEXT    NOT NULL,
    status           TEXT    NOT NULL DEFAULT 'available'
                             CHECK (status IN ('available', 'borrowed', 'disabled')),
    created_at       TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- -------------------------------------------------------------
-- 3. borrow_records：借阅记录表
-- 外键保证资料和借阅用户真实存在；默认的 ON DELETE NO ACTION
-- 会阻止删除仍被借阅记录引用的资料或用户，从而保留历史。
-- CHECK 保证归还时间不早于借阅时间。
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS borrow_records (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    material_id INTEGER NOT NULL,
    borrower_id INTEGER NOT NULL,
    borrowed_at TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    due_at      TEXT    NOT NULL,
    returned_at TEXT    DEFAULT NULL,
    FOREIGN KEY (material_id) REFERENCES materials (id),
    FOREIGN KEY (borrower_id) REFERENCES users (id),
    CHECK (returned_at IS NULL OR returned_at >= borrowed_at)
);

-- -------------------------------------------------------------
-- 4. operation_logs：操作日志表
-- 记录谁在什么时间做了什么操作，供管理员审计和导出。
-- 故意不对 user_id 建外键：日志需要独立留存，用户名/角色同时保存快照。
-- -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS operation_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER,
    username    TEXT,
    role        TEXT,
    action      TEXT    NOT NULL,
    target_type TEXT,
    target_id   INTEGER,
    detail      TEXT,
    ip          TEXT,
    created_at  TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_operation_logs_created_at
    ON operation_logs (created_at);

-- -------------------------------------------------------------
-- 查询索引
-- -------------------------------------------------------------

-- 按状态筛选资料（如查询全部可借阅资料）
CREATE INDEX IF NOT EXISTS idx_materials_status
    ON materials (status);

-- 按借阅人查借阅历史
CREATE INDEX IF NOT EXISTS idx_borrow_records_borrower
    ON borrow_records (borrower_id);

-- 按资料查完整借阅历史（含已归还记录）
CREATE INDEX IF NOT EXISTS idx_borrow_records_material
    ON borrow_records (material_id);

-- 只为未归还记录建立到期时间索引，加速逾期查询
CREATE INDEX IF NOT EXISTS idx_borrow_records_overdue
    ON borrow_records (due_at)
    WHERE returned_at IS NULL;

-- -------------------------------------------------------------
-- 核心业务约束：部分唯一索引
-- 同一份资料在同一时间只允许存在一条未归还的借阅记录。
-- 已归还记录的 returned_at 不为 NULL，不参与这个唯一索引，
-- 因此历史记录会保留，资料归还后也可以再次借阅。
-- -------------------------------------------------------------
CREATE UNIQUE INDEX IF NOT EXISTS uq_borrow_records_active_material
    ON borrow_records (material_id)
    WHERE returned_at IS NULL;

-- -------------------------------------------------------------
-- 大小写不敏感的唯一性
-- 用户名和资料编号如果允许 Admin 与 admin 同时存在，登录和查询就会产生歧义。
-- 这两个唯一索引配合 queries.sql 中的 COLLATE NOCASE 查询，
-- 保证“大小写不同但内容相同”的账号/编号不能重复创建。
--
-- 注意：如果旧数据库里已经存在只差大小写的重复数据，
-- 迁移时创建索引会失败。升级前请先执行检查并清理重复：
--     SELECT lower(username), COUNT(*) FROM users
--     GROUP BY lower(username) HAVING COUNT(*) > 1;
--     SELECT lower(material_code), COUNT(*) FROM materials
--     GROUP BY lower(material_code) HAVING COUNT(*) > 1;
-- -------------------------------------------------------------
CREATE UNIQUE INDEX IF NOT EXISTS uq_users_username_nocase
    ON users (username COLLATE NOCASE);

CREATE UNIQUE INDEX IF NOT EXISTS uq_materials_code_nocase
    ON materials (material_code COLLATE NOCASE);
