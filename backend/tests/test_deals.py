"""G1 团购工坊后端测试。

运行方式：
    cd D:\two\backend
    pytest tests/test_deals.py -v

需要 Postgres + Redis + MinIO 运行中（docker compose up -d）。
AI Agent 与频控全部 monkeypatch，不调用真实 LLM / Redis。
"""
from __future__ import annotations

import asyncio
import io
import os

import pytest
from PIL import Image
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.ai.deal_agent import DealAgentError
from app.ai.deal_copy_agent import build_system_prompt


def _make_png(size=(64, 64), color=(210, 110, 50)) -> bytes:
    img = Image.new("RGB", size, color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ============================================================
# Helpers
# ============================================================


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
        json={"name": "测试门店", "category": "火锅"},
        headers=headers,
    )
    return s_resp.json()["id"]


def _create_project(
    client, shop_id: str | None = None, platform: str = "douyin", title: str = "抖音暑期套餐"
) -> dict:
    headers = auth_headers(client)
    shop_id = shop_id or _create_shop(client)
    resp = client.post(
        "/api/v1/deal-projects",
        json={"shop_id": shop_id, "title": title, "platform": platform},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _create_item(client, project_id: str, **overrides) -> dict:
    headers = auth_headers(client)
    data = {
        "name": "招牌毛肚",
        "category": "signature",
        "cost_price": 20.0,
        "sale_price": 68.0,
        "is_signature": True,
        "is_high_margin": False,
    }
    data.update(overrides)
    resp = client.post(
        f"/api/v1/deal-projects/{project_id}/items",
        json=data,
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _create_competitor(client, project_id: str, **overrides) -> dict:
    headers = auth_headers(client)
    data = {
        "name": "隔壁火锅双人餐",
        "price": 99.0,
        "items_summary": "招牌毛肚+肥牛+冰粉",
        "note": "抖音爆款",
    }
    data.update(overrides)
    resp = client.post(
        f"/api/v1/deal-projects/{project_id}/competitor-deals",
        json=data,
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _setup_project_with_items(client, platform: str = "douyin") -> tuple[dict, list[dict]]:
    """创建项目 + 三件菜品（招牌/高毛利/小吃）。"""
    project = _create_project(client, platform=platform)
    sig = _create_item(
        client, project["id"],
        name="招牌毛肚", category="signature", cost_price=20.0,
        sale_price=68.0, is_signature=True, is_high_margin=False,
    )
    hm = _create_item(
        client, project["id"],
        name="雪花肥牛", category="staple", cost_price=25.0,
        sale_price=58.0, is_signature=False, is_high_margin=True,
    )
    snack = _create_item(
        client, project["id"],
        name="红糖冰粉", category="snack", cost_price=2.0,
        sale_price=12.0, is_signature=False, is_high_margin=False,
    )
    return project, [sig, hm, snack]


async def _stub_generate_schemes(
    self, *, shop_name, category, platform, price_band, items, competitor_deals
):
    sig = next((it for it in items if it["is_signature"]), items[0])
    hm = next((it for it in items if it["is_high_margin"]), items[0])
    snack = next((it for it in items if it["category"] == "snack"), items[-1])

    def ref(it, qty=1):
        return {"item_id": it["id"], "qty": qty, "cost_price": it["cost_price"]}

    return [
        {
            "scheme_type": "hook",
            "title": "引流款·招牌单人餐",
            "description": "低价拉新到店",
            "original_price": float(sig["sale_price"]),
            "deal_price": 39.9,
            "items": [ref(sig)],
        },
        {
            "scheme_type": "profit",
            "title": "利润款·双人招牌套餐",
            "description": "招牌+高毛利托底",
            "original_price": float(sig["sale_price"]) + float(hm["sale_price"]),
            "deal_price": 88.0,
            "items": [ref(sig), ref(hm)],
        },
        {
            "scheme_type": "scenario",
            "title": "场景款·宵夜双拼",
            "description": "宵夜补时段",
            "original_price": float(snack["sale_price"]) * 2,
            "deal_price": 19.9,
            "items": [ref(snack, 2)],
        },
    ]


async def _stub_generate_negative(self, **kwargs):
    sig = next((it for it in kwargs["items"] if it["is_signature"]), kwargs["items"][0])
    hm = next((it for it in kwargs["items"] if it["is_high_margin"]), kwargs["items"][0])
    return [
        {
            "scheme_type": "hook",
            "title": "引流款·亏本引流",
            "description": "",
            "original_price": float(sig["sale_price"]),
            "deal_price": 39.9,
            "items": [{"item_id": sig["id"], "qty": 1, "cost_price": sig["cost_price"]}],
        },
        {
            "scheme_type": "profit",
            "title": "利润款·负毛利方案",
            "description": "",
            "original_price": float(sig["sale_price"]) + float(hm["sale_price"]),
            "deal_price": 30.0,
            "items": [
                {"item_id": sig["id"], "qty": 1, "cost_price": sig["cost_price"]},
                {"item_id": hm["id"], "qty": 1, "cost_price": hm["cost_price"]},
            ],
        },
        {
            "scheme_type": "scenario",
            "title": "场景款·宵夜",
            "description": "",
            "original_price": 24.0,
            "deal_price": 19.9,
            "items": [{"item_id": kwargs["items"][-1]["id"], "qty": 2, "cost_price": kwargs["items"][-1]["cost_price"]}],
        },
    ]


async def _stub_copy_generate(self, *, platform, shop_name, shop_category, scheme):
    return {
        "title": f"{platform}标题",
        "selling_points": ["卖点一", "卖点二", "卖点三"],
        "rules": "仅限工作日午餐，每桌限用1份",
        "cover_prompt": f"{platform}封面提示词",
    }


def _make_counter_copy_stub():
    calls = {"douyin": 0, "meituan": 0, "xiaohongshu": 0}

    async def stub(self, *, platform, shop_name, shop_category, scheme):
        calls[platform] += 1
        n = calls[platform]
        return {
            "title": f"{platform}标题#{n}",
            "selling_points": [f"卖点{n}"],
            "rules": "规则",
            "cover_prompt": f"{platform}封面#{n}",
        }

    return stub


async def _peek_ok(*args, **kwargs):
    return True


async def _peek_limited(*args, **kwargs):
    return False


async def _set_noop(*args, **kwargs):
    return None


def _patch_agents(monkeypatch, generate_stub=None, copy_stub=None, peek=None, set_=None):
    monkeypatch.setattr(
        "app.ai.deal_agent.DealAgent.generate_schemes",
        generate_stub or _stub_generate_schemes,
    )
    monkeypatch.setattr(
        "app.ai.deal_copy_agent.DealCopyAgent.generate",
        copy_stub or _stub_copy_generate,
    )
    monkeypatch.setattr("app.api.v1.deals.peek_rate_limit", peek or _peek_ok)
    monkeypatch.setattr("app.api.v1.deals.set_rate_limit", set_ or _set_noop)


def _generate(client, project_id: str) -> dict:
    resp = client.post(
        f"/api/v1/deal-projects/{project_id}/schemes/generate",
        headers=auth_headers(client),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _db_count(project_id: str) -> dict[str, int]:
    """跨事件循环直接查库，验证级联删除。"""
    async def _run() -> dict[str, int]:
        engine = create_async_engine(os.environ["DATABASE_URL"])
        out = {}
        try:
            async with engine.connect() as conn:
                for table in ("deal_items", "competitor_deals", "deal_schemes"):
                    r = await conn.execute(
                        text(f"SELECT count(*) FROM {table} WHERE project_id = :pid"),
                        {"pid": project_id},
                    )
                    out[table] = r.scalar_one()
                r = await conn.execute(
                    text(
                        "SELECT count(*) FROM deal_scheme_copies c "
                        "JOIN deal_schemes s ON c.scheme_id = s.id "
                        "WHERE s.project_id = :pid"
                    ),
                    {"pid": project_id},
                )
                out["deal_scheme_copies"] = r.scalar_one()
        finally:
            await engine.dispose()
        return out

    return asyncio.run(_run())


# ============================================================
# 项目 CRUD / 鉴权 / 分页
# ============================================================


def test_project_crud_and_pagination(client):
    project = _create_project(client)
    pid = project["id"]
    headers = auth_headers(client)

    get_resp = client.get(f"/api/v1/deal-projects/{pid}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["platform"] == "douyin"
    assert get_resp.json()["status"] == "draft"

    patch_resp = client.patch(
        f"/api/v1/deal-projects/{pid}",
        json={"title": "改名项目", "platform": "meituan", "price_band": "人均100"},
        headers=headers,
    )
    assert patch_resp.status_code == 200
    body = patch_resp.json()
    assert body["title"] == "改名项目"
    assert body["platform"] == "meituan"
    assert body["price_band"] == "人均100"

    # 分页
    list_resp = client.get(
        f"/api/v1/deal-projects?shop_id={project['shop_id']}&page=1&page_size=1",
        headers=headers,
    )
    assert list_resp.status_code == 200
    data = list_resp.json()
    assert data["total"] >= 1
    assert data["size"] == 1
    assert len(data["items"]) == 1

    del_resp = client.delete(f"/api/v1/deal-projects/{pid}", headers=headers)
    assert del_resp.status_code == 200
    assert client.get(
        f"/api/v1/deal-projects/{pid}", headers=headers
    ).status_code == 404


def test_project_requires_auth(client):
    assert client.get("/api/v1/deal-projects").status_code == 401


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
        f"/api/v1/deal-projects/{project['id']}", headers=other_headers
    ).status_code == 404
    assert client.post(
        f"/api/v1/deal-projects/{project['id']}/schemes/generate",
        headers=other_headers,
    ).status_code == 404


def test_project_sensitive_title_422(client):
    headers = auth_headers(client)
    shop_id = _create_shop(client)
    resp = client.post(
        "/api/v1/deal-projects",
        json={"shop_id": shop_id, "title": "赌博引流套餐"},
        headers=headers,
    )
    assert resp.status_code == 422


# ============================================================
# 菜品 / 竞品 CRUD
# ============================================================


def test_item_crud_and_category_enum(client):
    project = _create_project(client)
    pid = project["id"]
    headers = auth_headers(client)

    item = _create_item(client, pid)
    iid = item["id"]

    list_resp = client.get(f"/api/v1/deal-projects/{pid}/items", headers=headers)
    assert list_resp.status_code == 200
    assert list_resp.json()["total"] == 1

    patch_resp = client.patch(
        f"/api/v1/deal-projects/{pid}/items/{iid}",
        json={"sale_price": 99.0, "is_high_margin": True},
        headers=headers,
    )
    assert patch_resp.status_code == 200
    assert float(patch_resp.json()["sale_price"]) == 99.0
    assert patch_resp.json()["is_high_margin"] is True

    del_resp = client.delete(f"/api/v1/deal-projects/{pid}/items/{iid}", headers=headers)
    assert del_resp.status_code == 200
    assert client.get(f"/api/v1/deal-projects/{pid}/items", headers=headers).json()["total"] == 0

    # category 枚举越界（FastAPI 统一 422 校验失败语义）
    resp = client.post(
        f"/api/v1/deal-projects/{pid}/items",
        json={"name": "非法品类", "category": "xxx", "sale_price": 10},
        headers=headers,
    )
    assert resp.status_code == 422


def test_item_sensitive_name_422(client):
    project = _create_project(client)
    headers = auth_headers(client)
    resp = client.post(
        f"/api/v1/deal-projects/{project['id']}/items",
        json={"name": "赌博小吃", "category": "snack", "sale_price": 10},
        headers=headers,
    )
    assert resp.status_code == 422


def test_competitor_crud_and_sensitive(client):
    project = _create_project(client)
    pid = project["id"]
    headers = auth_headers(client)

    comp = _create_competitor(client, pid)
    cid = comp["id"]
    list_resp = client.get(f"/api/v1/deal-projects/{pid}/competitor-deals", headers=headers)
    assert list_resp.status_code == 200
    assert list_resp.json()["total"] == 1
    assert list_resp.json()["items"][0]["name"] == "隔壁火锅双人餐"

    patch_resp = client.patch(
        f"/api/v1/deal-projects/{pid}/competitor-deals/{cid}",
        json={"price": 89.0, "note": "改过备注"},
        headers=headers,
    )
    assert patch_resp.status_code == 200
    assert float(patch_resp.json()["price"]) == 89.0
    assert patch_resp.json()["note"] == "改过备注"

    del_resp = client.delete(f"/api/v1/deal-projects/{pid}/competitor-deals/{cid}", headers=headers)
    assert del_resp.status_code == 200
    assert client.get(
        f"/api/v1/deal-projects/{pid}/competitor-deals", headers=headers
    ).json()["total"] == 0

    resp = client.post(
        f"/api/v1/deal-projects/{pid}/competitor-deals",
        json={"name": "博彩套餐", "price": 9.9, "items_summary": "xxx"},
        headers=headers,
    )
    assert resp.status_code == 422


# ============================================================
# 方案生成 / 毛利 / regenerate / 快照
# ============================================================


def test_generate_three_types_and_margins(client, monkeypatch):
    _patch_agents(monkeypatch)
    project, items = _setup_project_with_items(client)
    data = _generate(client, project["id"])

    assert data["generation_batch"] == 1
    schemes = data["schemes"]
    assert len(schemes) == 3
    assert {s["scheme_type"] for s in schemes} == {"hook", "profit", "scenario"}
    assert all(s["status"] == "draft" for s in schemes)

    profit = next(s for s in schemes if s["scheme_type"] == "profit")
    # 招牌菜必含 + 快照字段
    sig_id = items[0]["id"]
    assert any(it["item_id"] == sig_id for it in profit["items"])
    snap_sig = next(it for it in profit["items"] if it["item_id"] == sig_id)
    assert snap_sig["name"] == "招牌毛肚"
    assert float(snap_sig["sale_price"]) == 68.0
    assert float(snap_sig["cost_price"]) == 20.0

    # 毛利公式：profit = 毛肚20 + 肥牛25，deal 88，抖音佣金 0.06
    margin = profit["margin_estimate"]
    assert margin["platform_commission_rate"] == 0.06
    assert margin["gross_margin"] == pytest.approx((88 - 45) / 88, abs=1e-4)
    assert margin["net_margin"] == pytest.approx((88 * 0.94 - 45) / 88, abs=1e-4)

    # 项目状态更新
    detail = client.get(
        f"/api/v1/deal-projects/{project['id']}",
        headers=auth_headers(client),
    ).json()
    assert detail["status"] == "generated"


def test_generate_rate_limit_429(client, monkeypatch):
    _patch_agents(monkeypatch, peek=_peek_limited)
    project, _ = _setup_project_with_items(client)
    resp = client.post(
        f"/api/v1/deal-projects/{project['id']}/schemes/generate",
        headers=auth_headers(client),
    )
    assert resp.status_code == 429


def test_regenerate_archives_old_batch(client, monkeypatch):
    _patch_agents(monkeypatch)
    project, _ = _setup_project_with_items(client)
    headers = auth_headers(client)

    data1 = _generate(client, project["id"])
    assert data1["generation_batch"] == 1

    # 人工编辑一个方案，regenerate 时同样被归档
    edited = data1["schemes"][0]
    put_resp = client.put(
        f"/api/v1/deal-projects/{project['id']}/schemes/{edited['id']}",
        json={"title": "人工改过的标题"},
        headers=headers,
    )
    assert put_resp.status_code == 200
    assert put_resp.json()["status"] == "edited"

    data2 = _generate(client, project["id"])
    assert data2["generation_batch"] == 2
    assert all(s["is_archived"] is False for s in data2["schemes"])
    assert all(s["status"] == "draft" for s in data2["schemes"])

    # 默认只返回活跃批次
    active = client.get(
        f"/api/v1/deal-projects/{project['id']}/schemes",
        headers=headers,
    ).json()
    assert len(active) == 3
    assert all(s["generation_batch"] == 2 for s in active)

    # include_archived 返回历史批次
    all_schemes = client.get(
        f"/api/v1/deal-projects/{project['id']}/schemes?include_archived=true",
        headers=headers,
    ).json()
    assert len(all_schemes) == 6
    archived = [s for s in all_schemes if s["is_archived"]]
    assert len(archived) == 3
    assert all(s["generation_batch"] == 1 for s in archived)
    # edited 方案确实被归档且保留编辑状态
    old_edited = next(s for s in archived if s["id"] == edited["id"])
    assert old_edited["status"] == "edited"
    assert old_edited["title"] == "人工改过的标题"


def test_snapshot_not_affected_by_item_changes(client, monkeypatch):
    _patch_agents(monkeypatch)
    project, items = _setup_project_with_items(client)
    headers = auth_headers(client)

    data = _generate(client, project["id"])
    sig_id = items[0]["id"]
    profit = next(s for s in data["schemes"] if s["scheme_type"] == "profit")
    snap_sig = next(it for it in profit["items"] if it["item_id"] == sig_id)
    assert float(snap_sig["sale_price"]) == 68.0

    # 修改菜品清单（改价 + 取消招牌标记）
    patch_resp = client.patch(
        f"/api/v1/deal-projects/{project['id']}/items/{sig_id}",
        json={"sale_price": 128.0, "is_signature": False},
        headers=headers,
    )
    assert patch_resp.status_code == 200

    schemes = client.get(
        f"/api/v1/deal-projects/{project['id']}/schemes",
        headers=headers,
    ).json()
    profit2 = next(s for s in schemes if s["scheme_type"] == "profit")
    snap2 = next(it for it in profit2["items"] if it["item_id"] == sig_id)
    assert float(snap2["sale_price"]) == 68.0  # 快照不受影响


def test_negative_net_margin_warns_but_saves(client, monkeypatch):
    _patch_agents(monkeypatch, generate_stub=_stub_generate_negative)
    project, _ = _setup_project_with_items(client)
    data = _generate(client, project["id"])
    profit = next(s for s in data["schemes"] if s["scheme_type"] == "profit")
    margin = profit["margin_estimate"]
    assert margin["net_margin"] < 0
    assert "净毛利为负" in margin["note"]
    assert profit["status"] == "draft"  # 不硬拒，允许保存


# ============================================================
# 敏感词 / AI 格式错误：422 / 502 且不占频控
# ============================================================


def test_sensitive_ai_output_422_and_no_rate_consume(client, monkeypatch):
    async def _blocked(self, **kwargs):
        raise DealAgentError("生成内容包含敏感词")

    recorded: list[str] = []
    async def _set_record(*args, **kwargs):
        recorded.append("set")

    _patch_agents(monkeypatch, generate_stub=_blocked, set_=_set_record)
    project, _ = _setup_project_with_items(client)
    resp = client.post(
        f"/api/v1/deal-projects/{project['id']}/schemes/generate",
        headers=auth_headers(client),
    )
    assert resp.status_code == 422
    assert recorded == []  # 未计入频控

    # 换回正常 agent，再次生成应成功（窗口未被占用）
    _patch_agents(monkeypatch, set_=_set_record)
    resp = client.post(
        f"/api/v1/deal-projects/{project['id']}/schemes/generate",
        headers=auth_headers(client),
    )
    assert resp.status_code == 200
    assert recorded == ["set"]


def test_agent_format_error_502_and_no_rate_consume(client, monkeypatch):
    async def _bad(self, **kwargs):
        raise DealAgentError("LLM 返回方案数量不是 3 款")

    recorded: list[str] = []
    async def _set_record(*args, **kwargs):
        recorded.append("set")

    _patch_agents(monkeypatch, generate_stub=_bad, set_=_set_record)
    project, _ = _setup_project_with_items(client)
    resp = client.post(
        f"/api/v1/deal-projects/{project['id']}/schemes/generate",
        headers=auth_headers(client),
    )
    assert resp.status_code == 502
    assert recorded == []


# ============================================================
# 平台文案 copy / export
# ============================================================


def _generate_and_take(client, project_id: str, scheme_type: str = "profit") -> dict:
    data = _generate(client, project_id)
    return next(s for s in data["schemes"] if s["scheme_type"] == scheme_type)


def test_copy_multi_platform_and_overwrite(client, monkeypatch):
    copy_stub = _make_counter_copy_stub()
    _patch_agents(monkeypatch, copy_stub=copy_stub)
    project, _ = _setup_project_with_items(client)
    headers = auth_headers(client)
    scheme = _generate_and_take(client, project["id"])

    r1 = client.post(
        f"/api/v1/deal-projects/{project['id']}/schemes/{scheme['id']}/copy",
        json={"platform": "douyin"},
        headers=headers,
    )
    assert r1.status_code == 200, r1.text
    assert r1.json()["title"] == "douyin标题#1"

    r2 = client.post(
        f"/api/v1/deal-projects/{project['id']}/schemes/{scheme['id']}/copy",
        json={"platform": "meituan"},
        headers=headers,
    )
    assert r2.status_code == 200
    assert r2.json()["title"] == "meituan标题#1"

    # 同平台重复生成 = 覆盖更新，其余平台不受影响
    r3 = client.post(
        f"/api/v1/deal-projects/{project['id']}/schemes/{scheme['id']}/copy",
        json={"platform": "douyin"},
        headers=headers,
    )
    assert r3.status_code == 200
    assert r3.json()["title"] == "douyin标题#2"

    copies = client.get(
        f"/api/v1/deal-projects/{project['id']}/schemes/{scheme['id']}/copies",
        headers=headers,
    ).json()
    assert len(copies) == 2
    by_platform = {c["platform"]: c for c in copies}
    assert by_platform["douyin"]["title"] == "douyin标题#2"
    assert by_platform["meituan"]["title"] == "meituan标题#1"
    assert by_platform["douyin"]["cover_prompt"] == "douyin封面#2"


async def _peek_block_copy(key, *args, **kwargs):
    # 只限制 copy 频控（key 含 "deals:copy:"），generate 放行
    return "deals:copy:" not in key


def test_copy_rate_limit_429(client, monkeypatch):
    _patch_agents(monkeypatch, peek=_peek_block_copy)
    project, _ = _setup_project_with_items(client)
    scheme = _generate_and_take(client, project["id"])
    resp = client.post(
        f"/api/v1/deal-projects/{project['id']}/schemes/{scheme['id']}/copy",
        json={"platform": "douyin"},
        headers=auth_headers(client),
    )
    assert resp.status_code == 429


def test_export_to_design(client, monkeypatch):
    _patch_agents(monkeypatch)
    project, _ = _setup_project_with_items(client)
    headers = auth_headers(client)
    scheme = _generate_and_take(client, project["id"])

    # 未生成该平台 copy → 400
    resp = client.post(
        f"/api/v1/deal-projects/{project['id']}/schemes/{scheme['id']}/export-to-design",
        json={"platform": "xiaohongshu"},
        headers=headers,
    )
    assert resp.status_code == 400

    client.post(
        f"/api/v1/deal-projects/{project['id']}/schemes/{scheme['id']}/copy",
        json={"platform": "douyin"},
        headers=headers,
    )
    resp = client.post(
        f"/api/v1/deal-projects/{project['id']}/schemes/{scheme['id']}/export-to-design",
        json={"platform": "douyin"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["design_project_id"]
    assert len(data["asset_ids"]) == 1

    # 校验 design asset：source=deals + cover_prompt 写入 beauty_config
    assets = client.get(
        f"/api/v1/design-projects/{data['design_project_id']}/assets",
        headers=headers,
    ).json()
    assert len(assets) == 1
    asset = assets[0]
    assert asset["source"] == "deals"
    assert asset["asset_type"] == "photo"
    assert asset["beauty_config"]["cover_prompt"] == "douyin封面提示词"
    assert asset["tagline"] == "douyin标题"


def test_archived_scheme_copies_still_queryable(client, monkeypatch):
    _patch_agents(monkeypatch)
    project, _ = _setup_project_with_items(client)
    headers = auth_headers(client)

    data1 = _generate(client, project["id"])
    scheme1 = data1["schemes"][0]
    client.post(
        f"/api/v1/deal-projects/{project['id']}/schemes/{scheme1['id']}/copy",
        json={"platform": "douyin"},
        headers=headers,
    )

    _generate(client, project["id"])  # regenerate → 归档 batch1

    # 归档方案的 copies 物理保留、仍可查询
    copies = client.get(
        f"/api/v1/deal-projects/{project['id']}/schemes/{scheme1['id']}/copies",
        headers=headers,
    ).json()
    assert len(copies) == 1
    assert copies[0]["platform"] == "douyin"

    # include_archived 列表里归档方案带 copies
    all_schemes = client.get(
        f"/api/v1/deal-projects/{project['id']}/schemes?include_archived=true",
        headers=headers,
    ).json()
    archived = next(s for s in all_schemes if s["id"] == scheme1["id"])
    assert archived["is_archived"] is True
    assert len(archived["copies"]) == 1


def test_update_and_delete_scheme(client, monkeypatch):
    _patch_agents(monkeypatch)
    project, _ = _setup_project_with_items(client)
    headers = auth_headers(client)
    scheme = _generate_and_take(client, project["id"])

    put_resp = client.put(
        f"/api/v1/deal-projects/{project['id']}/schemes/{scheme['id']}",
        json={"title": "人工改标题", "deal_price": 66.0},
        headers=headers,
    )
    assert put_resp.status_code == 200
    assert put_resp.json()["status"] == "edited"
    assert put_resp.json()["title"] == "人工改标题"
    assert float(put_resp.json()["deal_price"]) == 66.0

    # 敏感词编辑 422
    resp = client.put(
        f"/api/v1/deal-projects/{project['id']}/schemes/{scheme['id']}",
        json={"title": "赌博方案"},
        headers=headers,
    )
    assert resp.status_code == 422

    # 删除方案
    del_resp = client.delete(
        f"/api/v1/deal-projects/{project['id']}/schemes/{scheme['id']}",
        headers=headers,
    )
    assert del_resp.status_code == 200
    remaining = client.get(
        f"/api/v1/deal-projects/{project['id']}/schemes",
        headers=headers,
    ).json()
    assert len(remaining) == 2


# ============================================================
# 级联删除
# ============================================================


def test_cascade_delete_project(client, monkeypatch):
    _patch_agents(monkeypatch)
    project, _ = _setup_project_with_items(client)
    headers = auth_headers(client)
    scheme = _generate_and_take(client, project["id"])
    client.post(
        f"/api/v1/deal-projects/{project['id']}/schemes/{scheme['id']}/copy",
        json={"platform": "douyin"},
        headers=headers,
    )

    counts_before = _db_count(project["id"])
    assert counts_before["deal_items"] == 3
    assert counts_before["deal_schemes"] == 3
    assert counts_before["deal_scheme_copies"] == 1

    del_resp = client.delete(f"/api/v1/deal-projects/{project['id']}", headers=headers)
    assert del_resp.status_code == 200

    counts_after = _db_count(project["id"])
    assert counts_after == {
        "deal_items": 0,
        "competitor_deals": 0,
        "deal_schemes": 0,
        "deal_scheme_copies": 0,
    }






# ============================================================
# 图片上传 / copy 人工编辑（G2 补充端点）
# ============================================================


def test_item_image_upload(client, monkeypatch):
    _patch_agents(monkeypatch)
    project, _ = _setup_project_with_items(client)
    headers = auth_headers(client)
    item = _create_item(client, project["id"])

    name = "dish.png"
    buf = io.BytesIO(_make_png())
    buf.seek(0)
    resp = client.post(
        f"/api/v1/deal-projects/{project['id']}/items/{item['id']}/image",
        files={"file": (name, buf, "image/png")},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["image_url"].startswith("http")

    # 列表返回预签名 URL
    listed = client.get(
        f"/api/v1/deal-projects/{project['id']}/items",
        headers=headers,
    ).json()
    match = next(i for i in listed["items"] if i["id"] == item["id"])
    assert match["image_url"].startswith("http")


def test_item_image_upload_bad_type(client, monkeypatch):
    project, _ = _setup_project_with_items(client)
    headers = auth_headers(client)
    item = _create_item(client, project["id"])
    resp = client.post(
        f"/api/v1/deal-projects/{project['id']}/items/{item['id']}/image",
        files={"file": ("a.txt", io.BytesIO(b"not image"), "text/plain")},
        headers=headers,
    )
    assert resp.status_code == 400


def test_copy_patch_updates_only_that_platform(client, monkeypatch):
    _patch_agents(monkeypatch)
    project, _ = _setup_project_with_items(client)
    headers = auth_headers(client)
    scheme = _generate_and_take(client, project["id"])

    client.post(
        f"/api/v1/deal-projects/{project['id']}/schemes/{scheme['id']}/copy",
        json={"platform": "douyin"},
        headers=headers,
    )
    client.post(
        f"/api/v1/deal-projects/{project['id']}/schemes/{scheme['id']}/copy",
        json={"platform": "meituan"},
        headers=headers,
    )

    copies = client.get(
        f"/api/v1/deal-projects/{project['id']}/schemes/{scheme['id']}/copies",
        headers=headers,
    ).json()
    douyin = next(c for c in copies if c["platform"] == "douyin")
    meituan = next(c for c in copies if c["platform"] == "meituan")

    resp = client.patch(
        f"/api/v1/deal-projects/{project['id']}/schemes/{scheme['id']}/copies/{douyin['id']}",
        json={"title": "人工改的抖音标题", "selling_points": ["新卖点A", "新卖点B"]},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "人工改的抖音标题"
    assert resp.json()["selling_points"] == ["新卖点A", "新卖点B"]

    # 其余平台不受影响
    meituan_after = next(
        c
        for c in client.get(
            f"/api/v1/deal-projects/{project['id']}/schemes/{scheme['id']}/copies",
            headers=headers,
        ).json()
        if c["platform"] == "meituan"
    )
    assert meituan_after["title"] == meituan["title"]

    # 敏感词 422
    resp = client.patch(
        f"/api/v1/deal-projects/{project['id']}/schemes/{scheme['id']}/copies/{douyin['id']}",
        json={"title": "赌博标题"},
        headers=headers,
    )
    assert resp.status_code == 422


# ============================================================
# copy agent 系统提示词（回归：.format 撞 JSON 大括号 500）
# ============================================================


def test_copy_system_prompt_builds_without_error():
    # 此前 _SYSTEM_PROMPT.format(...) 会把 JSON 示例的大括号当占位符 → KeyError 500
    for platform in ("douyin", "meituan", "xiaohongshu"):
        prompt = build_system_prompt(platform)
        assert "平台策略：" in prompt
        # JSON 结构示例的大括号必须保留
        assert '"title"' in prompt
        assert '"selling_points"' in prompt
        assert '"cover_prompt"' in prompt
    # 平台差异化文案确实注入
    assert "数字+场景+情绪" in build_system_prompt("douyin")
    assert "品类关键词前置" in build_system_prompt("meituan")
    assert "3:4 种草风" in build_system_prompt("xiaohongshu")

