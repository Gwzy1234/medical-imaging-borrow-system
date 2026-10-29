"""并发压力回归：重复并发读、并发借阅的唯一性。"""

from concurrent.futures import ThreadPoolExecutor

from helpers import ApiTest


class ApiConcurrencyTests(ApiTest):
    def test_repeated_concurrent_reads_are_all_ok(self):
        def call(_):
            response = self.client.get("/materials", headers=self.auth(self.staff_token))
            return response.status_code

        for round_index in range(3):
            with ThreadPoolExecutor(max_workers=10) as pool:
                codes = list(pool.map(call, range(30)))
            self.assertEqual(set(codes), {200}, f"第 {round_index + 1} 轮出现异常状态码")

    def test_concurrent_borrow_through_api(self):
        def call(_):
            response = self.client.post(
                "/borrows",
                headers=self.auth(self.staff_token),
                json={"material_id": self.material["id"]},
            )
            return response.status_code

        with ThreadPoolExecutor(max_workers=8) as pool:
            codes = list(pool.map(call, range(8)))

        self.assertEqual(codes.count(200), 1)
        self.assertEqual(codes.count(409), 7)

        history = self.client.get(
            "/borrows/history", headers=self.auth(self.viewer_token)
        ).json()
        self.assertEqual(len(history), 1)
