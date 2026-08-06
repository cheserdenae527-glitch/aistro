"""P1 装修模块自动化测试 — 覆盖乐观锁、频控、original_url 语义、敏感词过滤。

运行方式：
    cd D:\two\backend
    pytest tests/test_profile.py -v

需要数据库 + Redis + MinIO 运行中（docker compose up -d）。
"""
from __future__ import annotations

import base64
import io
import uuid
from urllib.parse import urlparse

import pytest
from PIL import Image


# ============================================================
# 1. 乐观锁并发更新 -> 409
# ============================================================

def test_optimistic_lock(client):
    shop_id = _create_test_shop(client)

    get_resp = client.get(
        f"/api/v1/shops/{shop_id}/profiles/xiaohongshu",
        headers=auth_headers(client),
    )
    assert get_resp.status_code == 200
    version = get_resp.json()["version"]

    # 第一次 PUT -> 成功
    put1 = client.put(
        f"/api/v1/shops/{shop_id}/profiles/xiaohongshu",
        json={"nickname": "测试昵称1", "version": version},
        headers=auth_headers(client),
    )
    assert put1.status_code == 200
    assert put1.json()["version"] == version + 1

    # 第二次 PUT 带旧 version -> 409
    put2 = client.put(
        f"/api/v1/shops/{shop_id}/profiles/xiaohongshu",
        json={"nickname": "测试昵称2", "version": version},
        headers=auth_headers(client),
    )
    assert put2.status_code == 409


# ============================================================
# 2. 频控触发 -> 429
# ============================================================

def test_rate_limit_generate(client, monkeypatch):
    shop_id = _create_test_shop(client)
    body = {"category": "火锅", "style": "市井烟火", "price_range": "人均80"}

    async def _stub_generate_variants(category, style, price_range):
        return [], "{}"

    monkeypatch.setattr(
        "app.api.v1.profiles.generate_variants", _stub_generate_variants
    )

    # 连续两次调用，第二次应被频控
    resp1 = client.post(
        f"/api/v1/shops/{shop_id}/profiles/xiaohongshu/generate",
        json=body,
        headers=auth_headers(client),
    )
    assert resp1.status_code == 200

    resp2 = client.post(
        f"/api/v1/shops/{shop_id}/profiles/xiaohongshu/generate",
        json=body,
        headers=auth_headers(client),
    )
    assert resp2.status_code == 429


# ============================================================
# 3. 敏感词过滤 - prompt -> 422
# ============================================================

def test_sensitive_prompt_rejected(client):
    shop_id = _create_test_shop(client)
    resp = client.post(
        f"/api/v1/shops/{shop_id}/profiles/xiaohongshu/generate",
        json={"category": "色情", "style": "暴力", "price_range": "人均80"},
        headers=auth_headers(client),
    )
    assert resp.status_code == 422


def test_sensitive_nickname_rejected(client):
    shop_id = _create_test_shop(client)
    get_resp = client.get(
        f"/api/v1/shops/{shop_id}/profiles/xiaohongshu",
        headers=auth_headers(client),
    )
    version = get_resp.json()["version"]

    resp = client.put(
        f"/api/v1/shops/{shop_id}/profiles/xiaohongshu",
        json={"nickname": "赌博平台", "version": version},
        headers=auth_headers(client),
    )
    assert resp.status_code == 422


def test_sensitive_bio_rejected(client):
    shop_id = _create_test_shop(client)
    get_resp = client.get(
        f"/api/v1/shops/{shop_id}/profiles/xiaohongshu",
        headers=auth_headers(client),
    )
    version = get_resp.json()["version"]

    resp = client.put(
        f"/api/v1/shops/{shop_id}/profiles/xiaohongshu",
        json={"bio": "加我微信刷单赚钱", "version": version},
        headers=auth_headers(client),
    )
    assert resp.status_code == 422


# ============================================================
# 3.5 敏感词后处理 — filtered / bio_flagged 边界
# ============================================================

