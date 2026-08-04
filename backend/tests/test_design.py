"""D1 视觉设计模块测试。

运行方式：
    cd D:\two\backend
    pytest tests/test_design.py -v

需要 Postgres + Redis + MinIO 运行中（docker compose up -d）。
"""
from __future__ import annotations

import base64
import io
import uuid
from pathlib import Path

import pytest
from PIL import Image, ImageStat
from pydantic import ValidationError


def _make_png(size=(128, 96), color=(210, 110, 50)) -> bytes:
    img = Image.new("RGB", size, color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _png_upload(name: str = "dish.png") -> tuple[str, io.BytesIO, str]:
    buf = io.BytesIO(_make_png())
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


def _create_project(client, shop_id: str | None = None, title: str = "测试项目") -> dict:
    headers = auth_headers(client)
    shop_id = shop_id or _create_shop(client)
    resp = client.post(
        "/api/v1/design-projects",
        json={"shop_id": shop_id, "title": title},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _upload_dish(
    client,
    project_id: str,
    dish_name: str = "红烧肉",
    price: str = "38",
) -> dict:
    name, buf, mime = _png_upload()
    resp = client.post(
        f"/api/v1/design-projects/{project_id}/assets",
        data={
            "asset_type": "dish",
            "dish_name": dish_name,
            "price": price,
            "tagline": "现点现做",
        },
        files={"file": (name, buf, mime)},
        headers=auth_headers(client),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _stub_generate_edited(prompt, ref_data=None, ref_mime="image/png", on_progress=None):
    return [(_make_png((160, 120), (190, 90, 40)), "image/png") for _ in range(4)]


def _asset_status(client, project_id: str, asset_id: str) -> str:
    resp = client.get(
        f"/api/v1/design-projects/{project_id}/assets?include_derived=true",
        headers=auth_headers(client),
    )
    assert resp.status_code == 200, resp.text
    for asset in resp.json():
        if asset["id"] == asset_id:
            return asset["status"]
    raise AssertionError(f"asset not found: {asset_id}")


# ============================================================
# 项目 CRUD / 鉴权
# ============================================================


def test_project_crud(client):
    project = _create_project(client)
    pid = project["id"]
    headers = auth_headers(client)

    get_resp = client.get(
        f"/api/v1/design-projects/{pid}", headers=headers
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["title"] == "测试项目"

    list_resp = client.get(
        f"/api/v1/design-projects?shop_id={project['shop_id']}",
        headers=headers,
    )
    assert list_resp.status_code == 200
    assert any(p["id"] == pid for p in list_resp.json())

    patch_resp = client.patch(
        f"/api/v1/design-projects/{pid}",
        json={"title": "改名项目", "status": "active"},
        headers=headers,
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["status"] == "active"

    del_resp = client.delete(
        f"/api/v1/design-projects/{pid}", headers=headers
    )
    assert del_resp.status_code == 200
    assert client.get(
        f"/api/v1/design-projects/{pid}", headers=headers
    ).status_code == 404


def test_anonymous_401(client):
    resp = client.get(f"/api/v1/design-projects/{uuid.uuid4()}")
    assert resp.status_code == 401


def test_cross_user_404(client):
    resp = client.get(
        f"/api/v1/design-projects/{uuid.uuid4()}",
        headers=auth_headers(client),
    )
    assert resp.status_code == 404


# ============================================================
# 素材上传 / 更新
# ============================================================


def test_upload_and_patch_asset(client):
    project = _create_project(client)
    asset = _upload_dish(client, project["id"])
    assert asset["status"] == "active"
    assert asset["source"] == "upload"
    assert asset["dish_name"] == "红烧肉"
    assert asset["original_url"] is not None

    patch_resp = client.patch(
        f"/api/v1/design-projects/{project['id']}/assets/{asset['id']}",
        json={"dish_name": "秘制红烧肉", "price": "42.00", "tagline": "招牌必点"},
        headers=auth_headers(client),
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["dish_name"] == "秘制红烧肉"


def test_upload_invalid_mime(client):
    project = _create_project(client)
    resp = client.post(
        f"/api/v1/design-projects/{project['id']}/assets",
        data={"asset_type": "photo"},
        files={"file": ("bad.txt", io.BytesIO(b"not image"), "text/plain")},
        headers=auth_headers(client),
    )
    assert resp.status_code == 400


# ============================================================
# AI 候选生命周期
# ============================================================


def test_generate_candidates_and_confirm(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.designs.generate_edited", _stub_generate_edited
    )
    project = _create_project(client)
    headers = auth_headers(client)
    resp = client.post(
        f"/api/v1/design-projects/{project['id']}/assets/generate",
        data={"prompt": "深夜食堂暖光氛围", "asset_type": "dish"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(data["candidates"]) == 4
    batch_id = data["batch_id"]
    candidates = data["candidates"]
    assert all(c["batch_id"] == batch_id for c in candidates)

    active_aid = candidates[0]["aid"]
    confirm = client.post(
        f"/api/v1/design-projects/{project['id']}/assets/{active_aid}/confirm",
        headers=headers,
    )
    assert confirm.status_code == 200, confirm.text
    assert confirm.json()["active_aid"] == active_aid
    assert len(confirm.json()["discarded_aids"]) == 3

    # 重复 confirm -> 409（幂等）
    again = client.post(
        f"/api/v1/design-projects/{project['id']}/assets/{active_aid}/confirm",
        headers=headers,
    )
    assert again.status_code == 409

    assert _asset_status(client, project["id"], active_aid) == "active"
    for discarded in confirm.json()["discarded_aids"]:
        assert _asset_status(client, project["id"], discarded) == "discarded"


def test_confirm_batch_isolation(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.designs.generate_edited", _stub_generate_edited
    )
    async def _no_rate_limit(*args, **kwargs):
        return True

    monkeypatch.setattr("app.api.v1.designs.check_rate_limit", _no_rate_limit)
    project = _create_project(client)
    headers = auth_headers(client)
    base = f"/api/v1/design-projects/{project['id']}/assets"

    batch1 = client.post(
        base + "/generate", data={"prompt": "第一批"}, headers=headers
    ).json()
    batch2 = client.post(
        base + "/generate", data={"prompt": "第二批"}, headers=headers
    ).json()

    confirm = client.post(
        f"{base}/{batch1['candidates'][0]['aid']}/confirm", headers=headers
    )
    assert confirm.status_code == 200

    for candidate in batch2["candidates"]:
        assert _asset_status(client, project["id"], candidate["aid"]) == "pending"
    for candidate in batch1["candidates"][1:]:
        assert _asset_status(client, project["id"], candidate["aid"]) == "discarded"


def test_rate_limit_generate_429(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.designs.generate_edited", _stub_generate_edited
    )
    project = _create_project(client)
    headers = auth_headers(client)
    base = f"/api/v1/design-projects/{project['id']}/assets/generate"

    first = client.post(base, data={"prompt": "测试生成"}, headers=headers)
    assert first.status_code == 200, first.text
    second = client.post(base, data={"prompt": "测试生成"}, headers=headers)
    assert second.status_code == 429


def test_sensitive_prompt_422(client):
    project = _create_project(client)
    resp = client.post(
        f"/api/v1/design-projects/{project['id']}/assets/generate",
        data={"prompt": "赌博平台推广图"},
        headers=auth_headers(client),
    )
    assert resp.status_code == 422


# ============================================================
# 一键美化
# ============================================================


def test_auto_beautify_warm_tone_preserved():
    from app.services.design_beautify import auto_beautify

    fixture = (
        Path(__file__).parent / "fixtures" / "warm_restaurant.jpg"
    )
    data = fixture.read_bytes()
    out = auto_beautify(data)

    with Image.open(io.BytesIO(out)) as img:
        assert img.format == "JPEG"
        assert img.size == (1200, 1599)
        r, g, b = ImageStat.Stat(img).mean[:3]

    # 暖调保留：R > G > B，且没有被白平衡洗掉
    assert r > g > b
    assert r - b > 30


def test_beautify_api(client):
    project = _create_project(client)
    fixture = Path(__file__).parent / "fixtures" / "warm_restaurant.jpg"
    resp = client.post(
        f"/api/v1/design-projects/{project['id']}/assets",
        data={"asset_type": "photo"},
        files={"file": ("warm.jpg", io.BytesIO(fixture.read_bytes()), "image/jpeg")},
        headers=auth_headers(client),
    )
    assert resp.status_code == 200, resp.text
    aid = resp.json()["id"]

    beautify = client.post(
        f"/api/v1/design-projects/{project['id']}/assets/{aid}/beautify",
        json={"mode": "enhance"},
        headers=auth_headers(client),
    )
    assert beautify.status_code == 200, beautify.text
    assert beautify.json()["processed_url"] is not None
    assert beautify.json()["beauty_config"]["mode"] == "enhance"


# ============================================================
# 派生候选：bg-replace -> confirm -> save 折叠
# ============================================================


def test_derived_fold_and_list_exclusion(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.designs.generate_edited", _stub_generate_edited
    )
    project = _create_project(client)
    original = _upload_dish(client, project["id"])
    headers = auth_headers(client)
    base = f"/api/v1/design-projects/{project['id']}/assets/{original['id']}"

    # GET /assets 默认排除派生候选
    assets = client.get(
        f"/api/v1/design-projects/{project['id']}/assets", headers=headers
    ).json()
    assert len(assets) == 1
    assert assets[0]["id"] == original["id"]

    bg = client.post(
        base + "/bg-replace",
        json={"prompt": "换成深夜暖光木质餐桌氛围"},
        headers=headers,
    )
    assert bg.status_code == 200, bg.text
    candidates = bg.json()["candidates"]
    assert len(candidates) == 4

    # 候选仍不进入素材库列表
    assets = client.get(
        f"/api/v1/design-projects/{project['id']}/assets", headers=headers
    ).json()
    assert len(assets) == 1

    confirm = client.post(
        f"/api/v1/design-projects/{project['id']}/assets/{candidates[0]['aid']}/confirm",
        headers=headers,
    )
    assert confirm.status_code == 200
    assert _asset_status(client, project["id"], candidates[0]["aid"]) == "active"

    # 保存成品到原 aid -> 派生候选折叠为 discarded
    save = client.post(
        base + "/save",
        json={"image_base64": base64.b64encode(_make_png()).decode()},
        headers=headers,
    )
    assert save.status_code == 200, save.text
    assert save.json()["processed_url"] is not None
    assert _asset_status(client, project["id"], candidates[0]["aid"]) == "discarded"


def test_ai_beautify_candidates_and_fold(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.designs.generate_edited", _stub_generate_edited
    )
    project = _create_project(client)
    original = _upload_dish(client, project["id"])
    headers = auth_headers(client)
    base = f"/api/v1/design-projects/{project['id']}/assets/{original['id']}"

    resp = client.post(base + "/ai-beautify", json={}, headers=headers)
    assert resp.status_code == 200, resp.text
    candidates = resp.json()["candidates"]
    assert len(candidates) == 4

    derived = [
        a
        for a in client.get(
            f"/api/v1/design-projects/{project['id']}/assets?include_derived=true",
            headers=headers,
        ).json()
        if a["derived_from_asset_id"] == original["id"]
    ]
    assert len(derived) == 4
    assert all(a["status"] == "pending" for a in derived)

    confirm = client.post(
        f"/api/v1/design-projects/{project['id']}/assets/{candidates[0]['aid']}/confirm",
        headers=headers,
    )
    assert confirm.status_code == 200
    assert _asset_status(client, project["id"], candidates[0]["aid"]) == "active"

    save = client.post(
        base + "/save",
        json={"image_base64": base64.b64encode(_make_png()).decode()},
        headers=headers,
    )
    assert save.status_code == 200, save.text
    assert _asset_status(client, project["id"], candidates[0]["aid"]) == "discarded"


def test_ai_beautify_sensitive_prompt_422(client):
    project = _create_project(client)
    asset = _upload_dish(client, project["id"])
    resp = client.post(
        f"/api/v1/design-projects/{project['id']}/assets/{asset['id']}/ai-beautify",
        json={"prompt": "赌博平台宣传图"},
        headers=auth_headers(client),
    )
    assert resp.status_code == 422


def test_ai_beautify_rate_limit_429(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.designs.generate_edited", _stub_generate_edited
    )
    project = _create_project(client)
    asset = _upload_dish(client, project["id"])
    headers = auth_headers(client)
    url = f"/api/v1/design-projects/{project['id']}/assets/{asset['id']}/ai-beautify"

    first = client.post(url, json={}, headers=headers)
    assert first.status_code == 200, first.text
    second = client.post(url, json={}, headers=headers)
    assert second.status_code == 429


def test_ai_beautify_prompt_generation(client, monkeypatch):
    captured: dict = {}

    async def fake_generate(kind, focus=None, dish_name=None):
        captured["kind"] = kind
        captured["focus"] = focus
        captured["dish_name"] = dish_name
        return f"AI 美化提示词：{focus or '默认'}，保留主体与构图"

    monkeypatch.setattr(
        "app.api.v1.designs.generate_edit_prompt", fake_generate
    )
    project = _create_project(client)
    asset = _upload_dish(client, project["id"], dish_name="红烧肉")
    resp = client.post(
        f"/api/v1/design-projects/{project['id']}/assets/{asset['id']}/ai-beautify/prompt",
        json={"kind": "bg", "focus": "深夜暖光"},
        headers=auth_headers(client),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["prompt"].startswith("AI 美化提示词：深夜暖光")
    assert captured["focus"] == "深夜暖光"
    assert captured["kind"] == "bg"
    assert captured["dish_name"] == "红烧肉"


def test_ai_beautify_prompt_sensitive_422(client):
    project = _create_project(client)
    asset = _upload_dish(client, project["id"])
    resp = client.post(
        f"/api/v1/design-projects/{project['id']}/assets/{asset['id']}/ai-beautify/prompt",
        json={"focus": "赌博平台"},
        headers=auth_headers(client),
    )
    assert resp.status_code == 422


def test_ai_beautify_prompt_rate_limit_429(client, monkeypatch):
    async def fake_generate(kind, focus=None, dish_name=None):
        return "测试提示词"

    monkeypatch.setattr(
        "app.api.v1.designs.generate_edit_prompt", fake_generate
    )
    project = _create_project(client)
    asset = _upload_dish(client, project["id"])
    headers = auth_headers(client)
    url = f"/api/v1/design-projects/{project['id']}/assets/{asset['id']}/ai-beautify/prompt"

    first = client.post(url, json={"focus": "提升食欲"}, headers=headers)
    assert first.status_code == 200, first.text
    second = client.post(url, json={"focus": "提升食欲"}, headers=headers)
    assert second.status_code == 429


# ============================================================
# 素材删除 / 菜单校验
# ============================================================


def test_delete_asset_referenced_409(client):
    project = _create_project(client)
    dish_a = _upload_dish(client, project["id"], dish_name="鱼香肉丝", price="28")
    dish_b = _upload_dish(client, project["id"], dish_name="麻婆豆腐", price="22")
    headers = auth_headers(client)

    menu = client.post(
        f"/api/v1/design-projects/{project['id']}/menus",
        json={
            "menu_type": "xhs",
            "template_id": "xhs_menu_01",
            "shop_name": "川味小馆",
            "items": [{"asset_id": dish_a["id"], "section": "招牌", "sort": 1}],
        },
        headers=headers,
    )
    assert menu.status_code == 200, menu.text

    del_a = client.delete(
        f"/api/v1/design-projects/{project['id']}/assets/{dish_a['id']}",
        headers=headers,
    )
    assert del_a.status_code == 409

    del_b = client.delete(
        f"/api/v1/design-projects/{project['id']}/assets/{dish_b['id']}",
        headers=headers,
    )
    assert del_b.status_code == 200


def test_menu_items_asset_validation(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.designs.generate_edited", _stub_generate_edited
    )
    project_a = _create_project(client)
    project_b = _create_project(client)
    asset_a = _upload_dish(client, project_a["id"])
    asset_b = _upload_dish(client, project_b["id"])
    headers = auth_headers(client)
    menu_url = f"/api/v1/design-projects/{project_a['id']}/menus"

    # 不属于当前项目 -> 400
    wrong_project = client.post(
        menu_url,
        json={"items": [{"asset_id": asset_b["id"]}]},
        headers=headers,
    )
    assert wrong_project.status_code == 400

    # 非 active（discarded）-> 400
    gen = client.post(
        f"/api/v1/design-projects/{project_a['id']}/assets/generate",
        data={"prompt": "生成一批"},
        headers=headers,
    ).json()
    first = gen["candidates"][0]["aid"]
    client.post(
        f"/api/v1/design-projects/{project_a['id']}/assets/{first}/confirm",
        headers=headers,
    )
    discarded = gen["candidates"][1]["aid"]
    discarded_item = client.post(
        menu_url,
        json={"items": [{"asset_id": discarded}]},
        headers=headers,
    )
    assert discarded_item.status_code == 400

    # 正常 active -> 200
    ok = client.post(
        menu_url,
        json={"items": [{"asset_id": asset_a["id"]}]},
        headers=headers,
    )
    assert ok.status_code == 200, ok.text


# ============================================================
# 菜单渲染
# ============================================================


def test_menu_render_version_mismatch(client):
    project = _create_project(client)
    asset = _upload_dish(client, project["id"])
    menu = client.post(
        f"/api/v1/design-projects/{project['id']}/menus",
        json={
            "items": [{"asset_id": asset["id"]}],
            "shop_name": "测试餐厅",
        },
        headers=auth_headers(client),
    ).json()

    render = client.post(
        f"/api/v1/design-projects/{project['id']}/menus/{menu['id']}/render",
        json={"version": 99},
        headers=auth_headers(client),
    )
    assert render.status_code == 409


def test_menu_render_override_priority(client):
    project = _create_project(client)
    asset = _upload_dish(client, project["id"], dish_name="原味鸡", price="30")
    menu = client.post(
        f"/api/v1/design-projects/{project['id']}/menus",
        json={
            "shop_name": "测试餐厅",
            "items": [{
                "asset_id": asset["id"],
                "section": "招牌",
                "sort": 1,
                "override_name": "香辣鸡",
                "override_price": "35",
                "override_tagline": "招牌现炸",
            }],
        },
        headers=auth_headers(client),
    ).json()

    render = client.post(
        f"/api/v1/design-projects/{project['id']}/menus/{menu['id']}/render",
        json={"version": 0},
        headers=auth_headers(client),
    )
    assert render.status_code == 200, render.text
    assert render.json()["output_url"] is not None
    assert render.json()["version"] == 1

    get_after = client.get(
        f"/api/v1/design-projects/{project['id']}/menus/{menu['id']}",
        headers=auth_headers(client),
    ).json()
    assert get_after["status"] == "rendered"
    assert get_after["version"] == 1


def test_resolve_item_override_priority():
    from app.services.menu_render import resolve_item

    class FakeAsset:
        dish_name = "原味鸡"
        price = 30
        tagline = "现炸"

    item = {
        "asset_id": "abc",
        "section": "招牌",
        "override_name": "香辣鸡",
        "override_price": "35",
        "override_tagline": None,
    }
    resolved = resolve_item(item, FakeAsset())
    assert resolved["name"] == "香辣鸡"
    assert resolved["price"] == "35"
    assert resolved["tagline"] == "现炸"


def test_render_templates_sizes_and_chinese_text():
    from app.services.menu_render import render_menu

    images = {
        "a": _make_png((400, 300), (200, 120, 60)),
        "b": _make_png((400, 300), (80, 160, 90)),
    }
    base_items = [
        {"asset_id": "a", "section": "招牌", "name": "红烧肉", "price": "38", "tagline": "肥而不腻"},
        {"asset_id": "b", "section": "主食", "name": "米饭", "price": "3", "tagline": ""},
    ]

    xhs = render_menu(
        {
            "template_id": "xhs_menu_01",
            "shop_name": "深夜食堂",
            "color_scheme": {"primary": "#D4520A", "secondary": "#FFF6EC", "text": "#2D1A0A"},
            "items": base_items,
        },
        images,
    )
    with Image.open(io.BytesIO(xhs)) as img:
        assert img.size == (1242, 1660)
        xhs_pixels = list(img.get_flattened_data() if hasattr(img, "get_flattened_data") else img.getdata())
    assert len(set(xhs_pixels)) > 10  # 有文字/图形内容

    a4 = render_menu(
        {
            "template_id": "a4_menu_01",
            "shop_name": "深夜食堂",
            "color_scheme": {"primary": "#C93828", "secondary": "#FFFFFF", "text": "#2A0A08"},
            "items": base_items,
        },
        images,
    )
    with Image.open(io.BytesIO(a4)) as img:
        assert img.size == (2480, 3508)
        a4_pixels = list(img.get_flattened_data() if hasattr(img, "get_flattened_data") else img.getdata())
    assert len(set(a4_pixels)) > 10


def test_save_base64_size_limit():
    from app.schemas.design import SaveRequest

    big = base64.b64encode(b"\x00" * (10 * 1024 * 1024 + 1)).decode()
    with pytest.raises(ValidationError):
        SaveRequest(image_base64=big)


# ============================================================
# 菜单分页 / PDF 导出
# ============================================================


def test_render_menu_pages_chunks_and_pdf_unit():
    from app.services.menu_render import render_menu_pages, render_menu_pdf

    images = {
        f"a{i}": _make_png((300, 200), (180 + i * 10, 100, 60)) for i in range(7)
    }
    items = [
        {
            "asset_id": f"a{i}",
            "section": "招牌",
            "name": f"菜{i}",
            "price": str(10 + i),
            "tagline": "",
        }
        for i in range(7)
    ]
    config = {
        "template_id": "xhs_menu_01",
        "shop_name": "测试",
        "color_scheme": {},
        "items": items,
    }
    pages = render_menu_pages(config, images)
    assert len(pages) == 2
    pdf = render_menu_pdf(pages)
    assert pdf.startswith(b"%PDF")


def test_menu_render_pagination_api(client):
    project = _create_project(client)
    asset_ids = [
        _upload_dish(client, project["id"], dish_name=f"菜{i}", price=str(10 + i))["id"]
        for i in range(7)
    ]
    headers = auth_headers(client)
    menu = client.post(
        f"/api/v1/design-projects/{project['id']}/menus",
        json={
            "menu_type": "xhs",
            "template_id": "xhs_menu_01",
            "shop_name": "分页测试",
            "items": [
                {"asset_id": aid, "section": "招牌", "sort": i + 1}
                for i, aid in enumerate(asset_ids)
            ],
        },
        headers=headers,
    ).json()

    render = client.post(
        f"/api/v1/design-projects/{project['id']}/menus/{menu['id']}/render",
        json={"version": 0},
        headers=headers,
    )
    assert render.status_code == 200, render.text
    data = render.json()
    assert len(data["pages"]) == 2
    assert data["version"] == 1

    get_menu = client.get(
        f"/api/v1/design-projects/{project['id']}/menus/{menu['id']}",
        headers=headers,
    ).json()
    assert len(get_menu["output_pages"]) == 2


def test_menu_export_pdf(client):
    from urllib.request import urlopen

    project = _create_project(client)
    asset = _upload_dish(client, project["id"])
    menu = client.post(
        f"/api/v1/design-projects/{project['id']}/menus",
        json={"items": [{"asset_id": asset["id"]}]},
        headers=auth_headers(client),
    ).json()
    client.post(
        f"/api/v1/design-projects/{project['id']}/menus/{menu['id']}/render",
        json={"version": 0},
        headers=auth_headers(client),
    )
    resp = client.post(
        f"/api/v1/design-projects/{project['id']}/menus/{menu['id']}/export-pdf",
        json={"version": 1},
        headers=auth_headers(client),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["output_url"].startswith("http")
    with urlopen(resp.json()["output_url"], timeout=30) as f:
        head = f.read(4)
    assert head == b"%PDF"


def test_menu_export_pdf_version_mismatch(client):
    project = _create_project(client)
    asset = _upload_dish(client, project["id"])
    menu = client.post(
        f"/api/v1/design-projects/{project['id']}/menus",
        json={"items": [{"asset_id": asset["id"]}]},
        headers=auth_headers(client),
    ).json()
    client.post(
        f"/api/v1/design-projects/{project['id']}/menus/{menu['id']}/render",
        json={"version": 0},
        headers=auth_headers(client),
    )
    resp = client.post(
        f"/api/v1/design-projects/{project['id']}/menus/{menu['id']}/export-pdf",
        json={"version": 0},
        headers=auth_headers(client),
    )
    assert resp.status_code == 409


def test_menu_export_pdf_not_rendered(client):
    project = _create_project(client)
    asset = _upload_dish(client, project["id"])
    menu = client.post(
        f"/api/v1/design-projects/{project['id']}/menus",
        json={"items": [{"asset_id": asset["id"]}]},
        headers=auth_headers(client),
    ).json()
    resp = client.post(
        f"/api/v1/design-projects/{project['id']}/menus/{menu['id']}/export-pdf",
        json={"version": 0},
        headers=auth_headers(client),
    )
    assert resp.status_code == 400



def _wait_job(client, headers, url: str, timeout: float = 15.0) -> dict:
    import time

    deadline = time.time() + timeout
    data: dict = {}
    while time.time() < deadline:
        resp = client.get(url, headers=headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        if data["status"] in ("success", "failed"):
            return data
        time.sleep(0.2)
    return data
# ============================================================
# D6 工程补强：异步任务 / 缩略图 / GC / 菜单版本
# ============================================================


def test_generate_job_end_to_end(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.designs.generate_edited", _stub_generate_edited
    )
    project = _create_project(client)
    headers = auth_headers(client)
    resp = client.post(
        f"/api/v1/design-projects/{project['id']}/assets/generate/job",
        data={"prompt": "后台生成测试", "asset_type": "photo"},
        headers=headers,
    )
    assert resp.status_code == 202, resp.text
    job_id = resp.json()["job_id"]

    data = _wait_job(
        client,
        headers,
        f"/api/v1/design-projects/{project['id']}/jobs/{job_id}",
    )
    assert data["status"] == "success"
    assert len(data["result"]["candidates"]) == 4
    assert data["result"]["candidates"][0]["thumb_url"].startswith("http")


def test_ai_beautify_job_derived_candidates(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.designs.generate_edited", _stub_generate_edited
    )
    project = _create_project(client)
    original = _upload_dish(client, project["id"])
    headers = auth_headers(client)
    resp = client.post(
        f"/api/v1/design-projects/{project['id']}/assets/{original['id']}/ai-beautify/job",
        json={},
        headers=headers,
    )
    assert resp.status_code == 202, resp.text
    job_id = resp.json()["job_id"]
    job = _wait_job(
        client,
        headers,
        f"/api/v1/design-projects/{project['id']}/jobs/{job_id}",
    )
    assert job["status"] == "success"
    assert len(job["result"]["candidates"]) == 4

    derived = [
        a
        for a in client.get(
            f"/api/v1/design-projects/{project['id']}/assets?include_derived=true",
            headers=headers,
        ).json()
        if a["derived_from_asset_id"] == original["id"]
    ]
    assert len(derived) == 4
    assert all(a["status"] == "pending" for a in derived)


def test_upload_generates_thumb(client):
    project = _create_project(client)
    asset = _upload_dish(client, project["id"])
    assert asset["thumb_url"] is not None
    listed = client.get(
        f"/api/v1/design-projects/{project['id']}/assets",
        headers=auth_headers(client),
    ).json()
    assert listed[0]["thumb_url"].startswith("http")


def test_cleanup_discarded_assets(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.designs.generate_edited", _stub_generate_edited
    )
    project = _create_project(client)
    headers = auth_headers(client)
    gen = client.post(
        f"/api/v1/design-projects/{project['id']}/assets/generate",
        data={"prompt": "批量"},
        headers=headers,
    ).json()
    client.post(
        f"/api/v1/design-projects/{project['id']}/assets/{gen['candidates'][0]['aid']}/confirm",
        headers=headers,
    )
    cleanup = client.post(
        f"/api/v1/design-projects/{project['id']}/assets/cleanup-discarded",
        headers=headers,
    )
    assert cleanup.status_code == 200, cleanup.text
    assert cleanup.json()["deleted"] == 3
    remaining = client.get(
        f"/api/v1/design-projects/{project['id']}/assets?include_derived=true",
        headers=headers,
    ).json()
    assert len(remaining) == 1
    assert remaining[0]["status"] == "active"


def test_menu_versions_and_restore(client):
    project = _create_project(client)
    asset = _upload_dish(client, project["id"])
    headers = auth_headers(client)
    base = f"/api/v1/design-projects/{project['id']}/menus"
    menu = client.post(
        base,
        json={
            "items": [{"asset_id": asset["id"]}],
            "shop_name": "v0",
        },
        headers=headers,
    ).json()

    versions1 = client.get(f"{base}/{menu['id']}/versions", headers=headers).json()
    assert len(versions1) == 1
    assert versions1[0]["version"] == 0

    patched = client.patch(
        f"{base}/{menu['id']}",
        json={"version": 0, "shop_name": "v1"},
        headers=headers,
    ).json()
    assert patched["version"] == 1
    render = client.post(
        f"{base}/{menu['id']}/render",
        json={"version": 1},
        headers=headers,
    )
    assert render.status_code == 200
    versions2 = client.get(f"{base}/{menu['id']}/versions", headers=headers).json()
    assert len(versions2) == 3

    restored = client.post(
        f"{base}/{menu['id']}/restore",
        json={"version": 0},
        headers=headers,
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["shop_name"] == "v0"
    assert restored.json()["version"] == 3
    versions3 = client.get(f"{base}/{menu['id']}/versions", headers=headers).json()
    assert len(versions3) == 4
