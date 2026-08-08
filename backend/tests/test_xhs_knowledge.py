"""小红书设计知识库检索与接入测试。"""
from __future__ import annotations

import pytest

from app.services.xhs_knowledge import (
    build_knowledge_context,
    enrich_clone_schemes,
    reset_cache,
    retrieve,
)


@pytest.fixture(autouse=True)
def _fresh_cache():
    reset_cache()
    yield
    reset_cache()


def test_static_files_load_and_schema_valid():
    payload = retrieve()
    assert payload["styles"]
    assert payload["rules"]
    assert payload["styles"][0]["color_palettes"][0]["primary"].startswith("#")
    assert isinstance(payload["templates"], dict)
    assert set(payload["templates"].keys()) <= {s["id"] for s in payload["styles"]}


def test_retrieve_templates_keyed_by_style_id():
    payload = retrieve(category="火锅", limit=1)
    assert "shi_jing" in payload["templates"]
    assert payload["templates"]["shi_jing"]["avatar_template"]


def test_retrieve_by_category_returns_default_style():
    payload = retrieve(category="火锅", limit=1)
    assert payload["styles"][0]["id"] == "shi_jing"


def test_retrieve_by_style_alias():
    payload = retrieve(style_keywords=["温馨"], limit=3)
    ids = [s["id"] for s in payload["styles"]]
    assert "shi_jing" in ids


def test_retrieve_by_style_name():
    payload = retrieve(style_keywords=["高级冷淡"], limit=1)
    assert payload["styles"][0]["id"] == "gao_ji"


def test_retrieve_scoring_combines_category_and_keywords():
    payload = retrieve(category="火锅", style_keywords=["市井烟火"], limit=1)
    assert payload["styles"][0]["id"] == "shi_jing"


def test_retrieve_fallback_to_default_style():
    payload = retrieve(category="不存在品类", style_keywords=[], limit=1)
    assert payload["styles"][0]["id"] == "gao_ji"


def test_retrieve_palette_hint_boosts_style():
    payload = retrieve(category="咖啡", palette_hint="#E8C37A", limit=1)
    assert payload["styles"][0]["id"] == "ri_xi"


def test_build_context_contains_style_and_rules():
    ctx = build_knowledge_context(category="火锅", style_keywords=["市井烟火"])
    assert "市井烟火" in ctx
    assert "通用设计规则" in ctx
    assert "背景图比例 1125:420" in ctx


def test_build_context_section_filtering():
    avatar_ctx = build_knowledge_context(category="火锅", style_keywords=["市井烟火"], section="avatar")
    bg_ctx = build_knowledge_context(category="火锅", style_keywords=["市井烟火"], section="bg")
    assert "头像模板" in avatar_ctx and "背景模板" not in avatar_ctx
    assert "背景模板" in bg_ctx and "头像模板" not in bg_ctx


def test_enrich_clone_schemes_fills_missing_prompts():
    result = {
        "style_keywords": ["烟火气"],
        "schemes": [
            {
                "id": "A",
                "name": "暖辣市井方案",
                "color_scheme": {
                    "primary": "#C93828",
                    "secondary": "#FFF0EE",
                    "accent": "#A82015",
                    "text": "#2A0A08",
                },
                "avatar_prompt": "",
                "bg_prompt": "",
            }
        ],
    }
    out = enrich_clone_schemes(result)
    assert out["schemes"][0]["avatar_prompt"]
    assert out["schemes"][0]["bg_prompt"]
    assert out["knowledge_styles"] == ["市井烟火"]
    assert "{" not in out["schemes"][0]["avatar_prompt"]
    assert "{" not in out["schemes"][0]["bg_prompt"]


def test_generate_variants_injects_knowledge(monkeypatch):
    import asyncio

    from app.ai import profile_agent

    captured = {}

    class FakeCompletions:
        async def create(self, **kwargs):
            captured["kwargs"] = kwargs
            return type(
                "R",
                (),
                {
                    "choices": [
                        type("Ch", (), {"message": type("M", (), {"content": '{"variants":[]}'})()})()
                    ]
                },
            )()

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    monkeypatch.setattr(profile_agent, "_get_client", lambda: FakeClient())
    variants, _ = asyncio.run(
        profile_agent.generate_variants("火锅", "市井烟火", "人均80")
    )
    system = captured["kwargs"]["messages"][0]["content"]
    assert "参考设计知识库" in system
    assert "市井烟火" in system
    assert len(variants) == 4
def test_section_prompt_injects_avatar_template(monkeypatch):
    import asyncio

    from app.ai import profile_agent

    captured = {}

    class FakeCompletions:
        async def create(self, **kwargs):
            captured["kwargs"] = kwargs
            return type(
                "R",
                (),
                {
                    "choices": [
                        type("Ch", (), {"message": type("M", (), {"content": "头像提示词"})()})()
                    ]
                },
            )()

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    monkeypatch.setattr(profile_agent, "_get_client", lambda: FakeClient())
    prompt = asyncio.run(
        profile_agent.generate_section_prompt("avatar", "火锅", "市井烟火", "人均80")
    )
    system = captured["kwargs"]["messages"][0]["content"]
    assert "参考设计知识库" in system
    assert "头像模板" in system
    assert "背景模板" not in system
    assert prompt == "头像提示词"
