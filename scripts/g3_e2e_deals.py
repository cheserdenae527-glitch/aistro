"""G3 团购工坊集成验证 — 真实 API + 真实 AI 端到端流水线。

用法：
    python scripts/g3_e2e_deals.py

流程（PLAN-DEALS G3 1-5）：
1. 真实门店建项目 + 录入真实菜单 → AI 生成 3 款套餐（验证毛利估算）
2. 三平台 copy 各生成一套，确认互不覆盖
3. regenerate 验证归档/新批次
4. 导出到视觉设计 → 出图（豆包）→ 确认保存
5. 修改菜品清单后确认已生成方案不受影响（快照）
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = os.environ.get("AISTRO_BASE_URL", "http://localhost:8000/api/v1")
EMAIL = os.environ.get("AISTRO_EMAIL", "admin@test.com")
PASSWORD = os.environ.get("AISTRO_PASSWORD", "admin123")

passed: list[str] = []
failed: list[str] = []


def req(method: str, path: str, token: str | None = None, body: dict | None = None, timeout: int = 180) -> tuple[int, dict]:
    r = urllib.request.Request(BASE + path, method=method)
    r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", f"Bearer {token}")
    data = json.dumps(body).encode() if body is not None else None
    try:
        with urllib.request.urlopen(r, data=data, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raw = e.read() or b"{}"
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"detail": raw.decode("utf-8", "ignore")}


def step(name: str, ok: bool, detail: str = "") -> None:
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {name}" + (f" — {detail}" if detail else ""))
    (passed if ok else failed).append(name)


def login() -> str:
    code, data = req("POST", "/auth/login", body={"email": EMAIL, "password": PASSWORD})
    if code != 200:
        code, data = req("POST", "/auth/register", body={"email": EMAIL, "password": PASSWORD, "name": "G3 Admin"})
        code, data = req("POST", "/auth/login", body={"email": EMAIL, "password": PASSWORD})
    return data["access_token"]


def main() -> int:
    token = login()
    print("== 已登录 ==")

    # 0) 找一个真实火锅门店（优先：已有 deal 项目所属门店）
    code, projects = req("GET", "/deal-projects?page=1&page_size=100", token)
    shop_id = None
    if code == 200 and projects.get("items"):
        shop_id = projects["items"][0]["shop_id"]
    if not shop_id:
        code, merchants = req("GET", "/merchants", token)
        items = merchants["items"] if isinstance(merchants, dict) and "items" in merchants else merchants
        mid = items[0]["id"]
        code, shops = req("GET", f"/merchants/{mid}/shops", token)
        sitems = shops["items"] if isinstance(shops, dict) and "items" in shops else shops
        hotpot = next((s for s in sitems if (s.get("category") or "").find("火锅") >= 0), None)
        shop_id = (hotpot or sitems[0])["id"]
    print(f"使用门店 shop_id={shop_id}")

    # 1) 建项目 + 真实菜单
    title = "解放碑火锅·暑期爆款双人套餐"
    code, proj = req("POST", "/deal-projects", token, {
        "shop_id": shop_id, "title": title, "platform": "douyin", "price_band": "人均80",
    })
    step("创建团购项目", code == 200, f"{code} {proj.get('id')}")
    if code != 200:
        return 1
    pid = proj["id"]

    menu = [
        {"name": "招牌鲜毛肚", "category": "signature", "cost_price": 22, "sale_price": 68, "is_signature": True, "is_high_margin": False},
        {"name": "雪花肥牛", "category": "staple", "cost_price": 28, "sale_price": 58, "is_signature": False, "is_high_margin": True},
        {"name": "现炸酥肉", "category": "snack", "cost_price": 10, "sale_price": 28, "is_signature": False, "is_high_margin": False},
        {"name": "手打柠檬茶", "category": "drink", "cost_price": 3, "sale_price": 15, "is_signature": False, "is_high_margin": False},
        {"name": "千层肚", "category": "staple", "cost_price": 18, "sale_price": 42, "is_signature": False, "is_high_margin": True},
    ]
    item_ids: dict[str, str] = {}
    ok = True
    for m in menu:
        code, it = req("POST", f"/deal-projects/{pid}/items", token, m)
        if code != 200:
            ok = False
            print("  录入失败:", code, it)
        item_ids[m["name"]] = it.get("id", "")
    step("录入真实菜单（5 道菜）", ok, f"items={len(item_ids)}")

    # 2) AI 生成套餐（真实 DeepSeek）
    print("== 调用真实 AI 生成套餐（可能需要 10-40s）==")
    code, gen = req("POST", f"/deal-projects/{pid}/schemes/generate", token, {}, timeout=240)
    if code != 200:
        step("AI 生成三款套餐", False, f"{code} {gen}")
        return 1
    schemes = gen.get("schemes", [])
    types = {s["scheme_type"] for s in schemes}
    step("生成 3 款（hook/profit/scenario）", len(schemes) == 3 and types == {"hook", "profit", "scenario"}, f"batch={gen.get('generation_batch')} types={sorted(types)}")

    margin_ok = all(
        s.get("margin_estimate") and "gross_margin" in s["margin_estimate"] and "net_margin" in s["margin_estimate"]
        for s in schemes
    )
    profit = next((s for s in schemes if s["scheme_type"] == "profit"), None)
    for s in schemes:
        m = s["margin_estimate"] or {}
        print(f"  [{s['scheme_type']}] {s['title']} 原价{s.get('original_price')} 团购价{s.get('deal_price')} "
              f"gross={m.get('gross_margin')} net={m.get('net_margin')} 佣金={m.get('platform_commission_rate')} note={m.get('note')!r}")
    step("毛利估算（gross/net/佣金）", margin_ok)
    if profit:
        has_sig = any(it.get("name", "").find("毛肚") >= 0 for it in (profit.get("items") or []))
        step("利润款含招牌菜", has_sig)

    # 3) 三平台 copy 互不覆盖
    # 注意：copy 频控按 scheme 20s（规格如此），三平台需间隔 21s，避免 429
    sid = profit["id"] if profit else schemes[0]["id"]
    plat_ok = True
    for i, p in enumerate(("douyin", "meituan", "xiaohongshu")):
        if i > 0:
            print("  （等待 21s 越过 copy 频控窗口）")
            time.sleep(21)
        code, c = req("POST", f"/deal-projects/{pid}/schemes/{sid}/copy", token, {"platform": p}, timeout=240)
        if code != 200:
            plat_ok = False
            print("  copy 失败:", p, code, c)
        else:
            print(f"  [{p}] {c.get('title')} cover={str(c.get('cover_prompt'))[:40]}...")
    code, copies = req("GET", f"/deal-projects/{pid}/schemes/{sid}/copies", token)
    plats = {c["platform"] for c in copies}
    step("三平台 copy 生成且互不覆盖", plat_ok and plats == {"douyin", "meituan", "xiaohongshu"}, f"copies={len(copies)}")

    # 4) regenerate：归档旧批次（等 generate 频控 20s 窗口）
    print("  （等待 21s 越过 generate 频控窗口）")
    time.sleep(21)
    code, gen2 = req("POST", f"/deal-projects/{pid}/schemes/generate", token, {}, timeout=240)
    step("regenerate → 新批次", code == 200 and gen2.get("generation_batch") == 2, f"batch={gen2.get('generation_batch')}")
    code, active = req("GET", f"/deal-projects/{pid}/schemes", token)
    code, all_s = req("GET", f"/deal-projects/{pid}/schemes?include_archived=true", token)
    arch = [s for s in all_s if s["is_archived"]]
    step("旧批次归档 / 新批次活跃", code == 200 and len(active) == 3 and len(arch) == 3 and all(s["is_archived"] is False for s in active), f"active={len(active)} archived={len(arch)}")
    old_copies = req("GET", f"/deal-projects/{pid}/schemes/{sid}/copies", token)
    step("归档方案 copies 仍可查询", old_copies[0] == 200 and len(old_copies[1]) == 3, f"copies={len(old_copies[1]) if old_copies[0] == 200 else 'err'}")

    # 5) 快照：修改菜品不影响已生成方案
    gen2_schemes = gen2.get("schemes") or []
    profit2 = next((s for s in gen2_schemes if s["scheme_type"] == "profit"), None)
    snap_item = next((it for it in ((profit2 or {}).get("items") or []) if it["name"].find("毛肚") >= 0), None)
    snap_price = snap_item["sale_price"] if snap_item else None
    code, _ = req("PATCH", f"/deal-projects/{pid}/items/{item_ids.get('招牌鲜毛肚', '')}", token, {"sale_price": 98, "is_signature": False})
    code, schemes_after = req("GET", f"/deal-projects/{pid}/schemes?include_archived=true", token)
    s2 = next((s for s in schemes_after if profit2 and s["id"] == profit2["id"]), None)
    snap_after = next((it for it in ((s2 or {}).get("items") or []) if it["name"].find("毛肚") >= 0), None)
    step("修改菜品后方案快照不变", snap_price is not None and snap_after is not None and snap_after["sale_price"] == snap_price,
         f"snapshot={snap_price} 修改后={snap_after.get('sale_price') if snap_after else None}")

    # 6) 导出到视觉设计 + 生图 + 确认保存
    code, exp = req("POST", f"/deal-projects/{pid}/schemes/{sid}/export-to-design", token, {"platform": "douyin"})
    step("导出到视觉设计", code == 200, f"{code} {exp.get('design_project_id')}")
    dp_id = exp.get("design_project_id")
    if dp_id:
        code, assets = req("GET", f"/design-projects/{dp_id}/assets", token)
        exported = next((a for a in assets if a.get("source") == "deals"), None)
        step("design_asset source=deals + cover_prompt", bool(exported and (exported.get("beauty_config") or {}).get("cover_prompt")),
             f"asset={exported.get('id') if exported else None}")
        cover = (exported.get("beauty_config") or {}).get("cover_prompt", "")
        # 生图（豆包）→ 确认保存
        fd = urllib.parse.urlencode({"prompt": cover}).encode()
        r = urllib.request.Request(BASE + f"/design-projects/{dp_id}/assets/generate", method="POST", data=fd)
        r.add_header("Authorization", f"Bearer {token}")
        r.add_header("Content-Type", "application/x-www-form-urlencoded")
        try:
            with urllib.request.urlopen(r, timeout=240) as resp:
                cand = json.loads(resp.read())
            batch = cand.get("candidates", [])
            step("视觉设计出图（豆包 4 候选）", len(batch) == 4, f"candidates={len(batch)}")
            if batch:
                code, conf = req("POST", f"/design-projects/{dp_id}/assets/{batch[0]['aid']}/confirm", token, {})
                step("确认保存封面", code == 200, f"{code} {conf.get('status') if isinstance(conf, dict) else ''}")
        except urllib.error.HTTPError as e:
            step("视觉设计出图（豆包 4 候选）", False, f"{e.code} {e.read()[:200]}")

    # 清理演示项目（保留导出物）
    req("DELETE", f"/deal-projects/{pid}", token)
    print(f"\n== G3 集成验证完成：PASS {len(passed)} / FAIL {len(failed)} ==")
    for f_ in failed:
        print("  FAIL:", f_)
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())


