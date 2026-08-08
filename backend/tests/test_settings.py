"""设置 API 测试：保存位置、API 密钥脱敏、用户信息更新。"""
from __future__ import annotations

import uuid

import pytest


@pytest.fixture(autouse=True)
def _isolate_settings(tmp_path, monkeypatch):
    """设置写入临时文件，并恢复被改动过的运行时配置，避免污染其他测试。"""
    from app.core.config import settings as app_settings
    from app.services import runtime_settings

    monkeypatch.setattr(runtime_settings, "SETTINGS_FILE", tmp_path / "settings.json")
    runtime_settings.reset()
    keys = (
        "LOCAL_STORAGE_DIR",
        "DEEPSEEK_API_KEY",
        "DEEPSEEK_BASE_URL",
        "DEEPSEEK_MODEL",
        "VOLCENGINE_API_KEY",
        "VOLCENGINE_BASE_URL",
        "VOLCENGINE_IMAGE_MODEL",
        "VOLCENGINE_VISION_MODEL",
        "VIDEO_API_KEY",
        "VIDEO_API_BASE_URL",
        "VIDEO_API_MODEL",
    )
    before = {k: getattr(app_settings, k) for k in keys}
    yield
    runtime_settings.reset()
    for key, value in before.items():
        setattr(app_settings, key, value)


def _register(client) -> dict:
    email = f"settings-{uuid.uuid4().hex[:8]}@test.com"
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "password123", "name": "设置测试"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_settings_get_and_update(client, tmp_path):
    token = _register(client)["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.get("/api/v1/settings", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert {"storage", "text", "image", "video"} <= set(data)
    assert "api_key" not in str(data)

    body = {
        "storage_dir": str(tmp_path / "media"),
        "text": {
            "api_key": "sk-test-1234567890",
            "base_url": "https://api.deepseek.com",
            "model": "deepseek-chat",
        },
        "image": {
            "api_key": "",
            "base_url": "https://ark.cn-beijing.volces.com/api/v3",
            "model": "doubao-image",
        },
        "video": {"api_key": "video-key-abcdef", "base_url": "", "model": ""},
    }
    resp = client.put("/api/v1/settings", json=body, headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["text"]["configured"] is True
    assert data["text"]["preview"] is not None
    assert "sk-test-1234567890" not in str(data)
    assert data["image"]["configured"] is False
    assert data["video"]["configured"] is True
    assert (tmp_path / "settings.json").exists()


def test_update_user_info(client):
    token = _register(client)["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.put(
        "/api/v1/auth/me",
        json={"name": "新名字", "new_password": "newpass123"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == "新名字"

    login = client.post(
        "/api/v1/auth/login",
        json={"email": resp.json()["email"], "password": "newpass123"},
    )
    assert login.status_code == 200, login.text