"""Locust 冒烟压测：登录后访问公开色板 API 和受限的 profile API。"""
from locust import HttpUser, between, task


class AiRestroUser(HttpUser):
    wait_time = between(0.5, 2.0)

    def on_start(self) -> None:
        resp = self.client.post(
            "/api/v1/auth/login",
            json={"email": "admin@test.com", "password": "admin123"},
        )
        self.token = resp.json().get("access_token", "")
        self.headers = {"Authorization": f"Bearer {self.token}"}

    @task(3)
    def color_schemes(self) -> None:
        self.client.get("/api/v1/color-schemes")

    @task(1)
    def read_profile(self) -> None:
        self.client.get(
            "/api/v1/shops/00000000-0000-0000-0000-000000000000/profiles/xiaohongshu",
            headers=self.headers,
        )
