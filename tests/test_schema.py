"""验证 schema.sql：表、约束、索引、具名 SQL 是否齐全。"""

import sqlite3
import unittest

from helpers import DatabaseTest
from app import db


class SchemaConstraintTests(DatabaseTest):
    def test_three_tables_exist(self):
        rows = self.conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        names = {row["name"] for row in rows}
        for expected in ("users", "materials", "borrow_records"):
            self.assertIn(expected, names)

    def test_foreign_keys_enabled(self):
        value = self.conn.execute("PRAGMA foreign_keys").fetchone()[0]
        self.assertEqual(value, 1)

    def test_username_must_be_unique(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO users (username, password_hash, role) VALUES ('admin', 'x', 'viewer')"
            )

    def test_role_is_restricted(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO users (username, password_hash, role) VALUES ('guest', 'x', 'guest')"
            )

    def test_is_active_is_restricted(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO users (username, password_hash, role, is_active) VALUES ('x', 'y', 'viewer', 2)"
            )

    def test_borrow_record_requires_existing_material(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO borrow_records (material_id, borrower_id, due_at) VALUES (9999, ?, '2030-01-01 00:00:00')",
                (self.staff["id"],),
            )

    def test_borrow_record_requires_existing_user(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO borrow_records (material_id, borrower_id, due_at) VALUES (?, 9999, '2030-01-01 00:00:00')",
                (self.material["id"],),
            )

    def test_return_time_cannot_be_before_borrow_time(self):
        record_id = self.insert_raw_record("2030-01-01 00:00:00")
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "UPDATE borrow_records SET returned_at = '2000-01-01 00:00:00' WHERE id = ?",
                (record_id,),
            )

    def test_only_one_active_borrow_per_material(self):
        self.insert_raw_record("2030-01-01 00:00:00")
        with self.assertRaises(sqlite3.IntegrityError):
            self.insert_raw_record("2030-01-02 00:00:00")

    def test_partial_unique_index_ignores_returned_records(self):
        first = self.insert_raw_record("2030-01-01 00:00:00")
        self.conn.execute(
            "UPDATE borrow_records SET returned_at = CURRENT_TIMESTAMP WHERE id = ?", (first,)
        )
        # 归还之后可以再建新的未归还记录
        self.insert_raw_record("2030-02-01 00:00:00")

    def test_case_insensitive_unique_indexes_exist(self):
        rows = self.conn.execute("SELECT name FROM sqlite_master WHERE type = 'index'").fetchall()
        names = {row["name"] for row in rows}
        self.assertIn("uq_users_username_nocase", names)
        self.assertIn("uq_materials_code_nocase", names)


class QueriesFileTests(unittest.TestCase):
    EXPECTED = {
        "create_user", "get_user_by_id", "get_user_by_username", "list_users", "disable_user",
        "enable_user", "update_user_role",
        "create_material", "get_material_by_id", "get_material_by_code", "list_materials",
        "list_available_materials", "update_material", "disable_material", "enable_material",
        "count_borrow_records_by_material", "delete_material",
        "delete_borrow_records_by_material",
        "create_borrow_record", "mark_material_borrowed", "get_active_borrow_by_material",
        "list_active_borrows", "list_borrow_history", "list_overdue_borrows",
        "return_borrow_record", "mark_material_available",
        "create_operation_log", "list_operation_logs", "count_operation_logs",
        "delete_operation_logs_before",
    }

    def test_all_named_queries_present(self):
        queries = db.load_queries()
        self.assertEqual(self.EXPECTED - set(queries), set())

    def test_every_query_uses_qmark_placeholders(self):
        for name, text in db.load_queries().items():
            # 本项目统一用 ? 占位符，不出现 :name / $name / @name 风格
            for marker in (":", "$", "@"):
                self.assertNotIn(f" {marker}", text, f"{name} 里出现了非 ? 占位符")
