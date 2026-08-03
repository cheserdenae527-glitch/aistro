"""安全回归测试：越权、SSRF、爬虫任务隔离。"""
from __future__ import annotations

import time
import uuid

from crawler import tasks


def _register(client, email: str) -> dict:
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "admin123", "name": "Test User"},
    )
    assert resp.status_code == 201, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _create_shop(client, headers: dict) -> str:
    m_resp = client.post(
        "/api/v1/merchants",
        json={"name": "越权测试商家"},
        headers=headers,
    )
    assert m_resp.status_code == 201, m_resp.text
    s_resp = client.post(
        f"/api/v1/merchants/{m_resp.json()['id']}/shops",
        json={"name": "越权测试门店"},
        headers=headers,
    )
    assert s_resp.status_code == 201, s_resp.text
    return s_resp.json()["id"]


def test_cross_user_shop_access_rejected(client):
    owner_headers = _register(client, f"owner-{uuid.uuid4()}@test.com")
    intruder_headers = _register(client, f"intruder-{uuid.uuid4()}@test.com")
    shop_id = _create_shop(client, owner_headers)

    assert client.get(f"/api/v1/shops/{shop_id}", headers=intruder_headers).status_code == 404
    assert (
        client.patch(
            f"/api/v1/shops/{shop_id}",
            json={"name": "被篡改"},
            headers=intruder_headers,
        ).status_code
        == 404
    )
    assert client.delete(f"/api/v1/shops/{shop_id}", headers=intruder_headers).status_code == 404
    assert (
        client.get(f"/api/v1/shops/{shop_id}/platforms", headers=intruder_headers).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/shops/{shop_id}/platforms",
            json={"platform": "xiaohongshu", "shop_url": "https://example.com"},
            headers=intruder_headers,
        ).status_code
        == 404
    )

    owner_resp = client.get(f"/api/v1/shops/{shop_id}", headers=owner_headers)
    assert owner_resp.status_code == 200
    assert owner_resp.json()["name"] == "越权测试门店"


def test_subscription_snapshots_require_owner(client):
    owner_headers = _register(client, f"sub-owner-{uuid.uuid4()}@test.com")
    intruder_headers = _register(client, f"sub-intruder-{uuid.uuid4()}@test.com")

    sub_resp = client.post(
        "/api/v1/subscriptions",
        json={"xhs_user_id": "xhs-1", "nickname": "博主"},
        headers=owner_headers,
    )
    assert sub_resp.status_code == 201, sub_resp.text
    sub_id = sub_resp.json()["id"]

    assert (
        client.get(f"/api/v1/subscriptions/{sub_id}/snapshots", headers=intruder_headers).status_code
        == 404
    )
    assert (
        client.get(f"/api/v1/subscriptions/{sub_id}/snapshots", headers=owner_headers).status_code
        == 200
    )


def test_image_proxy_rejects_non_xhs_urls(client, monkeypatch):
    local_url = "http://127.0.0.1:3000/login"
    assert (
        client.get("/api/v1/images/proxy", params={"url": local_url}).status_code == 400
    )

    class FakeResponse:
        status_code = 200
        headers = {"content-type": "image/webp"}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def iter_content(self, chunk_size):
            yield b"fake-image-bytes"

    monkeypatch.setattr(
        "app.api.v1.images.requests.get",
        lambda *args, **kwargs: FakeResponse(),
    )
    resp = client.get(
        "/api/v1/images/proxy",
        params={"url": "https://ci.xiaohongshu.com/note.webp"},
    )
    assert resp.status_code == 200
    assert resp.content == b"fake-image-bytes"


def test_crawl_jobs_isolated_by_user():
    job_id = tasks.dispatch_job("unknown", {}, user_id="user-a")

    assert [j["id"] for j in tasks.list_tasks("user-a")] == [job_id]
    assert tasks.list_tasks("user-b") == []
    assert tasks.get_task(job_id, "user-a") is not None
    assert tasks.get_task(job_id, "user-b") is None


def test_crawl_job_invalid_params_fails():
    job_id = tasks.dispatch_job("note_detail", {}, user_id="user-c")
    time.sleep(0.2)
    job = tasks.get_task(job_id, "user-c")
    assert job is not None
    assert job["status"] == "failed"


def test_image_proxy_rejects_redirect(client, monkeypatch):
    class RedirectResponse:
        status_code = 302
        headers = {"location": "http://127.0.0.1:8000/ping"}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def iter_content(self, chunk_size):
            return iter(())

    monkeypatch.setattr(
        "app.api.v1.images.requests.get",
        lambda *args, **kwargs: RedirectResponse(),
    )
    resp = client.get(
        "/api/v1/images/proxy",
        params={"url": "https://ci.xiaohongshu.com/note.webp"},
    )
    assert resp.status_code == 502


def test_empty_password_rejected(client):
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"weak-{uuid.uuid4()}@test.com",
            "password": "",
            "name": "Weak",
        },
    )
    assert resp.status_code == 422


def test_login_rate_limit_blocks_after_threshold():
    from app.api.v1.auth import _check_login_rate

    email = f"rate-{uuid.uuid4()}@test.com"
    for _ in range(200):
        assert _check_login_rate(email, "1.2.3.4")
    assert not _check_login_rate(email, "1.2.3.4")
    assert _check_login_rate(email, "5.6.7.8")


def test_security_headers_present(client):
    resp = client.get("/ping")
    assert resp.status_code == 200
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "DENY"
    assert resp.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert resp.headers["cross-origin-opener-policy"] == "same-origin"