def test_variant_filtered_when_all_nicknames_blocked():
    from app.ai.profile_agent import _sanitize_variants

    variants = _sanitize_variants([
        {
            "id": "A",
            "nickname_options": ["赌博", "刷单"],
            "bio": "正常简介",
            "avatar_prompt": "a",
            "bg_prompt": "b",
        }
    ])
    assert len(variants) == 4
    assert variants[0].filtered is True
    assert variants[0].nickname_options == []
    assert variants[0].bio_flagged is False


def test_variant_bio_flagged_when_bio_blocked():
    from app.ai.profile_agent import _sanitize_variants

    variants = _sanitize_variants([
        {
            "id": "B",
            "nickname_options": ["正常昵称"],
            "bio": "加我微信刷单赚钱",
            "avatar_prompt": "a",
            "bg_prompt": "b",
        }
    ])
    assert variants[0].bio_flagged is True
    assert variants[0].bio == "[内容待审核]"
    # 昵称候选有效时，方案本身仍可用
    assert variants[0].filtered is False


# ============================================================
# 4. original_url 语义验证
# ============================================================

def test_original_url_semantic(client):
    shop_id = _create_test_shop(client)

    get_resp = client.get(
        f"/api/v1/shops/{shop_id}/profiles/xiaohongshu",
        headers=auth_headers(client),
    )
    assert get_resp.status_code == 200
    profile = get_resp.json()
    assert profile["avatar_original_url"] is None
    assert profile["avatar_url"] is None

    # 上传测试图
    img = Image.new("RGB", (100, 100), color=(255, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    upload = client.post(
        f"/api/v1/shops/{shop_id}/profiles/xiaohongshu/upload-avatar",
        files={"file": ("test.png", buf, "image/png")},
        headers=auth_headers(client),
    )
    if upload.status_code == 200:
        get2 = client.get(
            f"/api/v1/shops/{shop_id}/profiles/xiaohongshu",
            headers=auth_headers(client),
        )
        p2 = get2.json()
        assert p2["avatar_original_url"] is not None

        # 裁剪
        buf.seek(0)
        b64 = base64.b64encode(buf.read()).decode()
        crop = client.post(
            f"/api/v1/shops/{shop_id}/profiles/xiaohongshu/crop-avatar",
            json={"image_base64": b64},
            headers=auth_headers(client),
        )
        if crop.status_code == 200:
            get3 = client.get(
                f"/api/v1/shops/{shop_id}/profiles/xiaohongshu",
                headers=auth_headers(client),
            )
            p3 = get3.json()
            assert p3["avatar_url"] is not None
            # 预签名 URL 每次签名不同，比较对象路径即可
            assert urlparse(p3["avatar_original_url"]).path == urlparse(
                p2["avatar_original_url"]
            ).path


# ============================================================
# 5. 匿名 -> 401
# ============================================================

def test_anonymous_401(client):
    fake_id = str(uuid.uuid4())
    resp = client.get(f"/api/v1/shops/{fake_id}/profiles/xiaohongshu")
    assert resp.status_code == 401


# ============================================================
# 6. 跨用户 -> 404
# ============================================================

def test_cross_user_404(client):
    fake_id = str(uuid.uuid4())
    resp = client.get(
        f"/api/v1/shops/{fake_id}/profiles/xiaohongshu",
        headers=auth_headers(client),
    )
    assert resp.status_code == 404


# ============================================================
# 7. 色板 API
# ============================================================

def test_color_schemes(client):
    resp = client.get("/api/v1/color-schemes")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 8
    assert data[0]["name"] == "暖冬橘"


# ============================================================
# 8. 敏感词过滤单元测试
# ============================================================

def test_sensitive_filter_unit():
    from app.core.sensitive_filter import contains_blocked, filter_text

    assert not contains_blocked("正常文本")
    assert not contains_blocked("")
    assert contains_blocked("刷单赚钱")

    result, flagged = filter_text("正常内容")
    assert not flagged
    assert result == "正常内容"

    result, flagged = filter_text("刷单兼职")
    assert flagged
    assert result == "[内容待审核]"


# ============================================================
# 9. 单板块提示词请求 Schema
# ============================================================

def test_generate_prompt_request_schema():
    from pydantic import ValidationError

    from app.schemas.profile import PromptGenerateRequest

    req = PromptGenerateRequest(
        section="avatar", category="火锅", style="市井烟火", price_range="人均80"
    )
    assert req.section == "avatar"

    with pytest.raises(ValidationError):
        PromptGenerateRequest(
            section="header", category="火锅", style="市井烟火", price_range="人均80"
        )

    with pytest.raises(ValidationError):
        PromptGenerateRequest(
            section="bg", category="刷单", style="市井烟火", price_range="人均80"
        )


# ============================================================
# Helpers
# ============================================================

def auth_headers(client) -> dict:
    """获取认证 header。"""
    resp = client.post("/api/v1/auth/login", json={
        "email": "admin@test.com",
        "password": "admin123",
    })
    if resp.status_code != 200:
        client.post("/api/v1/auth/register", json={
            "email": "admin@test.com",
            "password": "admin123",
            "name": "Test Admin",
        })
        resp = client.post("/api/v1/auth/login", json={
            "email": "admin@test.com",
            "password": "admin123",
        })
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _create_test_shop(client) -> str:
    """创建测试商家+门店，返回 shop_id。"""
    m_resp = client.post(
        "/api/v1/merchants",
        json={"name": "测试商家"},
        headers=auth_headers(client),
    )
    mid = m_resp.json()["id"]
    s_resp = client.post(
        f"/api/v1/merchants/{mid}/shops",
        json={"name": "测试门店"},
        headers=auth_headers(client),
    )
    return s_resp.json()["id"]

# ============================================================
# 10. 置顶笔记 / 体检重写 Schema
# ============================================================

def test_pinned_notes_schema():
    from pydantic import ValidationError

    from app.schemas.profile import (
        HealthRewriteRequest,
        PinnedNote,
        ProfileUpdate,
    )

    note = PinnedNote(title="巷子口老灶火锅点单攻略", content="人均80吃撑，评论区问地址")
    assert note.title == "巷子口老灶火锅点单攻略"

    upd = ProfileUpdate(version=1, pinned_notes=[note])
    assert upd.pinned_notes[0].content == "人均80吃撑，评论区问地址"

    with pytest.raises(ValidationError):
        PinnedNote(title="x" * 41)

    rewrite = HealthRewriteRequest(
        nickname="巷子口老灶火锅",
        bio="人均80吃撑",
        weaknesses=["目标用户不清晰"],
        suggestions=["写明学生党聚餐首选"],
    )
    assert rewrite.weaknesses == ["目标用户不清晰"]
    assert rewrite.suggestions == ["写明学生党聚餐首选"]

def test_pinned_notes_persist(client):
    shop_id = _create_test_shop(client)

    get_resp = client.get(
        f"/api/v1/shops/{shop_id}/profiles/xiaohongshu",
        headers=auth_headers(client),
    )
    assert get_resp.status_code == 200
    version = get_resp.json()["version"]

    note = {"title": "人均80吃市井火锅", "content": "点单攻略看这条，照着吃不出错"}
    put = client.put(
        f"/api/v1/shops/{shop_id}/profiles/xiaohongshu",
        json={"version": version, "pinned_notes": [note]},
        headers=auth_headers(client),
    )
    assert put.status_code == 200
    assert put.json()["pinned_notes"][0]["title"] == "人均80吃市井火锅"

    get2 = client.get(
        f"/api/v1/shops/{shop_id}/profiles/xiaohongshu",
        headers=auth_headers(client),
    )
    assert get2.json()["pinned_notes"][0]["content"] == "点单攻略看这条，照着吃不出错"

def test_profile_options_request_schema():
    from pydantic import ValidationError

    from app.schemas.profile import ProfileOptionsGenerateRequest

    req = ProfileOptionsGenerateRequest(
        kind="nickname", category="火锅", style="市井烟火", price_range="人均80"
    )
    assert req.kind == "nickname"

    with pytest.raises(ValidationError):
        ProfileOptionsGenerateRequest(
            kind="avatar", category="火锅", style="市井烟火", price_range="人均80"
        )
