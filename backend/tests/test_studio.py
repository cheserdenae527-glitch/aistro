"""S1 内容工坊后端测试。

运行方式：
    cd D:\two\backend
    pytest tests/test_studio.py -v

需要 Postgres + Redis + MinIO 运行中（docker compose up -d）。
真实渲染测试（Playwright + Chromium）在 chromium 可用时自动运行。
"""
from __future__ import annotations

import base64
import io
import json
import uuid

import httpx

import pytest
from PIL import Image

from app.ai.studio_copy import StudioAgentError
from app.ai.studio_paginate import StudioPaginateError


def _make_png(size=(1080, 1440), color=(210, 110, 50)) -> bytes:
    img = Image.new("RGB", size, color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _png_upload(name: str = "dish.png") -> tuple[str, io.BytesIO, str]:
    buf = io.BytesIO(_make_png((64, 64)))
    buf.seek(0)
    return name, buf, "image/png"


def auth_headers(client) -> dict:
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


def _create_shop(client) -> str:
    headers = auth_headers(client)
    m_resp = client.post(
        "/api/v1/merchants",
        json={"name": "测试商家"},
        headers=headers,
    )
    mid = m_resp.json()["id"]
    s_resp = client.post(
        f"/api/v1/merchants/{mid}/shops",
        json={"name": "测试门店"},
        headers=headers,
    )
    return s_resp.json()["id"]


def _create_project(client, shop_id: str | None = None, title: str = "测试工坊项目") -> dict:
    headers = auth_headers(client)
    shop_id = shop_id or _create_shop(client)
    resp = client.post(
        "/api/v1/studio/projects",
        json={"shop_id": shop_id, "title": title},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _create_design_asset(client, shop_id: str) -> dict:
    """在视觉设计模块创建一张素材图（供 asset_ids 引用）。"""
    headers = auth_headers(client)
    resp = client.post(
        "/api/v1/design-projects",
        json={"shop_id": shop_id, "title": "素材项目"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    dp = resp.json()
    name, buf, mime = _png_upload()
    resp = client.post(
        f"/api/v1/design-projects/{dp['id']}/assets",
        data={"asset_type": "photo", "dish_name": "招牌菜"},
        files={"file": (name, buf, mime)},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _stub_copy_generate(self, category, style, price_range, topic, shop_name):
    return {
        "titles": [{"text": f"探店标题{i}号", "strategy": "痛点共鸣"} for i in range(5)],
        "body": "这是一段测试正文，讲这家店的市井烟火气和人均消费。" * 30,
        "tags": ["成都美食", "火锅探店", "人均80", "市井烟火", "周末去哪儿"],
        "image_guide": {
            "cover_prompt": "封面图提示词",
            "pages": [
                {"position": "第1段后", "purpose": "辅助说明", "prompt": "配图提示词"}
            ],
        },
    }


async def _stub_paginate(self, body, page_count, image_count):
    specs = []
    for i in range(page_count):
        specs.append(
            {
                "title": f"第{i + 1}页观点标题足够长",
                "bullets": ["要点一", "要点二", "要点三"],
                "image_index": 0 if image_count else None,
            }
        )
    return specs


def _stub_render_pages(htmls):
    png = _make_png()
    return [
        {
            "png": png,
            "metrics": {
                "client_height": 1440,
                "scroll_height": 1440,
                "overflow": 0,
                "bottom_gap": 88,
            },
        }
        for _ in htmls
    ]


async def _no_rate_limit(*args, **kwargs):
    return True


def _make_copy(client, project_id: str) -> dict:
    """在已 stub agent 的前提下生成文案并返回 copy。"""
    headers = auth_headers(client)
    resp = client.post(
        f"/api/v1/studio/projects/{project_id}/copy/generate",
        json={
            "category": "市井火锅",
            "style": "烟火气",
            "price_range": "人均80",
            "topic": "藏在巷子里的宝藏火锅",
            "shop_name": "蜀香里火锅",
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


# ============================================================
# 项目 CRUD / 鉴权
# ============================================================


def test_project_crud(client):
    project = _create_project(client)
    pid = project["id"]
    headers = auth_headers(client)

    get_resp = client.get(f"/api/v1/studio/projects/{pid}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["title"] == "测试工坊项目"

    list_resp = client.get(
        f"/api/v1/studio/projects?shop_id={project['shop_id']}",
        headers=headers,
    )
    assert list_resp.status_code == 200
    assert any(p["id"] == pid for p in list_resp.json())

    patch_resp = client.patch(
        f"/api/v1/studio/projects/{pid}",
        json={"title": "改名项目", "status": "generated"},
        headers=headers,
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["status"] == "generated"

    del_resp = client.delete(f"/api/v1/studio/projects/{pid}", headers=headers)
    assert del_resp.status_code == 200
    assert client.get(
        f"/api/v1/studio/projects/{pid}", headers=headers
    ).status_code == 404


def test_project_requires_auth(client):
    assert client.get("/api/v1/studio/projects").status_code == 401


def test_project_cross_user_404(client):
    project = _create_project(client)

    other = client.post("/api/v1/auth/register", json={
        "email": "other@test.com",
        "password": "admin123",
        "name": "Other",
    })
    if other.status_code not in (200, 201):
        pass
    other_login = client.post("/api/v1/auth/login", json={
        "email": "other@test.com",
        "password": "admin123",
    })
    other_headers = {"Authorization": f"Bearer {other_login.json()['access_token']}"}

    assert client.get(
        f"/api/v1/studio/projects/{project['id']}", headers=other_headers
    ).status_code == 404


# ============================================================
# 文案生成
# ============================================================


def test_copy_generate_and_persist(client, monkeypatch):
    monkeypatch.setattr(
        "app.ai.studio_copy.StudioCopyAgent.generate", _stub_copy_generate
    )
    monkeypatch.setattr("app.api.v1.studio.check_rate_limit", _no_rate_limit)
    project = _create_project(client)
    data = _make_copy(client, project["id"])

    assert len(data["titles"]) == 5
    assert all(t["text"] and t["strategy"] for t in data["titles"])
    assert 300 <= len(data["body"]) <= 800
    assert 5 <= len(data["tags"]) <= 10
    assert data["image_guide"]["cover_prompt"]
    assert data["image_guide"]["pages"]

    # copy 已持久化，项目详情包含 copies
    detail = client.get(
        f"/api/v1/studio/projects/{project['id']}",
        headers=auth_headers(client),
    ).json()
    assert any(c["id"] == data["id"] for c in detail["copies"])
    assert detail["status"] == "generated"


def test_copy_generate_sensitive_input_422(client, monkeypatch):
    monkeypatch.setattr(
        "app.ai.studio_copy.StudioCopyAgent.generate", _stub_copy_generate
    )
    project = _create_project(client)
    resp = client.post(
        f"/api/v1/studio/projects/{project['id']}/copy/generate",
        json={
            "category": "市井火锅",
            "style": "烟火气",
            "price_range": "人均80",
            "topic": "赌博推荐",
            "shop_name": "蜀香里火锅",
        },
        headers=auth_headers(client),
    )
    assert resp.status_code == 422


def test_copy_generate_rate_limit_429(client, monkeypatch):
    async def _limited(*args, **kwargs):
        return False

    monkeypatch.setattr(
        "app.ai.studio_copy.StudioCopyAgent.generate", _stub_copy_generate
    )
    monkeypatch.setattr("app.api.v1.studio.check_rate_limit", _limited)
    project = _create_project(client)
    resp = client.post(
        f"/api/v1/studio/projects/{project['id']}/copy/generate",
        json={
            "category": "市井火锅",
            "style": "烟火气",
            "price_range": "人均80",
            "topic": "宝藏火锅",
            "shop_name": "蜀香里火锅",
        },
        headers=auth_headers(client),
    )
    assert resp.status_code == 429


def test_copy_generate_agent_error_502(client, monkeypatch):
    async def _bad(self, **kwargs):
        raise StudioAgentError("LLM 返回标题数量不是 5 条")

    monkeypatch.setattr("app.ai.studio_copy.StudioCopyAgent.generate", _bad)
    monkeypatch.setattr("app.api.v1.studio.check_rate_limit", _no_rate_limit)
    project = _create_project(client)
    resp = client.post(
        f"/api/v1/studio/projects/{project['id']}/copy/generate",
        json={
            "category": "市井火锅",
            "style": "烟火气",
            "price_range": "人均80",
            "topic": "宝藏火锅",
            "shop_name": "蜀香里火锅",
        },
        headers=auth_headers(client),
    )
    assert resp.status_code == 502


def test_copy_generate_blocked_output_422(client, monkeypatch):
    async def _blocked(self, **kwargs):
        raise StudioAgentError("生成内容包含敏感词")

    monkeypatch.setattr("app.ai.studio_copy.StudioCopyAgent.generate", _blocked)
    monkeypatch.setattr("app.api.v1.studio.check_rate_limit", _no_rate_limit)
    project = _create_project(client)
    resp = client.post(
        f"/api/v1/studio/projects/{project['id']}/copy/generate",
        json={
            "category": "市井火锅",
            "style": "烟火气",
            "price_range": "人均80",
            "topic": "宝藏火锅",
            "shop_name": "蜀香里火锅",
        },
        headers=auth_headers(client),
    )
    assert resp.status_code == 422


def test_copy_update(client, monkeypatch):
    monkeypatch.setattr(
        "app.ai.studio_copy.StudioCopyAgent.generate", _stub_copy_generate
    )
    monkeypatch.setattr("app.api.v1.studio.check_rate_limit", _no_rate_limit)
    project = _create_project(client)
    copy = _make_copy(client, project["id"])
    resp = client.patch(
        f"/api/v1/studio/copies/{copy['id']}",
        json={"body": "手动修改后的正文，字数达标。" * 30},
        headers=auth_headers(client),
    )
    assert resp.status_code == 200
    assert "手动修改后的正文" in resp.json()["body"]


# ============================================================
# 卡组生成
# ============================================================


def test_deck_generate_json_with_assets(client, monkeypatch):
    monkeypatch.setattr(
        "app.ai.studio_copy.StudioCopyAgent.generate", _stub_copy_generate
    )
    monkeypatch.setattr(
        "app.ai.studio_paginate.StudioPaginateAgent.paginate", _stub_paginate
    )
    monkeypatch.setattr("app.api.v1.studio.render_pages", _stub_render_pages)
    monkeypatch.setattr("app.api.v1.studio.check_rate_limit", _no_rate_limit)

    shop_id = _create_shop(client)
    project = _create_project(client, shop_id=shop_id)
    copy = _make_copy(client, project["id"])
    asset = _create_design_asset(client, shop_id)

    resp = client.post(
        f"/api/v1/studio/projects/{project['id']}/decks",
        json={
            "copy_id": copy["id"],
            "template": "editorial",
            "theme": "ink-classic",
            "page_count": 4,
            "asset_ids": [asset["id"]],
        },
        headers=auth_headers(client),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "rendered"
    assert len(data["images"]) == 4
    assert data["images"][0]["width"] == 1080
    assert data["images"][0]["height"] == 1440
    assert all(img["url"].startswith("http") for img in data["images"])
    assert data["qa_report"]["all_pass"] is True
    assert len(data["qa_report"]["pages"]) == 4

    # 详情返回（含 source_assets 引用）
    detail = client.get(
        f"/api/v1/studio/decks/{data['deck_id']}",
        headers=auth_headers(client),
    ).json()
    assert detail["template"] == "editorial"
    assert detail["source_assets"][0]["source"] == "design"
    assert detail["images"][0]["url"].startswith("http")


def test_deck_generate_multipart(client, monkeypatch):
    monkeypatch.setattr(
        "app.ai.studio_copy.StudioCopyAgent.generate", _stub_copy_generate
    )
    monkeypatch.setattr(
        "app.ai.studio_paginate.StudioPaginateAgent.paginate", _stub_paginate
    )
    monkeypatch.setattr("app.api.v1.studio.render_pages", _stub_render_pages)
    monkeypatch.setattr("app.api.v1.studio.check_rate_limit", _no_rate_limit)

    project = _create_project(client)
    copy = _make_copy(client, project["id"])
    files = []
    for i in range(3):
        name, buf, mime = _png_upload(f"img{i}.png")
        files.append(("files", (name, buf, mime)))

    resp = client.post(
        f"/api/v1/studio/projects/{project['id']}/decks",
        data={
            "copy_id": copy["id"],
            "template": "swiss",
            "theme": "ikb-blue",
            "page_count": 4,
        },
        files=files,
        headers=auth_headers(client),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "rendered"
    assert len(data["images"]) == 4

    # 确认 multipart 上传素材被引用
    detail = client.get(
        f"/api/v1/studio/decks/{data['deck_id']}",
        headers=auth_headers(client),
    ).json()
    assert len(detail["source_assets"]) == 3
    assert all(a["source"] == "upload" for a in detail["source_assets"])


def test_deck_page_count_out_of_range_400(client, monkeypatch):
    project = _create_project(client)
    resp = client.post(
        f"/api/v1/studio/projects/{project['id']}/decks",
        json={
            "copy_id": str(uuid.uuid4()),
            "template": "editorial",
            "theme": "ink-classic",
            "page_count": 9,
            "asset_ids": [],
        },
        headers=auth_headers(client),
    )
    assert resp.status_code == 400
    assert "page_count" in resp.json()["detail"]


def test_deck_unknown_theme_400(client, monkeypatch):
    monkeypatch.setattr(
        "app.ai.studio_copy.StudioCopyAgent.generate", _stub_copy_generate
    )
    monkeypatch.setattr("app.api.v1.studio.check_rate_limit", _no_rate_limit)
    project = _create_project(client)
    copy = _make_copy(client, project["id"])
    resp = client.post(
        f"/api/v1/studio/projects/{project['id']}/decks",
        json={
            "copy_id": copy["id"],
            "template": "editorial",
            "theme": "no-such-theme",
            "page_count": 4,
            "asset_ids": [],
        },
        headers=auth_headers(client),
    )
    assert resp.status_code == 400


def test_deck_cross_shop_asset_404(client, monkeypatch):
    monkeypatch.setattr("app.api.v1.studio.check_rate_limit", _no_rate_limit)
    shop_a = _create_shop(client)
    asset_a = _create_design_asset(client, shop_a)

    project = _create_project(client)  # 新 shop
    resp = client.post(
        f"/api/v1/studio/projects/{project['id']}/decks",
        json={
            "copy_id": str(uuid.uuid4()),
            "template": "editorial",
            "theme": "ink-classic",
            "page_count": 4,
            "asset_ids": [asset_a["id"]],
        },
        headers=auth_headers(client),
    )
    assert resp.status_code == 404


def test_deck_upload_invalid_mime_400(client, monkeypatch):
    monkeypatch.setattr(
        "app.ai.studio_copy.StudioCopyAgent.generate", _stub_copy_generate
    )
    monkeypatch.setattr("app.api.v1.studio.check_rate_limit", _no_rate_limit)
    project = _create_project(client)
    copy = _make_copy(client, project["id"])
    resp = client.post(
        f"/api/v1/studio/projects/{project['id']}/decks",
        data={
            "copy_id": copy["id"],
            "template": "editorial",
            "theme": "ink-classic",
            "page_count": 4,
        },
        files={"files": ("bad.txt", io.BytesIO(b"not image"), "text/plain")},
        headers=auth_headers(client),
    )
    assert resp.status_code == 400


def test_deck_upload_too_many_files_400(client, monkeypatch):
    monkeypatch.setattr(
        "app.ai.studio_copy.StudioCopyAgent.generate", _stub_copy_generate
    )
    monkeypatch.setattr("app.api.v1.studio.check_rate_limit", _no_rate_limit)
    project = _create_project(client)
    copy = _make_copy(client, project["id"])
    files = []
    for i in range(9):
        name, buf, mime = _png_upload(f"img{i}.png")
        files.append(("files", (name, buf, mime)))
    resp = client.post(
        f"/api/v1/studio/projects/{project['id']}/decks",
        data={
            "copy_id": copy["id"],
            "template": "editorial",
            "theme": "ink-classic",
            "page_count": 4,
        },
        files=files,
        headers=auth_headers(client),
    )
    assert resp.status_code == 400


def test_deck_rate_limit_429(client, monkeypatch):
    async def _limited(*args, **kwargs):
        return False

    monkeypatch.setattr("app.api.v1.studio.check_rate_limit", _limited)
    project = _create_project(client)
    resp = client.post(
        f"/api/v1/studio/projects/{project['id']}/decks",
        json={
            "copy_id": str(uuid.uuid4()),
            "template": "editorial",
            "theme": "ink-classic",
            "page_count": 4,
            "asset_ids": [],
        },
        headers=auth_headers(client),
    )
    assert resp.status_code == 429


def test_deck_paginate_error_502(client, monkeypatch):
    async def _bad(self, body, page_count, image_count):
        raise StudioPaginateError("LLM 返回页数 2 不等于 4")

    monkeypatch.setattr(
        "app.ai.studio_copy.StudioCopyAgent.generate", _stub_copy_generate
    )
    monkeypatch.setattr(
        "app.ai.studio_paginate.StudioPaginateAgent.paginate", _bad
    )
    monkeypatch.setattr("app.api.v1.studio.check_rate_limit", _no_rate_limit)
    project = _create_project(client)
    copy = _make_copy(client, project["id"])
    resp = client.post(
        f"/api/v1/studio/projects/{project['id']}/decks",
        json={
            "copy_id": copy["id"],
            "template": "editorial",
            "theme": "ink-classic",
            "page_count": 4,
            "asset_ids": [],
        },
        headers=auth_headers(client),
    )
    assert resp.status_code == 502


def test_deck_generate_multipart_with_asset_ids(client, monkeypatch):
    """multipart 模式下素材库引用 + 直接上传可同时使用。"""
    monkeypatch.setattr(
        "app.ai.studio_copy.StudioCopyAgent.generate", _stub_copy_generate
    )
    monkeypatch.setattr(
        "app.ai.studio_paginate.StudioPaginateAgent.paginate", _stub_paginate
    )
    monkeypatch.setattr("app.api.v1.studio.render_pages", _stub_render_pages)
    monkeypatch.setattr("app.api.v1.studio.check_rate_limit", _no_rate_limit)

    shop_id = _create_shop(client)
    project = _create_project(client, shop_id=shop_id)
    copy = _make_copy(client, project["id"])
    asset = _create_design_asset(client, shop_id)

    files = []
    for i in range(2):
        name, buf, mime = _png_upload(f"up{i}.png")
        files.append(("files", (name, buf, mime)))

    resp = client.post(
        f"/api/v1/studio/projects/{project['id']}/decks",
        data={
            "copy_id": copy["id"],
            "template": "editorial",
            "theme": "ink-classic",
            "page_count": 4,
            "asset_ids": json.dumps([asset["id"]]),
        },
        files=files,
        headers=auth_headers(client),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "rendered"

    detail = client.get(
        f"/api/v1/studio/decks/{resp.json()['deck_id']}",
        headers=auth_headers(client),
    ).json()
    sources = [a["source"] for a in detail["source_assets"]]
    assert sources.count("upload") == 2
    assert sources.count("design") == 1


def test_deck_paginate_openai_rate_limit_429(client, monkeypatch):
    """DeepSeek 429（RateLimitError）应返回 429 而非 500。"""
    import openai

    async def _rl(self, body, page_count, image_count):
        req = httpx.Request("POST", "http://deepseek.local")
        resp = httpx.Response(429, request=req)
        raise openai.RateLimitError("rate limit", response=resp, body=None)

    monkeypatch.setattr(
        "app.ai.studio_copy.StudioCopyAgent.generate", _stub_copy_generate
    )
    monkeypatch.setattr(
        "app.ai.studio_paginate.StudioPaginateAgent.paginate", _rl
    )
    monkeypatch.setattr("app.api.v1.studio.check_rate_limit", _no_rate_limit)
    project = _create_project(client)
    copy = _make_copy(client, project["id"])
    resp = client.post(
        f"/api/v1/studio/projects/{project['id']}/decks",
        json={
            "copy_id": copy["id"],
            "template": "editorial",
            "theme": "ink-classic",
            "page_count": 4,
            "asset_ids": [],
        },
        headers=auth_headers(client),
    )
    assert resp.status_code == 429


def test_deck_paginate_openai_api_error_502(client, monkeypatch):
    """DeepSeek 网络错误应返回 502 而非 500。"""
    import openai

    async def _conn(self, body, page_count, image_count):
        raise openai.APIConnectionError(request=None)

    monkeypatch.setattr(
        "app.ai.studio_copy.StudioCopyAgent.generate", _stub_copy_generate
    )
    monkeypatch.setattr(
        "app.ai.studio_paginate.StudioPaginateAgent.paginate", _conn
    )
    monkeypatch.setattr("app.api.v1.studio.check_rate_limit", _no_rate_limit)
    project = _create_project(client)
    copy = _make_copy(client, project["id"])
    resp = client.post(
        f"/api/v1/studio/projects/{project['id']}/decks",
        json={
            "copy_id": copy["id"],
            "template": "editorial",
            "theme": "ink-classic",
            "page_count": 4,
            "asset_ids": [],
        },
        headers=auth_headers(client),
    )
    assert resp.status_code == 502


def test_copy_generate_openai_rate_limit_429(client, monkeypatch):
    """文案生成 DeepSeek 429 应返回 429。"""
    import openai

    async def _rl(self, **kwargs):
        req = httpx.Request("POST", "http://deepseek.local")
        resp = httpx.Response(429, request=req)
        raise openai.RateLimitError("rl", response=resp, body=None)

    monkeypatch.setattr("app.ai.studio_copy.StudioCopyAgent.generate", _rl)
    monkeypatch.setattr("app.api.v1.studio.check_rate_limit", _no_rate_limit)
    project = _create_project(client)
    resp = client.post(
        f"/api/v1/studio/projects/{project['id']}/copy/generate",
        json={
            "category": "市井火锅",
            "style": "烟火气",
            "price_range": "人均80",
            "topic": "宝藏火锅",
            "shop_name": "蜀香里火锅",
        },
        headers=auth_headers(client),
    )
    assert resp.status_code == 429




def test_deck_generate_with_pending_ai_candidates(client, monkeypatch):
    """卡组可引用 AI 生成的 pending 候选素材（所有权 + 归属校验不变）。"""
    async def _stub_gen(prompt, ref_data=None, ref_mime="image/png", on_progress=None):
        return [(_make_png((160, 120), (190, 90, 40)), "image/png") for _ in range(4)]

    monkeypatch.setattr("app.api.v1.designs.generate_edited", _stub_gen)
    monkeypatch.setattr(
        "app.ai.studio_copy.StudioCopyAgent.generate", _stub_copy_generate
    )
    monkeypatch.setattr(
        "app.ai.studio_paginate.StudioPaginateAgent.paginate", _stub_paginate
    )
    monkeypatch.setattr("app.api.v1.studio.render_pages", _stub_render_pages)
    monkeypatch.setattr("app.api.v1.studio.check_rate_limit", _no_rate_limit)

    shop_id = _create_shop(client)
    project = _create_project(client, shop_id=shop_id)
    copy = _make_copy(client, project["id"])
    headers = auth_headers(client)

    # 在视觉设计项目里生成 4 张 AI 候选（status=pending）
    dp = client.post(
        "/api/v1/design-projects",
        json={"shop_id": shop_id, "title": "AI 素材"},
        headers=headers,
    ).json()
    gen = client.post(
        f"/api/v1/design-projects/{dp['id']}/assets/generate",
        data={"prompt": "深夜食堂暖光氛围", "asset_type": "photo"},
        headers=headers,
    )
    assert gen.status_code == 200, gen.text
    candidate = gen.json()["candidates"][0]

    resp = client.post(
        f"/api/v1/studio/projects/{project['id']}/decks",
        json={
            "copy_id": copy["id"],
            "template": "editorial",
            "theme": "ink-classic",
            "page_count": 4,
            "asset_ids": [candidate["aid"]],
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "rendered"
    detail = client.get(
        f"/api/v1/studio/decks/{resp.json()['deck_id']}",
        headers=headers,
    ).json()
    assert detail["source_assets"][0]["source"] == "design"
    assert detail["source_assets"][0]["asset_id"] == candidate["aid"]




# ============================================================
# 配图提示词丰富
# ============================================================


def test_enrich_image_prompt_ok(client, monkeypatch):
    """返回提炼的核心想法 + 丰富后的提示词。"""
    from app.ai.studio_image_prompt import StudioImagePromptAgent

    async def _enrich(self, direction, context):
        assert context.get("category") == "市井火锅"
        return {
            "main_idea": "突出火锅沸腾的市井烟火气",
            "prompt": "深夜暖光下沸腾的牛油火锅特写，蒸汽升腾，毛肚黄喉在红汤中翻滚，木桌竹凳，烟火气氛围，电影感侧逆光，3:4 竖版构图",
        }

    monkeypatch.setattr(StudioImagePromptAgent, "enrich", _enrich)
    monkeypatch.setattr("app.api.v1.studio.check_rate_limit", _no_rate_limit)
    monkeypatch.setattr(
        "app.ai.studio_copy.StudioCopyAgent.generate", _stub_copy_generate
    )
    project = _create_project(client)
    copy = _make_copy(client, project["id"])
    resp = client.post(
        f"/api/v1/studio/copies/{copy['id']}/image-prompt/enrich",
        json={"direction": "火锅沸腾，烟火气"},
        headers=auth_headers(client),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["main_idea"]
    assert data["prompt"]
    assert "火锅" in data["prompt"]


def test_enrich_image_prompt_sensitive_422(client, monkeypatch):
    monkeypatch.setattr(
        "app.ai.studio_copy.StudioCopyAgent.generate", _stub_copy_generate
    )
    project = _create_project(client)
    copy = _make_copy(client, project["id"])
    resp = client.post(
        f"/api/v1/studio/copies/{copy['id']}/image-prompt/enrich",
        json={"direction": "赌博广告风格"},
        headers=auth_headers(client),
    )
    assert resp.status_code == 422


def test_enrich_image_prompt_rate_limit_429(client, monkeypatch):
    async def _limited(*args, **kwargs):
        return False

    monkeypatch.setattr(
        "app.ai.studio_copy.StudioCopyAgent.generate", _stub_copy_generate
    )
    monkeypatch.setattr("app.api.v1.studio.check_rate_limit", _no_rate_limit)
    project = _create_project(client)
    copy = _make_copy(client, project["id"])
    monkeypatch.setattr("app.api.v1.studio.check_rate_limit", _limited)
    resp = client.post(
        f"/api/v1/studio/copies/{copy['id']}/image-prompt/enrich",
        json={"direction": "火锅沸腾"},
        headers=auth_headers(client),
    )
    assert resp.status_code == 429


def test_enrich_image_prompt_agent_error_502(client, monkeypatch):
    from app.ai.studio_image_prompt import ImagePromptAgentError, StudioImagePromptAgent

    async def _bad(self, direction, context):
        raise ImagePromptAgentError("LLM 返回内容不完整")

    monkeypatch.setattr(StudioImagePromptAgent, "enrich", _bad)
    monkeypatch.setattr("app.api.v1.studio.check_rate_limit", _no_rate_limit)
    monkeypatch.setattr(
        "app.ai.studio_copy.StudioCopyAgent.generate", _stub_copy_generate
    )
    project = _create_project(client)
    copy = _make_copy(client, project["id"])
    resp = client.post(
        f"/api/v1/studio/copies/{copy['id']}/image-prompt/enrich",
        json={"direction": "火锅沸腾"},
        headers=auth_headers(client),
    )
    assert resp.status_code == 502


def test_enrich_image_prompt_openai_rate_limit_429(client, monkeypatch):
    import openai

    from app.ai.studio_image_prompt import StudioImagePromptAgent

    async def _rl(self, direction, context):
        req = httpx.Request("POST", "http://deepseek.local")
        resp = httpx.Response(429, request=req)
        raise openai.RateLimitError("rl", response=resp, body=None)

    monkeypatch.setattr(StudioImagePromptAgent, "enrich", _rl)
    monkeypatch.setattr("app.api.v1.studio.check_rate_limit", _no_rate_limit)
    monkeypatch.setattr(
        "app.ai.studio_copy.StudioCopyAgent.generate", _stub_copy_generate
    )
    project = _create_project(client)
    copy = _make_copy(client, project["id"])
    resp = client.post(
        f"/api/v1/studio/copies/{copy['id']}/image-prompt/enrich",
        json={"direction": "火锅沸腾"},
        headers=auth_headers(client),
    )
    assert resp.status_code == 429




# ============================================================
# 导出到视觉设计
# ============================================================


def _render_deck(client, project_id: str, copy_id: str) -> dict:
    resp = client.post(
        f"/api/v1/studio/projects/{project_id}/decks",
        json={
            "copy_id": copy_id,
            "template": "editorial",
            "theme": "ink-classic",
            "page_count": 4,
            "asset_ids": [],
        },
        headers=auth_headers(client),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_export_to_design(client, monkeypatch):
    monkeypatch.setattr(
        "app.ai.studio_copy.StudioCopyAgent.generate", _stub_copy_generate
    )
    monkeypatch.setattr(
        "app.ai.studio_paginate.StudioPaginateAgent.paginate", _stub_paginate
    )
    monkeypatch.setattr("app.api.v1.studio.render_pages", _stub_render_pages)
    monkeypatch.setattr("app.api.v1.studio.check_rate_limit", _no_rate_limit)

    shop_id = _create_shop(client)
    project = _create_project(client, shop_id=shop_id)
    copy = _make_copy(client, project["id"])
    deck = _render_deck(client, project["id"], copy["id"])
    headers = auth_headers(client)

    resp = client.post(
        f"/api/v1/studio/decks/{deck['deck_id']}/export-to-design",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(data["asset_ids"]) == 4

    # 设计模块可见导出的素材（source=studio）
    assets = client.get(
        f"/api/v1/design-projects/{data['design_project_id']}/assets",
        headers=headers,
    ).json()
    assert len(assets) == 4
    assert all(a["source"] == "studio" for a in assets)
    assert all(a["status"] == "active" for a in assets)


def test_export_unrendered_deck_400(client, monkeypatch):
    """已创建但渲染失败的卡组不可导出。"""
    monkeypatch.setattr(
        "app.ai.studio_copy.StudioCopyAgent.generate", _stub_copy_generate
    )
    monkeypatch.setattr(
        "app.ai.studio_paginate.StudioPaginateAgent.paginate", _stub_paginate
    )
    monkeypatch.setattr("app.api.v1.studio.check_rate_limit", _no_rate_limit)

    def _bad_render(htmls):
        raise RuntimeError("playwright 不可用")

    monkeypatch.setattr("app.api.v1.studio.render_pages", _bad_render)
    project = _create_project(client)
    copy = _make_copy(client, project["id"])
    resp = client.post(
        f"/api/v1/studio/projects/{project['id']}/decks",
        json={
            "copy_id": copy["id"],
            "template": "editorial",
            "theme": "ink-classic",
            "page_count": 4,
            "asset_ids": [],
        },
        headers=auth_headers(client),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "failed"

    exp = client.post(
        f"/api/v1/studio/decks/{resp.json()['deck_id']}/export-to-design",
        headers=auth_headers(client),
    )
    assert exp.status_code == 400


# ============================================================
# QA 单元测试（PIL 密度）
# ============================================================


def test_qa_density_pass_on_full_page():
    from app.services.studio_qa import analyze_density

    # 整页填充（非 paper 色）
    png = _make_png(color=(200, 90, 40))
    result = analyze_density(png, "#f3f0e8")
    assert result["pass"] is True
    assert result["coverage"] >= 95


def test_qa_density_fail_on_blank_page():
    from app.services.studio_qa import analyze_density

    # 与 paper 完全一致 → 无内容
    img = Image.new("RGB", (1080, 1440), (243, 240, 232))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    result = analyze_density(buf.getvalue(), "#f3f0e8")
    assert result["pass"] is False
    assert any("密度" in issue for issue in result["issues"])


def test_qa_report_overflow_and_bottom():
    from app.services.studio_qa import build_qa_report

    png = _make_png(color=(200, 90, 40))
    report = build_qa_report(
        png,
        {"overflow": 60, "bottom_gap": 250},
        "#f3f0e8",
    )
    assert report["pass"] is False
    assert report["checks"]["overflow"]["pass"] is False
    assert report["checks"]["bottom_blank"]["pass"] is False


# ============================================================
# 真实渲染（Playwright + Chromium，可用时运行）
# ============================================================


def test_render_real_page_and_qa():
    try:
        from app.services.studio_qa import build_qa_report
        from app.services.studio_render import build_page_html, render_pages
        from app.services.studio_themes import theme_paper
    except Exception:
        pytest.skip("playwright 未安装")

    img = Image.new("RGB", (400, 500), (210, 110, 50))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    data_url = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

    html = build_page_html(
        template="editorial",
        theme="ink-classic",
        title="周末必去！人均80的市井火锅",
        bullets=["每天现炒底料", "0 预制料包", "麻辣鲜香", "双人套餐 168", "招牌毛肚必点"],
        image_url=data_url,
        shop_name="蜀香里火锅",
        category="市井火锅",
        topic="藏在小巷里的市井烟火气",
        page_num=1,
        page_total=4,
        is_cover=True,
    )
    try:
        results = render_pages([html])
    except Exception as exc:
        pytest.skip(f"chromium 不可用: {exc}")
    assert len(results) == 1
    png = results[0]["png"]
    assert Image.open(io.BytesIO(png)).size == (1080, 1440)
    qa = build_qa_report(png, results[0]["metrics"], theme_paper("editorial", "ink-classic"))
    assert qa["pass"] is True






