"""借阅 / 归还流程测试：状态流转、重复借阅、历史保留、逾期查询。"""

import unittest

from helpers import DatabaseTest
from app import borrowing
from app.errors import ConflictError, NotFoundError, ValidationError


class BorrowFlowTests(DatabaseTest):
    def test_borrow_marks_material_borrowed_and_creates_record(self):
        record = borrowing.borrow_material(self.conn, material_id=self.material["id"], actor=self.staff)
        self.assertIsNone(record["returned_at"])
        self.assertEqual(record["borrower_id"], self.staff["id"])
        self.assertEqual(self.material_status(), "borrowed")

    def test_double_borrow_is_rejected(self):
        borrowing.borrow_material(self.conn, material_id=self.material["id"], actor=self.staff)
        with self.assertRaises(ConflictError):
            borrowing.borrow_material(self.conn, material_id=self.material["id"], actor=self.admin)

    def test_return_restores_available_and_stamps_time(self):
        record = borrowing.borrow_material(self.conn, material_id=self.material["id"], actor=self.staff)
        result = borrowing.return_material(self.conn, material_id=self.material["id"], actor=self.staff)

        self.assertEqual(result["record_id"], record["id"])
        self.assertEqual(self.material_status(), "available")
        history = borrowing.list_borrow_history(self.conn, self.admin)
        self.assertEqual(len(history), 1)
        self.assertIsNotNone(history[0]["returned_at"])

    def test_return_without_active_record_is_rejected(self):
        with self.assertRaises(ConflictError):
            borrowing.return_material(self.conn, material_id=self.material["id"], actor=self.staff)

    def test_history_kept_and_reborrow_allowed(self):
        first = borrowing.borrow_material(self.conn, material_id=self.material["id"], actor=self.staff)
        borrowing.return_material(self.conn, material_id=self.material["id"], actor=self.staff)
        second = borrowing.borrow_material(self.conn, material_id=self.material["id"], actor=self.admin)

        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(self.material_status(), "borrowed")

        history = borrowing.list_borrow_history(self.conn, self.viewer)
        self.assertEqual(len(history), 2)
        returned = [row for row in history if row["returned_at"] is not None]
        self.assertEqual([row["id"] for row in returned], [first["id"]])

    def test_borrow_unknown_material(self):
        with self.assertRaises(NotFoundError):
            borrowing.borrow_material(self.conn, material_id=9999, actor=self.staff)

    def test_past_due_date_is_rejected(self):
        with self.assertRaises(ValidationError):
            borrowing.borrow_material(
                self.conn, material_id=self.material["id"], actor=self.staff,
                due_at="2000-01-01 00:00:00",
            )

    def test_default_due_date_is_after_borrowed_time(self):
        record = borrowing.borrow_material(self.conn, material_id=self.material["id"], actor=self.staff)
        self.assertGreater(record["due_at"], record["borrowed_at"])

    def test_active_borrow_list(self):
        borrowing.borrow_material(self.conn, material_id=self.material["id"], actor=self.staff)
        rows = borrowing.list_active_borrows(self.conn, self.viewer)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["material_code"], "IMG-001")
        self.assertEqual(rows[0]["borrower_username"], "staff")

    def test_overdue_list(self):
        self.insert_raw_record("2000-01-01 00:00:00")
        overdue = borrowing.list_overdue_borrows(self.conn, self.admin)
        self.assertEqual(len(overdue), 1)
        self.assertEqual(overdue[0]["material_code"], "IMG-001")
