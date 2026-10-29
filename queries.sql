-- =============================================================
-- 医学影像资料借阅管理系统 —— 数据库操作（queries.sql）
-- 数据库：SQLite 3
--
-- 【使用约定】
-- 1. 每条语句以 "-- name: 操作名" 开头，供 Python 按名称取用。
-- 2. 所有参数统一使用 ? 占位符，按出现顺序放在元组中传入：
--        conn.execute(SQL["get_user_by_id"], (user_id,))
-- 3. 本文件只提供 SQL，不包含事务控制。借阅、归还涉及多条语句，
--    必须在 Python 中放进同一个事务按顺序调用，任一步失败即回滚。
-- 4. 带状态条件的 UPDATE 会返回受影响行数（cursor.rowcount）。
--    Python 必须检查 rowcount 是否为 1；为 0 说明状态已变化，
--    应立即回滚，不能当作成功继续执行。
-- 5. 每次新建数据库连接后都要执行：
--        PRAGMA foreign_keys = ON
-- 6. 时间统一使用 "YYYY-MM-DD HH:MM:SS" 文本格式（CURRENT_TIMESTAMP
--    的格式，UTC 时间）。不要在 Python 中混用带 "T" 的 ISO 格式，
--    否则文本比较和 CHECK 约束可能失效。
-- =============================================================


-- -------------------------------------------------------------
-- 一、用户管理
-- -------------------------------------------------------------

-- name: create_user
-- 新增用户；is_active 使用默认值 1（启用）。
-- 参数：username, password_hash, role
-- password_hash 必须由 Python 侧生成，禁止存储明文密码。
INSERT INTO users (username, password_hash, role)
VALUES (?, ?, ?);

-- name: get_user_by_id
-- 按主键查询用户；不返回密码哈希。
-- 参数：id
SELECT id, username, role, is_active
FROM users
WHERE id = ?;

-- name: get_user_by_username
-- 按用户名查询用户，登录时先查用户再校验密码哈希。
-- 用户名按大小写不敏感匹配（Admin 与 admin 视为同一个账号）。
-- 这是唯一返回 password_hash 的查询，结果不要直接返回给前端。
-- 参数：username
SELECT id, username, password_hash, role, is_active
FROM users
WHERE username = ? COLLATE NOCASE;

-- name: list_users
-- 查询全部用户，按 id 升序排列；不返回密码哈希。
SELECT id, username, role, is_active
FROM users
ORDER BY id ASC;

-- name: disable_user
-- 停用用户；只允许把启用状态（1）改为停用状态（0）。
-- 参数：id
UPDATE users
SET is_active = 0
WHERE id = ? AND is_active = 1;

-- name: enable_user
-- 启用用户；只允许把停用状态（0）改为启用状态（1）。
-- 参数：id
UPDATE users
SET is_active = 1
WHERE id = ? AND is_active = 0;

-- name: update_user_role
-- 修改用户角色；角色取值由服务层校验。
-- 参数：role, id
UPDATE users
SET role = ?
WHERE id = ?;


-- -------------------------------------------------------------
-- 二、资料管理
-- -------------------------------------------------------------

-- name: create_material
-- 新增资料；status 使用默认值 available，created_at 自动生成。
-- 参数：material_code, title, modality, body_part, material_type, storage_location
INSERT INTO materials (
    material_code, title, modality, body_part, material_type, storage_location
)
VALUES (?, ?, ?, ?, ?, ?);

-- name: get_material_by_id
-- 按主键查询资料。
-- 参数：id
SELECT id, material_code, title, modality, body_part, material_type,
       storage_location, status, created_at
FROM materials
WHERE id = ?;

-- name: get_material_by_code
-- 按资料编号查询资料。
-- 参数：material_code
SELECT id, material_code, title, modality, body_part, material_type,
       storage_location, status, created_at
FROM materials
WHERE material_code = ? COLLATE NOCASE;

-- name: list_materials
-- 查询全部资料，按 id 升序排列。
SELECT id, material_code, title, modality, body_part, material_type,
       storage_location, status, created_at
FROM materials
ORDER BY id ASC;

-- name: list_available_materials
-- 查询全部可借阅资料。
SELECT id, material_code, title, modality, body_part, material_type,
       storage_location, status, created_at
FROM materials
WHERE status = 'available'
ORDER BY id ASC;

-- name: update_material
-- 修改资料基本信息；资料编号作为标识不允许修改。
-- 参数：title, modality, body_part, material_type, storage_location, id
UPDATE materials
SET title = ?,
    modality = ?,
    body_part = ?,
    material_type = ?,
    storage_location = ?
WHERE id = ?;

-- name: disable_material
-- 停用资料；只允许停用未借出的资料（available）。
-- 参数：id
UPDATE materials
SET status = 'disabled'
WHERE id = ? AND status = 'available';

-- name: enable_material
-- 启用资料；只允许把已停用的资料（disabled）恢复为可借阅（available）。
-- 参数：id
UPDATE materials
SET status = 'available'
WHERE id = ? AND status = 'disabled';

-- name: count_borrow_records_by_material
-- 统计某份资料的借阅记录数，用于判断能否删除。
-- 参数：material_id
SELECT COUNT(*) AS total
FROM borrow_records
WHERE material_id = ?;

