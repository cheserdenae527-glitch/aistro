"""直播工坊 L1 后端测试。

运行方式：
    cd D:\two\backend
    pytest tests/test_live.py -v

需要 Postgres + Redis 运行中（docker compose up -d）。
AI Agent 与频控全部 monkeypatch，不调用真实 LLM / Redis。
"""
from __future__ import annotations


import pytest

from app.ai.live_compliance import LiveCompliance
from app.ai.live_danmaku_agent import LiveDanmakuAgentError
from app.ai.live_script_agent import LiveScriptAgent, LiveScriptAgentError


# ============================================================
# Helpers
# ============================================================


def auth_headers(client, email="admin@test.com", password="admin123") -> dict:
    resp = client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    if resp.status_code != 200:
        client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": password, "name": "Test User"},
        )
        resp = client.post(
            "/api/v1/auth/login", json={"email": email, "password": password}
        )
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def other_headers(client, email="other@test.com") -> dict:
    return auth_headers(client, email=email)


def current_user_id(client) -> str:
    resp = client.get("/api/v1/auth/me", headers=auth_headers(client))
    return resp.json()["id"]


def _create_shop(client) -> str:
    headers = auth_headers(client)
    m_resp = client.post(
        "/api/v1/merchants", json={"name": "测试商家"}, headers=headers
    )
    mid = m_resp.json()["id"]
    s_resp = client.post(
        f"/api/v1/merchants/{mid}/shops",
        json={"name": "测试门店", "category": "火锅"},
        headers=headers,
    )
    return s_resp.json()["id"]


