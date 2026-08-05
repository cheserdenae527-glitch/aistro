"""L3 端到端验证脚本 — 临时后端(:8011) + mock 引擎(:8010)。

流程：注册登录 → 建门店/项目(engine_config.base_url=mock) →
  1) engine-test 默认推送（占位人设 + 内置词库）→ 检查健康检查/推送/last_health_check/脱敏
  2) 配置弹幕 persona+敏感词 → engine-test 再推 → mock 回读确认热加载
  3) engine-test 带 base_url 覆盖（未保存）→ 不污染项目配置
  4) 导出开播包 JSON Schema 校验（用真实 export 若有定稿脚本，否则用代表性样例）
清理：删除测试项目。
"""
import io, json, os, sys, uuid

import httpx
import jsonschema

BASE = "http://localhost:8011/api/v1"
ENGINE = "http://localhost:8010"
SCHEMA_PATH = r"D:\two\docs\contracts\livestream-bundle.schema.json"

email = f"l3engine-{uuid.uuid4().hex[:8]}@test.com"
password = "admin123"
client = httpx.Client(base_url=BASE, timeout=30.0)

def post(path, **kw):
    r = client.post(path, **kw)
    print(f"POST {path} -> {r.status_code}")
    if r.status_code >= 400:
        print("  body:", r.text[:500])
    return r

def get(path, **kw):
    r = client.get(path, **kw)
    print(f"GET {path} -> {r.status_code}")
    return r

def patch(path, **kw):
    r = client.patch(path, **kw)
    print(f"PATCH {path} -> {r.status_code}")
    return r

ok = True

# 1) 注册/登录
r = post("/auth/register", json={"email": email, "password": password, "name": "L3 Engine Tester"})
if r.status_code not in (200, 201, 409):
    ok = False
r = post("/auth/login", json={"email": email, "password": password})
assert r.status_code == 200, r.text
headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

# 2) 门店
m = post("/merchants", json={"name": "L3测试商家"}, headers=headers)
assert 200 <= m.status_code < 300, m.text
s = post(f"/merchants/{m.json()['id']}/shops", json={"name": "L3测试门店", "category": "火锅"}, headers=headers)
assert 200 <= s.status_code < 300, s.text
shop_id = s.json()["id"]

# 3) 项目（带引擎配置）
p = post("/live-projects", json={
    "shop_id": shop_id,
    "title": "L3本地引擎验证直播",
    "platform": "douyin",
    "engine_config": {"base_url": ENGINE, "api_key": "sk-e2e", "enabled": True},
}, headers=headers)
assert 200 <= p.status_code < 300, p.text
project_id = p.json()["id"]
print("project:", project_id)

try:
    # 4) engine-test 默认推送
    t1 = post(f"/live-projects/{project_id}/engine-test", headers=headers)
    assert t1.status_code == 200, t1.text
    d1 = t1.json()
    print("engine-test#1:", json.dumps(d1, ensure_ascii=False, indent=2))
    assert d1["ok"] is True
    assert d1["health"]["ok"] is True
    assert d1["persona_push"]["status"] == "ok"
    assert d1["wordlist_push"]["status"] == "ok"
    assert d1["last_health_check"]

    # GET 项目：last_health_check 落库 + api_key 脱敏
    g = get(f"/live-projects/{project_id}", headers=headers).json()
    assert g["engine_config"]["last_health_check"], "last_health_check 未落库"
    assert g["engine_config"]["api_key_configured"] is True
    assert "api_key" not in g["engine_config"], "api_key 脱敏失败"
    print("GET 项目 engine_config:", json.dumps(g["engine_config"], ensure_ascii=False))

    # 5) 配置弹幕 persona + 敏感词 → engine-test 再推 → mock 回读
    danmaku = {
        "persona": {"name": "L3弹幕主播", "personality": "亲切", "style": "烟火气",
                     "knowledge_scope": "本店菜品", "forbidden_topics": ["政治"]},
        "sensitive_words": ["加微信", "regex:广告\\d+"],
    }
    put = client.put(f"/live-projects/{project_id}/danmaku-config", json=danmaku, headers=headers)
    assert 200 <= put.status_code < 300, put.text
    t2 = post(f"/live-projects/{project_id}/engine-test", headers=headers)
    assert t2.status_code == 200, t2.text
    print("engine-test#2 ok:", t2.json()["ok"])

    # mock 引擎回读（验证热加载生效）
    hp = httpx.get(f"{ENGINE}/admin/persona").json()
    hw = httpx.get(f"{ENGINE}/admin/wordlist").json()
    print("mock persona:", json.dumps(hp, ensure_ascii=False))
    print("mock wordlist:", json.dumps(hw, ensure_ascii=False))
    assert hp["data"]["name"] == "L3弹幕主播", "persona 未热加载"
    assert hw["data"]["content"].split("\n") == ["加微信", "regex:广告\\d+"], "wordlist 未热加载"

    # 6) base_url 覆盖（未保存）→ 不污染项目配置
    t3 = post(f"/live-projects/{project_id}/engine-test",
              json={"base_url": "http://localhost:9", "push_persona": False, "push_wordlist": False},
              headers=headers)
    assert t3.status_code == 502, t3.text  # 连不上的地址 → 502
    print("engine-test 覆盖地址 502 ok:", t3.json()["detail"])
    g2 = get(f"/live-projects/{project_id}", headers=headers).json()
    assert g2["engine_config"]["base_url"] == ENGINE, "覆盖地址污染了项目配置"

    # 7) 开播包 JSON Schema 校验（代表性样例，字段与真实 export 一致）
    with io.open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema = json.load(f)
    sample = {
        "script_markdown": "# 火锅直播间\n\n## 开场留人（60s）\n欢迎来到直播间\n\n总时长：300s\n",
        "persona_json": {"name": "L3弹幕主播", "personality": "亲切", "style": "烟火气",
                          "knowledge_scope": "本店菜品", "forbidden_topics": ["政治"]},
        "wordlist": ["加微信", "regex:广告\\d+"],
        "reply_rules": [{"trigger": "优惠", "reply": "今日套餐 9.9 元起", "mode": "manual"}],
        "compliance": {"pass": True, "items": [{"key": "ai_label", "ok": True, "detail": "AI 标识文案非空"}]},
        "engine_guide": "1. 启动 LiveTalking\n5. LiveTalking 水印提醒\n6. AI 标识文案提醒",
    }
    jsonschema.validate(sample, schema)
    print("开播包 JSON Schema 校验通过")

    print("\n=== E2E 全部通过 ===")
except AssertionError as e:
    ok = False
    print("!!! E2E 失败:", e)
except Exception as e:
    ok = False
    import traceback
    traceback.print_exc()
finally:
    # 清理：删除项目（级联清 scripts/danmaku/sessions）
    dr = client.delete(f"/live-projects/{project_id}", headers=headers)
    print("cleanup delete project:", dr.status_code)

sys.exit(0 if ok else 1)