-- name: delete_material
-- 永久删除资料；调用方必须先确认没有借阅记录（或已选择强制删除）。
-- 参数：id
DELETE FROM materials
WHERE id = ?;

-- name: delete_borrow_records_by_material
-- 强制删除资料时，先删除它的全部借阅记录。
-- 参数：material_id
DELETE FROM borrow_records
WHERE material_id = ?;


-- -------------------------------------------------------------
-- 三、借阅管理
-- 借阅事务顺序（Python 中必须放在同一个事务里）：
--   1. 用 mark_material_borrowed 的 WHERE 条件确认资料仍可借；
--   2. 执行 mark_material_borrowed，检查 rowcount 是否为 1；
--   3. 执行 create_borrow_record；
--   4. 提交事务；任一步失败则回滚。
-- 这些语句不能脱离事务单独调用，否则资料状态和借阅记录会不一致。
-- -------------------------------------------------------------

-- name: mark_material_borrowed
-- 将资料状态从 available 改为 borrowed。
-- 只有状态仍为 available 时才会更新，可防止重复借阅。
-- 参数：id
UPDATE materials
SET status = 'borrowed'
WHERE id = ? AND status = 'available';

-- name: create_borrow_record
-- 新增借阅记录；borrowed_at 使用默认值 CURRENT_TIMESTAMP。
-- 参数：material_id, borrower_id, due_at
-- 部分唯一索引会阻止同一资料出现第二条未归还记录。
INSERT INTO borrow_records (material_id, borrower_id, due_at)
VALUES (?, ?, ?);

-- name: get_active_borrow_by_material
-- 查询某份资料当前未归还的借阅记录（最多一条）。
-- 参数：material_id
SELECT id, material_id, borrower_id, borrowed_at, due_at, returned_at
FROM borrow_records
WHERE material_id = ? AND returned_at IS NULL;

-- name: list_active_borrows
-- 查询全部未归还记录，并显示资料编号、资料名称和借阅人用户名。
SELECT br.id,
       br.material_id,
       m.material_code,
       m.title,
       br.borrower_id,
       u.username AS borrower_username,
       br.borrowed_at,
       br.due_at
FROM borrow_records AS br
JOIN materials AS m ON m.id = br.material_id
JOIN users AS u ON u.id = br.borrower_id
WHERE br.returned_at IS NULL
ORDER BY br.due_at ASC, br.id ASC;

-- name: list_borrow_history
-- 查询全部借阅历史（含已归还记录），最新的排在前面。
SELECT br.id,
       br.material_id,
       m.material_code,
       m.title,
       br.borrower_id,
       u.username AS borrower_username,
       br.borrowed_at,
       br.due_at,
       br.returned_at
FROM borrow_records AS br
JOIN materials AS m ON m.id = br.material_id
JOIN users AS u ON u.id = br.borrower_id
ORDER BY br.borrowed_at DESC, br.id DESC;

-- name: list_overdue_borrows
-- 查询逾期未归还记录：尚未归还且已超过预计归还时间。
SELECT br.id,
       br.material_id,
       m.material_code,
       m.title,
       br.borrower_id,
       u.username AS borrower_username,
       br.borrowed_at,
       br.due_at
FROM borrow_records AS br
JOIN materials AS m ON m.id = br.material_id
JOIN users AS u ON u.id = br.borrower_id
WHERE br.returned_at IS NULL
  AND br.due_at < CURRENT_TIMESTAMP
ORDER BY br.due_at ASC;


-- -------------------------------------------------------------
-- 四、归还管理
-- 归还事务顺序（Python 中必须放在同一个事务里）：
--   1. 用 get_active_borrow_by_material 查到未归还记录；
--   2. 执行 return_borrow_record，检查 rowcount 是否为 1；
--   3. 执行 mark_material_available，检查 rowcount 是否为 1；
--   4. 提交事务；任一步失败则回滚。
-- 这些语句不能脱离事务单独调用，否则会出现“已还书但仍显示借出”
-- 或“未还书却显示可借”的脏数据。
-- -------------------------------------------------------------

-- name: return_borrow_record
-- 记录实际归还时间；只更新尚未归还的记录，防止重复归还。
-- 参数：id
UPDATE borrow_records
SET returned_at = CURRENT_TIMESTAMP
WHERE id = ? AND returned_at IS NULL;

-- name: mark_material_available
-- 将已借出的资料恢复为可借阅状态。
-- 参数：id
UPDATE materials
SET status = 'available'
WHERE id = ? AND status = 'borrowed';


-- -------------------------------------------------------------
-- 五、操作日志
-- -------------------------------------------------------------

-- name: create_operation_log
-- 写入一条操作日志；用户名和角色保存当时的快照。
-- 参数：user_id, username, role, action, target_type, target_id, detail, ip
INSERT INTO operation_logs (
    user_id, username, role, action, target_type, target_id, detail, ip
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?);

-- name: list_operation_logs
-- 查询全部操作日志，最新的排在最前面。
SELECT id, user_id, username, role, action, target_type, target_id, detail, ip, created_at
FROM operation_logs
ORDER BY id DESC;

-- name: count_operation_logs
-- 统计操作日志总数，供分页使用。
SELECT COUNT(*) AS total FROM operation_logs;

-- name: delete_operation_logs_before
-- 归档后删除截止时间之前的操作日志。
-- 参数：before
DELETE FROM operation_logs
WHERE created_at < ?;