def _create_project(client, shop_id=None, platform="douyin", title="火锅直播间") -> dict:
    headers = auth_headers(client)
    shop_id = shop_id or _create_shop(client)
    resp = client.post(
        "/api/v1/live-projects",
        json={"shop_id": shop_id, "title": title, "platform": platform},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _create_avatar(client, name="店长小雅", persona=None, status="ready", **overrides) -> dict:
    headers = auth_headers(client)
    data = {"name": name, "avatar_type": "image", "persona": persona, "status": status}
    data.update(overrides)
    resp = client.post("/api/v1/live-avatars", json=data, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


_PERSONA = {
    "identity": "店长小雅",
    "tone": "亲切热情，懂美食",
    "boundaries": "不承诺疗效，不讨论政治宗教",
    "forbidden_topics": ["政治", "宗教"],
}


def _make_segments(duration_sec: int = 1800) -> list[dict]:
    segs = [
        {"type": "opening", "title": "开场留人", "text": "欢迎来到直播间，今天福利超多", "duration_sec": 60, "cue": "微笑挥手"},
        {"type": "product", "title": "招牌毛肚", "text": "先讲招牌毛肚，每天现切现卖", "duration_sec": 900, "cue": "展示菜品"},
        {"type": "promo", "title": "优惠逼单", "text": "今天双人餐只要 88 元，限量 50 份", "duration_sec": 90, "cue": "指向优惠链接"},
        {"type": "interaction", "title": "互动点菜", "text": "大家想吃什么在评论区告诉我", "duration_sec": 300, "cue": "看屏幕"},
        {"type": "qa", "title": "答疑", "text": "辣度可选微辣中辣特辣，分量够三个人吃", "duration_sec": 300, "cue": "比划手势"},
        {"type": "closing", "title": "收尾", "text": "记得下单核销，下周三同一时间再见", "duration_sec": 60, "cue": "挥手告别"},
    ]
    total = sum(s["duration_sec"] for s in segs)
    if total != duration_sec:
        diff = duration_sec - total
        for s in segs:
            if s["type"] == "product":
                s["duration_sec"] += diff
                break
    return segs


async def _stub_generate(
    self, *, shop_name, category, platform, goal, promo_items, persona, tone, duration_min
):
    target = (duration_min or 30) * 60
    return {
        "title": "夏日招牌直播脚本",
        "tone": tone or "烟火气",
        "content": _make_segments(target),
        "total_duration_sec": target,
        "compliance_risks": [],
    }


async def _stub_danmaku(self, *, platform, persona, script):
    return {
        "persona": persona
        or {
            "name": "店长小雅",
            "personality": "亲切热情，懂美食",
            "style": "烟火气，口语化",
            "knowledge_scope": "本店菜品、优惠、营业信息",
            "forbidden_topics": ["政治", "宗教"],
        },
        "reply_rules": [
            {"trigger": "优惠", "reply": "今日套餐 9.9 元起，点小黄车就能下单", "mode": "manual"},
            {"trigger": "辣度", "reply": "可以选微辣中辣特辣", "mode": "manual"},
        ],
        "sensitive_words": ["加微信", "赌博"],
        "escalate_topics": ["投诉", "食品安全"],
    }


async def _stub_review(self, *, metrics, script_summary):
    return "复盘报告：峰值在线 100 人，互动率良好；建议下一场增加优惠逼单频次并提前预告。"


async def _peek_ok(*args, **kwargs):
    return True


async def _peek_limited(*args, **kwargs):
    return False


async def _set_noop(*args, **kwargs):
    return None


def _make_set_recorder():
    calls = []

    async def recorder(*args, **kwargs):
        calls.append(args)

    return recorder, calls


def _patch_agents(
    monkeypatch,
    script_stub=None,
    danmaku_stub=None,
    review_stub=None,
    peek=None,
    set_=None,
):
    monkeypatch.setattr(
        "app.ai.live_script_agent.LiveScriptAgent.generate",
        script_stub or _stub_generate,
    )
    monkeypatch.setattr(
        "app.ai.live_danmaku_agent.LiveDanmakuAgent.generate",
        danmaku_stub or _stub_danmaku,
    )
    monkeypatch.setattr(
        "app.ai.live_review_agent.LiveReviewAgent.review",
        review_stub or _stub_review,
    )
    monkeypatch.setattr("app.api.v1.live.peek_rate_limit", peek or _peek_ok)
    monkeypatch.setattr("app.api.v1.live.set_rate_limit", set_ or _set_noop)


def _generate(client, project_id, avatar_id=None, **body) -> dict:
    headers = auth_headers(client)
    payload = {"tone": "烟火气", "duration_min": 30}
    if avatar_id is not None:
        payload["avatar_id"] = avatar_id
    payload.update(body)
    resp = client.post(
        f"/api/v1/live-projects/{project_id}/scripts/generate",
        json=payload,
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _confirm(client, project_id, sid) -> dict:
    resp = client.post(
        f"/api/v1/live-projects/{project_id}/scripts/{sid}/confirm",
        headers=auth_headers(client),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _create_session(client, project_id, script_id=None, avatar_id=None, **overrides) -> dict:
    headers = auth_headers(client)
    data = {"scheduled_at": "2026-08-10T20:00:00+08:00"}
    if script_id is not None:
        data["script_id"] = script_id
    if avatar_id is not None:
        data["avatar_id"] = avatar_id
    data.update(overrides)
    resp = client.post(
        f"/api/v1/live-projects/{project_id}/sessions",
        json=data,
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _patch_session(client, project_id, sid, payload) -> dict:
    resp = client.patch(
        f"/api/v1/live-projects/{project_id}/sessions/{sid}",
        json=payload,
        headers=auth_headers(client),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


# ============================================================
# Agent / Compliance 单元测试
# ============================================================


def test_script_agent_clean_script_ok():
    agent = LiveScriptAgent()
    data = {
        "title": "测试脚本",
        "tone": "烟火气",
        "content": _make_segments(1800),
        "compliance_risks": [],
    }
    cleaned = agent._clean_script(data, duration_min=30)
    assert cleaned["total_duration_sec"] == 1800
    assert {s["type"] for s in cleaned["content"]} == {
        "opening", "product", "promo", "interaction", "qa", "closing",
    }


def test_script_agent_duration_deviation_rejected():
    agent = LiveScriptAgent()
    data = {
        "title": "测试脚本",
        "tone": "烟火气",
        "content": _make_segments(2000),  # 30min -> 1800s，偏差 >10%
        "compliance_risks": [],
    }
    with pytest.raises(LiveScriptAgentError, match="偏差超过 10%"):
        agent._clean_script(data, duration_min=30)


def test_script_agent_missing_type_rejected():
    agent = LiveScriptAgent()
    content = [s for s in _make_segments(1800) if s["type"] != "closing"]
    with pytest.raises(LiveScriptAgentError, match="缺少分段类型"):
        agent._clean_script({"title": "t", "content": content}, duration_min=None)


def test_script_agent_sensitive_rejected():
    agent = LiveScriptAgent()
    content = _make_segments(1800)
    content[0]["text"] = "欢迎来赌博直播间"
    with pytest.raises(LiveScriptAgentError, match="敏感词"):
        agent._clean_script({"title": "t", "content": content}, duration_min=None)


def test_compliance_rule_engine():
    ok = LiveCompliance.check(
        ai_label_text="本直播间由 AI 数字人出镜",
        persona_snapshot=_PERSONA,
        content=_make_segments(1800),
    )
    assert ok["pass"] is True

    bad_ai = LiveCompliance.check(
        ai_label_text="", persona_snapshot=_PERSONA, content=_make_segments(1800)
    )
    assert bad_ai["pass"] is False
    assert any(i["key"] == "ai_label" and not i["ok"] for i in bad_ai["items"])

    bad_persona = LiveCompliance.check(
        ai_label_text="x",
        persona_snapshot={**_PERSONA, "tone": "全网第一好吃"},
        content=_make_segments(1800),
    )
    assert bad_persona["pass"] is False
    assert any(i["key"] == "persona" and not i["ok"] for i in bad_persona["items"])

    red_line_content = _make_segments(1800)
    red_line_content[0]["text"] = "24小时无人直播，全天自动卖货"
    bad_red = LiveCompliance.check(
        ai_label_text="x", persona_snapshot=_PERSONA, content=red_line_content
    )
    assert bad_red["pass"] is False
    assert any(i["key"] == "sensitive" and not i["ok"] for i in bad_red["items"])

    off = _make_segments(1800)
    off[1]["text"] = "加微信转账更划算"
    bad_off = LiveCompliance.check(
        ai_label_text="x", persona_snapshot=_PERSONA, content=off
    )
    assert bad_off["pass"] is False
    assert any(i["key"] == "off_platform" and not i["ok"] for i in bad_off["items"])

    no_persona = LiveCompliance.check(
        ai_label_text="x", persona_snapshot=None, content=_make_segments(1800)
    )
    assert no_persona["pass"] is True
    assert any(i["key"] == "persona" and i["ok"] for i in no_persona["items"])


# ============================================================
# 项目 CRUD / 鉴权
# ============================================================


def test_live_project_crud_and_engine_config_masked(client, monkeypatch):
    _patch_agents(monkeypatch)
    headers = auth_headers(client)
    shop_id = _create_shop(client)
    resp = client.post(
        "/api/v1/live-projects",
        json={
            "shop_id": shop_id,
            "title": "火锅直播间",
            "platform": "douyin",
            "goal": "提升核销",
            "promo_items": [{"name": "双人餐", "price": 88, "original_price": 128}],
            "engine_config": {"base_url": "http://localhost:12345", "api_key": "sk-secret", "enabled": True},
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    pid = resp.json()["id"]
    # engine_config 脱敏：api_key 不原样回传
    cfg = resp.json()["engine_config"]
    assert "api_key" not in cfg
    assert cfg["api_key_configured"] is True
    assert cfg["base_url"] == "http://localhost:12345"

    list_resp = client.get(f"/api/v1/live-projects?shop_id={shop_id}", headers=headers)
    assert list_resp.status_code == 200
    assert list_resp.json()["total"] >= 1

    patch_resp = client.patch(
        f"/api/v1/live-projects/{pid}", json={"title": "火锅直播间V2"}, headers=headers
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["title"] == "火锅直播间V2"

    assert client.delete(f"/api/v1/live-projects/{pid}", headers=headers).status_code == 200
    assert client.get(f"/api/v1/live-projects/{pid}", headers=headers).status_code == 404


def test_live_requires_auth(client):
    assert client.get("/api/v1/live-projects").status_code == 401


def test_live_project_cross_user_404(client):
    project = _create_project(client)
    other = other_headers(client)
    assert client.get(
        f"/api/v1/live-projects/{project['id']}", headers=other
    ).status_code == 404
    assert client.patch(
        f"/api/v1/live-projects/{project['id']}", json={"title": "x"}, headers=other
    ).status_code == 404
    assert client.delete(
        f"/api/v1/live-projects/{project['id']}", headers=other
    ).status_code == 404


def test_live_project_sensitive_title_422(client):
    headers = auth_headers(client)
    shop_id = _create_shop(client)
    resp = client.post(
        "/api/v1/live-projects",
        json={"shop_id": shop_id, "title": "赌博引流直播间"},
        headers=headers,
    )
    assert resp.status_code == 422


# ============================================================
# 数字人形象（org 鉴权）
# ============================================================


def test_avatar_crud_org_scope(client, monkeypatch):
    _patch_agents(monkeypatch)
    headers = auth_headers(client)
    avatar = _create_avatar(client, persona=_PERSONA)
    other = other_headers(client)

    # 同 org 可读写
    assert client.get(
        f"/api/v1/live-avatars/{avatar['id']}", headers=headers
    ).status_code == 200
    patch = client.patch(
        f"/api/v1/live-avatars/{avatar['id']}",
        json={"name": "店长小雅V2"},
        headers=headers,
    )
    assert patch.status_code == 200
    assert patch.json()["name"] == "店长小雅V2"

    # 跨 org 一律 404
    assert client.get(
        f"/api/v1/live-avatars/{avatar['id']}", headers=other
    ).status_code == 404
    assert client.patch(
        f"/api/v1/live-avatars/{avatar['id']}", json={"name": "x"}, headers=other
    ).status_code == 404
    assert client.delete(
        f"/api/v1/live-avatars/{avatar['id']}", headers=other
    ).status_code == 404

    # 跨 org 列表不可见
    assert client.get("/api/v1/live-avatars", headers=other).json()["total"] == 0


def test_avatar_cross_org_binding_404(client, monkeypatch):
    _patch_agents(monkeypatch)
    avatar_a = _create_avatar(client, persona=_PERSONA)
    other = other_headers(client)
    other_shop = None
    # other 用户建自己的店 + 项目
    other_shop = _create_shop_for_headers(client, other)
    other_project = client.post(
        "/api/v1/live-projects",
        json={"shop_id": other_shop, "title": "别人的直播间", "platform": "douyin"},
        headers=other,
    ).json()

    # scripts/generate 传跨 org avatar → 404
    resp = client.post(
        f"/api/v1/live-projects/{other_project['id']}/scripts/generate",
        json={"avatar_id": avatar_a["id"]},
        headers=other,
    )
    assert resp.status_code == 404

    # sessions 创建传跨 org avatar → 404
    resp = client.post(
        f"/api/v1/live-projects/{other_project['id']}/sessions",
        json={"scheduled_at": "2026-08-10T20:00:00+08:00", "avatar_id": avatar_a["id"]},
        headers=other,
    )
    assert resp.status_code == 404

    # sessions PATCH 传跨 org avatar → 404
    session = client.post(
        f"/api/v1/live-projects/{other_project['id']}/sessions",
        json={"scheduled_at": "2026-08-10T20:00:00+08:00"},
        headers=other,
    ).json()
    resp = client.patch(
        f"/api/v1/live-projects/{other_project['id']}/sessions/{session['id']}",
        json={"avatar_id": avatar_a["id"]},
        headers=other,
    )
    assert resp.status_code == 404


def _create_shop_for_headers(client, headers) -> str:
    m_resp = client.post("/api/v1/merchants", json={"name": "测试商家2"}, headers=headers)
    mid = m_resp.json()["id"]
    s_resp = client.post(
        f"/api/v1/merchants/{mid}/shops",
        json={"name": "测试门店2", "category": "烧烤"},
        headers=headers,
    )
    return s_resp.json()["id"]


def test_avatar_delete_referenced_409(client, monkeypatch):
    _patch_agents(monkeypatch)
    headers = auth_headers(client)

    avatar_s = _create_avatar(client, name="脚本引用形象", persona=_PERSONA)
    project = _create_project(client)
    script = _generate(client, project["id"], avatar_id=avatar_s["id"])
    assert client.delete(
        f"/api/v1/live-avatars/{avatar_s['id']}", headers=headers
    ).status_code == 409

    avatar_ss = _create_avatar(client, name="场次引用形象", persona=_PERSONA)
    session = _create_session(client, project["id"], avatar_id=avatar_ss["id"])
    assert client.delete(
        f"/api/v1/live-avatars/{avatar_ss['id']}", headers=headers
    ).status_code == 409

    # 解除引用后可删
    assert client.delete(
        f"/api/v1/live-projects/{project['id']}/scripts/{script['id']}",
        headers=headers,
    ).status_code == 200
    assert client.delete(
        f"/api/v1/live-projects/{project['id']}/sessions/{session['id']}",
        headers=headers,
    ).status_code == 200
    assert client.delete(
        f"/api/v1/live-avatars/{avatar_s['id']}", headers=headers
    ).status_code == 200
    assert client.delete(
        f"/api/v1/live-avatars/{avatar_ss['id']}", headers=headers
    ).status_code == 200


# ============================================================
# 脚本生成 / 批次 / 合规 / 导出
# ============================================================


def test_script_generate_success_6_types(client, monkeypatch):
    _patch_agents(monkeypatch)
    project = _create_project(client)
    avatar = _create_avatar(client, persona=_PERSONA)
    script = _generate(client, project["id"], avatar_id=avatar["id"])

    assert script["generation_batch"] == 1
    assert script["status"] == "draft"
    assert script["total_duration_sec"] == 1800
    assert script["avatar_id"] == avatar["id"]
    assert script["persona_snapshot"]["identity"] == "店长小雅"
    types = {s["type"] for s in script["content"]}
    assert types == {"opening", "product", "promo", "interaction", "qa", "closing"}


def test_script_generate_requires_avatar_if_none_generated(client, monkeypatch):
    _patch_agents(monkeypatch)
    project = _create_project(client)
    resp = client.post(
        f"/api/v1/live-projects/{project['id']}/scripts/generate",
        json={"duration_min": 30},
        headers=auth_headers(client),
    )
    assert resp.status_code == 400
    assert "avatar_id" in resp.json()["detail"]


def test_script_generate_disabled_default_avatar_400(client, monkeypatch):
    _patch_agents(monkeypatch)
    project = _create_project(client)
    avatar = _create_avatar(client, persona=_PERSONA, status="ready")
    _generate(client, project["id"], avatar_id=avatar["id"])
    # 停用默认形象后，不显式传 avatar_id → 400
    client.patch(
        f"/api/v1/live-avatars/{avatar['id']}",
        json={"status": "disabled"},
        headers=auth_headers(client),
    )
    resp = client.post(
        f"/api/v1/live-projects/{project['id']}/scripts/generate",
        json={"duration_min": 30},
        headers=auth_headers(client),
    )
    assert resp.status_code == 400
    assert "停用" in resp.json()["detail"]


def test_script_generate_sensitive_422_no_rate_count(client, monkeypatch):
    async def bad_generate(self, **kwargs):
        raise LiveScriptAgentError("生成内容包含敏感词")

    recorder, calls = _make_set_recorder()
    _patch_agents(monkeypatch, script_stub=bad_generate, set_=recorder)
    project = _create_project(client)
    avatar = _create_avatar(client, persona=_PERSONA)
    resp = client.post(
        f"/api/v1/live-projects/{project['id']}/scripts/generate",
        json={"avatar_id": avatar["id"], "duration_min": 30},
        headers=auth_headers(client),
    )
    assert resp.status_code == 422
    assert calls == []  # 成功才计入频控


def test_script_generate_format_error_502_no_rate_count(client, monkeypatch):
    async def bad_generate(self, **kwargs):
        raise LiveScriptAgentError("LLM 返回无法解析的 JSON")

    recorder, calls = _make_set_recorder()
    _patch_agents(monkeypatch, script_stub=bad_generate, set_=recorder)
    project = _create_project(client)
    avatar = _create_avatar(client, persona=_PERSONA)
    resp = client.post(
        f"/api/v1/live-projects/{project['id']}/scripts/generate",
        json={"avatar_id": avatar["id"], "duration_min": 30},
        headers=auth_headers(client),
    )
    assert resp.status_code == 502
    assert calls == []


def test_script_generate_rate_limited_429(client, monkeypatch):
    _patch_agents(monkeypatch, peek=_peek_limited)
    project = _create_project(client)
    avatar = _create_avatar(client, persona=_PERSONA)
    resp = client.post(
        f"/api/v1/live-projects/{project['id']}/scripts/generate",
        json={"avatar_id": avatar["id"], "duration_min": 30},
        headers=auth_headers(client),
    )
    assert resp.status_code == 429


def test_persona_snapshot_isolated_from_avatar_edits(client, monkeypatch):
    _patch_agents(monkeypatch)
    project = _create_project(client)
    avatar = _create_avatar(client, persona=_PERSONA)
    script = _generate(client, project["id"], avatar_id=avatar["id"])
    assert script["persona_snapshot"]["identity"] == "店长小雅"

    # 生成后修改形象 persona，不应回溯影响脚本
    client.patch(
        f"/api/v1/live-avatars/{avatar['id']}",
        json={"persona": {**_PERSONA, "identity": "改后的店长"}},
        headers=auth_headers(client),
    )
    confirmed = _confirm(client, project["id"], script["id"])
    assert confirmed["status"] == "confirmed"
    # confirm 用的仍是快照
    export = client.post(
        f"/api/v1/live-projects/{project['id']}/scripts/{script['id']}/export",
        headers=auth_headers(client),
    ).json()
    assert export["persona_json"]["identity"] == "店长小雅"


def test_compliance_skips_persona_without_snapshot(client, monkeypatch):
    _patch_agents(monkeypatch)
    project = _create_project(client)
    avatar = _create_avatar(client, persona=None, status="ready")
    script = _generate(client, project["id"], avatar_id=avatar["id"])
    assert script["persona_snapshot"] is None

    resp = client.post(
        f"/api/v1/live-projects/{project['id']}/compliance/check",
        json={},
        headers=auth_headers(client),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["pass"] is True
    persona_item = next(i for i in body["items"] if i["key"] == "persona")
    assert persona_item["ok"] is True
    assert "跳过" in persona_item["detail"]

    confirmed = _confirm(client, project["id"], script["id"])
    assert confirmed["status"] == "confirmed"
    export = client.post(
        f"/api/v1/live-projects/{project['id']}/scripts/{script['id']}/export",
        headers=auth_headers(client),
    ).json()
    assert any(i["key"] == "persona_placeholder" for i in export["compliance"]["items"])
    assert export["persona_json"]["name"] == "门店主播"


def test_regenerate_archives_old_batches(client, monkeypatch):
    _patch_agents(monkeypatch)
    project = _create_project(client)
    avatar = _create_avatar(client, persona=_PERSONA)
    s1 = _generate(client, project["id"], avatar_id=avatar["id"])
    # 编辑 + 定稿旧批次
    client.put(
        f"/api/v1/live-projects/{project['id']}/scripts/{s1['id']}",
        json={"title": "改过的标题"},
        headers=auth_headers(client),
    )
    _confirm(client, project["id"], s1["id"])

    s2 = _generate(client, project["id"], avatar_id=avatar["id"])
    assert s2["generation_batch"] == 2
    assert s2["is_archived"] is False

    list_all = client.get(
        f"/api/v1/live-projects/{project['id']}/scripts?include_archived=true",
        headers=auth_headers(client),
    ).json()
    by_id = {s["id"]: s for s in list_all}
    assert by_id[s1["id"]]["is_archived"] is True
    assert by_id[s1["id"]]["status"] == "confirmed"
    assert by_id[s2["id"]]["is_archived"] is False

    # 默认不包含归档
    list_active = client.get(
        f"/api/v1/live-projects/{project['id']}/scripts",
        headers=auth_headers(client),
    ).json()
    assert len(list_active) == 1
    assert list_active[0]["id"] == s2["id"]


def test_confirm_compliance_fail_422(client, monkeypatch):
    _patch_agents(monkeypatch)
    project = _create_project(client)
    avatar = _create_avatar(client, persona={**_PERSONA, "tone": "全网第一好吃"})
    script = _generate(client, project["id"], avatar_id=avatar["id"])
    resp = client.post(
        f"/api/v1/live-projects/{project['id']}/scripts/{script['id']}/confirm",
        headers=auth_headers(client),
    )
    assert resp.status_code == 422
    body = resp.json()["detail"]
    assert body["message"] == "合规自检未通过"
    assert any(i["key"] == "persona" and not i["ok"] for i in body["items"])


def test_confirm_ai_label_missing_422(client, monkeypatch):
    _patch_agents(monkeypatch)
    project = _create_project(client)
    avatar = _create_avatar(client, persona=_PERSONA)
    script = _generate(client, project["id"], avatar_id=avatar["id"])
    # 清空 AI 标识文案
    client.patch(
        f"/api/v1/live-projects/{project['id']}",
        json={"ai_label_text": ""},
        headers=auth_headers(client),
    )
    resp = client.post(
        f"/api/v1/live-projects/{project['id']}/scripts/{script['id']}/confirm",
        headers=auth_headers(client),
    )
    assert resp.status_code == 422
    assert any(
        i["key"] == "ai_label" and not i["ok"]
        for i in resp.json()["detail"]["items"]
    )


def test_confirm_idempotent_and_confirmed_locked(client, monkeypatch):
    _patch_agents(monkeypatch)
    project = _create_project(client)
    avatar = _create_avatar(client, persona=_PERSONA)
    script = _generate(client, project["id"], avatar_id=avatar["id"])
    headers = auth_headers(client)

    assert _confirm(client, project["id"], script["id"])["status"] == "confirmed"
    # 幂等
    resp = client.post(
        f"/api/v1/live-projects/{project['id']}/scripts/{script['id']}/confirm",
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "confirmed"

    # confirmed 禁止 PUT / DELETE
    assert client.put(
        f"/api/v1/live-projects/{project['id']}/scripts/{script['id']}",
        json={"title": "x"},
        headers=headers,
    ).status_code == 400
    assert client.delete(
        f"/api/v1/live-projects/{project['id']}/scripts/{script['id']}",
        headers=headers,
    ).status_code == 400


def test_export_requires_confirmed_and_active(client, monkeypatch):
    _patch_agents(monkeypatch)
    headers = auth_headers(client)
    project = _create_project(client)
    avatar = _create_avatar(client, persona=_PERSONA)

    s1 = _generate(client, project["id"], avatar_id=avatar["id"])
    # 未定稿 → 400
    assert client.post(
        f"/api/v1/live-projects/{project['id']}/scripts/{s1['id']}/export",
        headers=headers,
    ).status_code == 400

    _confirm(client, project["id"], s1["id"])
    export = client.post(
        f"/api/v1/live-projects/{project['id']}/scripts/{s1['id']}/export",
        headers=headers,
    )
    assert export.status_code == 200
    bundle = export.json()
    assert "## 开场留人（60s）" in bundle["script_markdown"]
    assert bundle["persona_json"]["identity"] == "店长小雅"
    assert bundle["wordlist"]
    assert bundle["reply_rules"] == []
    assert any(i["key"] == "danmaku_missing" for i in bundle["compliance"]["items"])
    assert "LiveTalking" in bundle["engine_guide"]

    # regenerate 归档后（即使 confirmed）不可导出
    s2 = _generate(client, project["id"], avatar_id=avatar["id"])
    resp = client.post(
        f"/api/v1/live-projects/{project['id']}/scripts/{s1['id']}/export",
        headers=headers,
    )
    assert resp.status_code == 400
    assert "已归档" in resp.json()["detail"]
    assert s2["generation_batch"] == 2


# ============================================================
# 弹幕互动配置
# ============================================================


def test_danmaku_generate_precondition_and_write(client, monkeypatch):
    _patch_agents(monkeypatch)
    headers = auth_headers(client)
    project = _create_project(client)
    avatar = _create_avatar(client, persona=_PERSONA)

    # 无 confirmed 脚本 → 400
    resp = client.post(
        f"/api/v1/live-projects/{project['id']}/danmaku-config/generate",
        headers=headers,
    )
    assert resp.status_code == 400

    s1 = _generate(client, project["id"], avatar_id=avatar["id"])
    resp = client.post(
        f"/api/v1/live-projects/{project['id']}/danmaku-config/generate",
        headers=headers,
    )
    assert resp.status_code == 400  # draft 不算

    _confirm(client, project["id"], s1["id"])
    resp = client.post(
        f"/api/v1/live-projects/{project['id']}/danmaku-config/generate",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    cfg = resp.json()
    assert cfg["source_script_id"] == s1["id"]
    assert len(cfg["reply_rules"]) == 2
    assert cfg["sensitive_words"] == ["加微信", "赌博"]

    # GET / PUT
    assert client.get(
        f"/api/v1/live-projects/{project['id']}/danmaku-config", headers=headers
    ).json()["id"] == cfg["id"]
    put = client.put(
        f"/api/v1/live-projects/{project['id']}/danmaku-config",
        json={"escalate_topics": ["价格争议"]},
        headers=headers,
    )
    assert put.status_code == 200
    assert put.json()["escalate_topics"] == ["价格争议"]
    assert put.json()["source_script_id"] == s1["id"]  # 人工编辑保留来源


def test_danmaku_generate_archived_confirmed_not_precondition(client, monkeypatch):
    _patch_agents(monkeypatch)
    headers = auth_headers(client)
    project = _create_project(client)
    avatar = _create_avatar(client, persona=_PERSONA)
    s1 = _generate(client, project["id"], avatar_id=avatar["id"])
    _confirm(client, project["id"], s1["id"])
    # regenerate 归档旧 confirmed
    s2 = _generate(client, project["id"], avatar_id=avatar["id"])
    assert s2["generation_batch"] == 2
    # 新批次 draft，旧批次 confirmed 但已归档 → 400
    resp = client.post(
        f"/api/v1/live-projects/{project['id']}/danmaku-config/generate",
        headers=headers,
    )
    assert resp.status_code == 400


def test_danmaku_generate_cover_write_and_failure_keeps_old(client, monkeypatch):
    _patch_agents(monkeypatch)
    headers = auth_headers(client)
    project = _create_project(client)
    avatar = _create_avatar(client, persona=_PERSONA)
    s1 = _generate(client, project["id"], avatar_id=avatar["id"])
    _confirm(client, project["id"], s1["id"])

    # 第一次生成
    client.post(
        f"/api/v1/live-projects/{project['id']}/danmaku-config/generate",
        headers=headers,
    )

    # 覆盖式生成：第二次以新脚本为源
    s2 = _generate(client, project["id"], avatar_id=avatar["id"])
    _confirm(client, project["id"], s2["id"])
    resp = client.post(
        f"/api/v1/live-projects/{project['id']}/danmaku-config/generate",
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["source_script_id"] == s2["id"]

    # 生成失败 → 保留旧配置
    async def bad_danmaku(self, **kwargs):
        raise LiveDanmakuAgentError("LLM 返回无法解析的 JSON")

    monkeypatch.setattr(
        "app.ai.live_danmaku_agent.LiveDanmakuAgent.generate", bad_danmaku
    )
    fail = client.post(
        f"/api/v1/live-projects/{project['id']}/danmaku-config/generate",
        headers=headers,
    )
    assert fail.status_code == 502
    cfg = client.get(
        f"/api/v1/live-projects/{project['id']}/danmaku-config", headers=headers
    ).json()
    assert cfg["source_script_id"] == s2["id"]
    assert len(cfg["reply_rules"]) == 2


def test_danmaku_generate_sensitive_422_no_rate_count(client, monkeypatch):

    async def bad_danmaku(self, **kwargs):
        raise LiveDanmakuAgentError("生成内容包含敏感词")

    recorder, calls = _make_set_recorder()
    _patch_agents(monkeypatch, danmaku_stub=bad_danmaku, set_=recorder)
    headers = auth_headers(client)
    project = _create_project(client)
    avatar = _create_avatar(client, persona=_PERSONA)
    s1 = _generate(client, project["id"], avatar_id=avatar["id"])
    _confirm(client, project["id"], s1["id"])
    calls.clear()  # 之前成功的 scripts/generate 已计入频控，与本用例无关
    resp = client.post(
        f"/api/v1/live-projects/{project['id']}/danmaku-config/generate",
        headers=headers,
    )
    assert resp.status_code == 422
    assert calls == []  # danmaku 失败不新增频控


def test_export_danmaku_stale_hint(client, monkeypatch):
    _patch_agents(monkeypatch)
    headers = auth_headers(client)
    project = _create_project(client)
    avatar = _create_avatar(client, persona=_PERSONA)
    s1 = _generate(client, project["id"], avatar_id=avatar["id"])
    _confirm(client, project["id"], s1["id"])
    client.post(
        f"/api/v1/live-projects/{project['id']}/danmaku-config/generate",
        headers=headers,
    )
    # 脚本 regenerate 出新的活跃批次后，弹幕配置仍指向旧脚本
    s2 = _generate(client, project["id"], avatar_id=avatar["id"])
    _confirm(client, project["id"], s2["id"])
    export = client.post(
        f"/api/v1/live-projects/{project['id']}/scripts/{s2['id']}/export",
        headers=headers,
    ).json()
    assert any(i["key"] == "danmaku_stale" for i in export["compliance"]["items"])
    assert export["reply_rules"]  # 已有弹幕配置 → 带出回复规则


def test_export_persona_priority_danmaku_over_snapshot(client, monkeypatch):
    _patch_agents(monkeypatch)
    headers = auth_headers(client)
    project = _create_project(client)
    avatar = _create_avatar(client, persona=_PERSONA)
    s1 = _generate(client, project["id"], avatar_id=avatar["id"])
    _confirm(client, project["id"], s1["id"])
    client.post(
        f"/api/v1/live-projects/{project['id']}/danmaku-config/generate",
        headers=headers,
    )
    # 人工精调弹幕 persona
    client.put(
        f"/api/v1/live-projects/{project['id']}/danmaku-config",
        json={"persona": {**_PERSONA, "identity": "精调后的店长"}},
        headers=headers,
    )
    export = client.post(
        f"/api/v1/live-projects/{project['id']}/scripts/{s1['id']}/export",
        headers=headers,
    ).json()
    assert export["persona_json"]["identity"] == "精调后的店长"


# ============================================================
# 场次状态机
# ============================================================


def test_session_create_and_list(client, monkeypatch):
    _patch_agents(monkeypatch)
    project = _create_project(client)
    session = _create_session(client, project["id"])
    assert session["status"] == "planned"
    assert session["is_backfilled"] is False
    assert session["duty_confirmed"] is False

    list_resp = client.get(
        f"/api/v1/live-projects/{project['id']}/sessions",
        headers=auth_headers(client),
    )
    assert list_resp.status_code == 200
    assert list_resp.json()["total"] == 1


def test_session_planned_to_live_validations(client, monkeypatch):
    _patch_agents(monkeypatch)
    headers = auth_headers(client)
    project = _create_project(client)
    session = _create_session(client, project["id"])
    sid = session["id"]

    # 直接开播 → 422（值守 + AI 标识均未满足）
    resp = client.patch(
        f"/api/v1/live-projects/{project['id']}/sessions/{sid}",
        json={"status": "live"},
        headers=headers,
    )
    assert resp.status_code == 422
    assert len(resp.json()["detail"]["items"]) >= 2

    # duty_confirmed=true 但没值守人 → 422
    resp = client.patch(
        f"/api/v1/live-projects/{project['id']}/sessions/{sid}",
        json={"duty_confirmed": True},
        headers=headers,
    )
    assert resp.status_code == 422

    # 无脚本场次：满足值守 + AI 标识即可开播（MVP 弹性）
    operator = current_user_id(client)
    resp = client.patch(
        f"/api/v1/live-projects/{project['id']}/sessions/{sid}",
        json={
            "operator_id": operator,
            "duty_confirmed": True,
            "ai_label_confirmed": True,
            "status": "live",
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "live"

    # live → ended
    resp = client.patch(
        f"/api/v1/live-projects/{project['id']}/sessions/{sid}",
        json={"status": "ended"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ended"

    # 终态：仅 notes 可改
    assert client.patch(
        f"/api/v1/live-projects/{project['id']}/sessions/{sid}",
        json={"scheduled_at": "2026-08-11T20:00:00+08:00"},
        headers=headers,
    ).status_code == 400
    notes = client.patch(
        f"/api/v1/live-projects/{project['id']}/sessions/{sid}",
        json={"notes": "本场顺利"},
        headers=headers,
    )
    assert notes.status_code == 200
    assert notes.json()["notes"] == "本场顺利"


def test_session_with_script_requires_active_confirmed(client, monkeypatch):
    _patch_agents(monkeypatch)
    headers = auth_headers(client)
    project = _create_project(client)
    avatar = _create_avatar(client, persona=_PERSONA)
    s1 = _generate(client, project["id"], avatar_id=avatar["id"])
    session = _create_session(client, project["id"], script_id=s1["id"])
    operator = current_user_id(client)

    # 脚本 draft → 422
    resp = client.patch(
        f"/api/v1/live-projects/{project['id']}/sessions/{session['id']}",
        json={
            "operator_id": operator,
            "duty_confirmed": True,
            "ai_label_confirmed": True,
            "status": "live",
        },
        headers=headers,
    )
    assert resp.status_code == 422
    assert any("脚本" in item for item in resp.json()["detail"]["items"])

    # 定稿后开播 OK（失败回滚，需重新提交完整前置项）
    _confirm(client, project["id"], s1["id"])
    resp = client.patch(
        f"/api/v1/live-projects/{project['id']}/sessions/{session['id']}",
        json={
            "operator_id": operator,
            "duty_confirmed": True,
            "ai_label_confirmed": True,
            "status": "live",
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "live"


def test_session_cancel_and_backfill(client, monkeypatch):
    _patch_agents(monkeypatch)
    headers = auth_headers(client)
    project = _create_project(client)

    # planned → cancelled
    s_cancel = _create_session(client, project["id"])
    resp = client.patch(
        f"/api/v1/live-projects/{project['id']}/sessions/{s_cancel['id']}",
        json={"status": "cancelled"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"
    # 终态不可逆
    assert client.patch(
        f"/api/v1/live-projects/{project['id']}/sessions/{s_cancel['id']}",
        json={"status": "live"},
        headers=headers,
    ).status_code == 400

    # planned → ended 补录：缺时间 → 422
    s_back = _create_session(client, project["id"])
    resp = client.patch(
        f"/api/v1/live-projects/{project['id']}/sessions/{s_back['id']}",
        json={"status": "ended"},
        headers=headers,
    )
    assert resp.status_code == 422

    # 补录成功 → is_backfilled=true
    resp = client.patch(
        f"/api/v1/live-projects/{project['id']}/sessions/{s_back['id']}",
        json={
            "status": "ended",
            "started_at": "2026-08-10T20:00:00+08:00",
            "ended_at": "2026-08-10T21:00:00+08:00",
        },
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["is_backfilled"] is True
    assert resp.json()["status"] == "ended"


def test_session_live_locked_and_delete_rules(client, monkeypatch):
    _patch_agents(monkeypatch)
    headers = auth_headers(client)
    project = _create_project(client)
    operator = current_user_id(client)

    s_live = _create_session(client, project["id"])
    _patch_session(
        client,
        project["id"],
        s_live["id"],
        {
            "operator_id": operator,
            "duty_confirmed": True,
            "ai_label_confirmed": True,
            "status": "live",
        },
    )
    # live：绑定/排期字段锁定
    assert client.patch(
        f"/api/v1/live-projects/{project['id']}/sessions/{s_live['id']}",
        json={"duration_min": 120},
        headers=headers,
    ).status_code == 400
    # live 只能流转到 ended
    assert client.patch(
        f"/api/v1/live-projects/{project['id']}/sessions/{s_live['id']}",
        json={"status": "cancelled"},
        headers=headers,
    ).status_code == 400
    # 已开播禁止 DELETE
    assert client.delete(
        f"/api/v1/live-projects/{project['id']}/sessions/{s_live['id']}",
        headers=headers,
    ).status_code == 400

    s_ended = _create_session(client, project["id"])
    _patch_session(
        client,
        project["id"],
        s_ended["id"],
        {
            "operator_id": operator,
            "duty_confirmed": True,
            "ai_label_confirmed": True,
            "status": "live",
        },
    )
    _patch_session(client, project["id"], s_ended["id"], {"status": "ended"})
    assert client.delete(
        f"/api/v1/live-projects/{project['id']}/sessions/{s_ended['id']}",
        headers=headers,
    ).status_code == 400

    # planned 可删除
    s_planned = _create_session(client, project["id"])
    assert client.delete(
        f"/api/v1/live-projects/{project['id']}/sessions/{s_planned['id']}",
        headers=headers,
    ).status_code == 200


# ============================================================
# 复盘 / 级联
# ============================================================


def test_metrics_and_review(client, monkeypatch):
    _patch_agents(monkeypatch)
    headers = auth_headers(client)
    project = _create_project(client)
    session = _create_session(client, project["id"])
    sid = session["id"]

    # 无 metrics → review 400
    resp = client.post(
        f"/api/v1/live-projects/{project['id']}/sessions/{sid}/review",
        headers=headers,
    )
    assert resp.status_code == 400

    # 录入 metrics（重复提交覆盖）
    metrics = {
        "viewers": 1200,
        "peak_viewers": 300,
        "avg_watch_sec": 240,
        "interaction_count": 80,
        "danmaku_count": 150,
        "order_count": 12,
        "gmv": 1056.0,
        "redemption_count": 8,
        "note": "开场前 5 分钟引流效果一般",
    }
    resp = client.post(
        f"/api/v1/live-projects/{project['id']}/sessions/{sid}/metrics",
        json={"metrics": metrics, "source": "manual"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["metrics"]["viewers"] == 1200

    resp2 = client.post(
        f"/api/v1/live-projects/{project['id']}/sessions/{sid}/metrics",
        json={"metrics": {**metrics, "viewers": 1300}},
        headers=headers,
    )
    assert resp2.json()["metrics"]["viewers"] == 1300

    # review
    resp = client.post(
        f"/api/v1/live-projects/{project['id']}/sessions/{sid}/review",
        headers=headers,
    )
    assert resp.status_code == 200
    assert "复盘报告" in resp.json()["ai_review"]

    # ai_review 已写入
    metric = client.get(
        f"/api/v1/live-projects/{project['id']}/sessions/{sid}/metrics",
        headers=headers,
    ).json()
    assert metric["ai_review"] == resp.json()["ai_review"]


def test_review_rate_limited(client, monkeypatch):
    _patch_agents(monkeypatch, peek=_peek_limited)
    headers = auth_headers(client)
    project = _create_project(client)
    session = _create_session(client, project["id"])
    client.post(
        f"/api/v1/live-projects/{project['id']}/sessions/{session['id']}/metrics",
        json={"metrics": {"viewers": 100}},
        headers=headers,
    )
    resp = client.post(
        f"/api/v1/live-projects/{project['id']}/sessions/{session['id']}/review",
        headers=headers,
    )
    assert resp.status_code == 429


def test_cascade_delete_project(client, monkeypatch):
    _patch_agents(monkeypatch)
    headers = auth_headers(client)
    project = _create_project(client)
    avatar = _create_avatar(client, persona=_PERSONA)
    script = _generate(client, project["id"], avatar_id=avatar["id"])
    _confirm(client, project["id"], script["id"])
    client.post(
        f"/api/v1/live-projects/{project['id']}/danmaku-config/generate",
        headers=headers,
    )
    session = _create_session(client, project["id"])
    client.post(
        f"/api/v1/live-projects/{project['id']}/sessions/{session['id']}/metrics",
        json={"metrics": {"viewers": 100}},
        headers=headers,
    )

    assert client.delete(
        f"/api/v1/live-projects/{project['id']}", headers=headers
    ).status_code == 200
    # 子资源随项目级联删除
    assert client.get(
        f"/api/v1/live-projects/{project['id']}/scripts", headers=headers
    ).status_code == 404
    assert client.get(
        f"/api/v1/live-projects/{project['id']}/danmaku-config", headers=headers
    ).status_code == 404
    assert client.get(
        f"/api/v1/live-projects/{project['id']}/sessions", headers=headers
    ).status_code == 404
    # 形象是 org 维度，不随项目删除
    assert client.get(
        f"/api/v1/live-avatars/{avatar['id']}", headers=headers
    ).status_code == 200


def test_session_sensitive_notes_422(client, monkeypatch):
    _patch_agents(monkeypatch)
    project = _create_project(client)
    resp = client.post(
        f"/api/v1/live-projects/{project['id']}/sessions",
        json={"scheduled_at": "2026-08-10T20:00:00+08:00", "notes": "赌博引流"},
        headers=auth_headers(client),
    )
    assert resp.status_code == 422





