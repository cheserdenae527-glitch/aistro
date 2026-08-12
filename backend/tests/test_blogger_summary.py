"""博主分析 AI 总结服务测试（Task C2a）— build_prompt / generate_summary + 端点。

运行方式：
    cd D:\two\backend
    pytest tests/test_blogger_summary.py -v

端点用例需要 Postgres 运行中（docker compose up -d）；通过 API 登录 + 直接写库
构造任务，AI 调用全部 mock，不真实调用 DeepSeek。
"""
from __future__ import annotations

import asyncio
import json
import os
import uuid

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models.analysis_task import BloggerAnalysisTask
from app.services.blogger_summary import build_prompt, generate_summary


# ---------------------------------------------------------------- fixtures/helpers


def _sample_result() -> dict:
    """模拟 score_blogger 的高分结果结构。"""
    return {
        "nickname": "美食探店小王",
        "note_count": 40,
        "real_note_count": 32,
        "sampled": True,
        "coverage": {
            "total_notes": 40,
            "sample_size": 32,
            "fetched_notes": 32,
            "coverage_rate": 0.8,
        },
        "confidence": "high",
        "dimensions": {
            "seeding_depth": {"score": 82.5, "confidence": "high", "detail": {}},
            "verticality": {"score": 90.0, "confidence": "high", "detail": {}},
            "stable_output": {"score": 75.0, "confidence": "high", "detail": {}},
            "sustained_operation": {"score": 68.0, "confidence": "high", "detail": {}},
            "growth_trend": {
                "score": 72.0,
                "confidence": "high",
                "detail": {"growth_rate": 0.12, "has_snapshot": True},
            },
        },
        "overall": {"score": 78.0, "level": "优秀", "description": "推荐入选", "score_suppressed": False},
        "stage": {"label": "成长", "confidence": "high", "evidence": ["月化涨粉 12.0%", "周均发布 2.0"]},
        "decision": {
            "recommendation": "priority",
            "summary": "美食垂直度高、种草能力强，适合优先建联",
            "reasons": ["美食内容占比 80%", "篇均收藏率 3.20%", "月化涨粉 12.0%", "账号阶段：成长"],
            "red_flags": [],
            "low_quality": False,
        },
        "anomalies": [],
        "insights": ["综合评分 78，等级：优秀；阶段：成长"],
    }


def _no_score_result() -> dict:
    """数据不足/被闸门拦截：overall 为空。"""
    result = _sample_result()
    result["overall"] = None
    result["overall_score_suppressed"] = True
    result["decision"] = {
        "recommendation": "insufficient_data",
        "summary": "真实样本覆盖率不足，暂不评分",
        "reasons": ["已验证样本 5/40，覆盖率 12%"],
        "red_flags": [],
        "low_quality": False,
    }
    return result


def _fake_client(content: str) -> tuple[object, dict]:
    """构造带 chat.completions.create 的假 AsyncOpenAI 客户端。"""
    captured: dict = {}

    class FakeCompletions:
        async def create(self, **kwargs):
            captured.update(kwargs)
            return {"choices": [{"message": {"content": content}}]}

    class FakeChat:
        pass

    class FakeClient:
        pass

    chat = FakeChat()
    chat.completions = FakeCompletions()
    client = FakeClient()
    client.chat = chat
    return client, captured


def _install_fake_client(monkeypatch, content: str) -> dict:
    client, captured = _fake_client(content)
    monkeypatch.setattr("app.services.blogger_summary._get_client", lambda: client)
    return captured


# ---------------------------------------------------------------- build_prompt


def test_build_prompt_contains_key_info():
    prompt = build_prompt(_sample_result())
    # 五维分数与置信度
    for label in ("种草深度", "内容垂直度", "稳定产出", "持续经营", "增长趋势"):
        assert label in prompt
    assert "82.5" in prompt  # 五维分数
    assert "置信度" in prompt
    # 总分/等级/描述
    assert "78.0" in prompt
    assert "优秀" in prompt
    assert "推荐入选" in prompt
    # 账号阶段（标签+置信度+evidence）
    assert "账号阶段" in prompt
    assert "成长" in prompt
    assert "evidence" in prompt or "月化涨粉 12.0%" in prompt
    # 合作建议
    assert "priority" in prompt
    assert "合作建议" in prompt
    # 覆盖率/可信度
    assert "覆盖率" in prompt
    assert "可信度" in prompt
    # insights
    assert "分析洞察" in prompt
    assert "综合评分 78" in prompt
    # 涨粉率
    assert "12.0%" in prompt
    # 异常
    assert "异常" in prompt


def test_build_prompt_no_score_notes_insufficient():
    prompt = build_prompt(_no_score_result())
    assert "该账号无有效评分" in prompt
    assert "谨慎判断" in prompt
    assert "insufficient_data" in prompt


def test_build_prompt_empty_result_no_crash():
    prompt = build_prompt({})
    assert isinstance(prompt, str)
    assert prompt


# ---------------------------------------------------------------- generate_summary


def test_generate_summary_parses_json(monkeypatch):
    payload = {
        "summary": "该博主种草能力强、垂直度高，建议合作。",
        "strengths": ["内容垂直度高", "种草能力在线"],
        "weaknesses": ["更新频率偏低"],
        "cooperate": True,
        "cooperate_reason": "粉丝量级匹配且无红旗，建议合作",
    }
    captured = _install_fake_client(monkeypatch, json.dumps(payload, ensure_ascii=False))
    result = asyncio.run(generate_summary(_sample_result()))
    assert result == {
        "summary": payload["summary"],
        "strengths": payload["strengths"],
        "weaknesses": payload["weaknesses"],
        "cooperate": True,
        "cooperate_reason": payload["cooperate_reason"],
    }
    assert captured["temperature"] == 0.3
    assert captured["max_tokens"] == 600
    assert captured["model"] == settings.DEEPSEEK_MODEL
    # system + user 两段消息
    messages = captured["messages"]
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert "种草深度" in messages[1]["content"]


def test_generate_summary_parses_fenced_json(monkeypatch):
    payload = {
        "summary": "带围栏也能解析",
        "strengths": ["优点"],
        "weaknesses": ["不足"],
        "cooperate": False,
        "cooperate_reason": "不建议",
    }
    content = "```json\n" + json.dumps(payload, ensure_ascii=False) + "\n```"
    _install_fake_client(monkeypatch, content)
    result = asyncio.run(generate_summary(_sample_result()))
    assert result["summary"] == "带围栏也能解析"
    assert result["cooperate"] is False


def test_generate_summary_cooperate_string_compat(monkeypatch):
    cases = [("建议", True), ("不建议", False), ("谨慎", False)]
    for raw, expected in cases:
        payload = {
            "summary": "s",
            "strengths": [],
            "weaknesses": [],
            "cooperate": raw,
            "cooperate_reason": "reason",
        }
        _install_fake_client(monkeypatch, json.dumps(payload, ensure_ascii=False))
        result = asyncio.run(generate_summary(_sample_result()))
        assert result["cooperate"] is expected, raw


def test_generate_summary_defaults_missing_fields(monkeypatch):
    _install_fake_client(monkeypatch, json.dumps({"summary": "仅总结"}, ensure_ascii=False))
    result = asyncio.run(generate_summary(_sample_result()))
    assert result == {
        "summary": "仅总结",
        "strengths": [],
        "weaknesses": [],
        "cooperate": False,
        "cooperate_reason": "",
    }


def test_generate_summary_invalid_json_raises(monkeypatch):
    _install_fake_client(monkeypatch, "这不是 JSON")
    with pytest.raises(ValueError):
        asyncio.run(generate_summary(_sample_result()))


# ---------------------------------------------------------------- endpoint


def _auth(client, email: str | None = None) -> tuple[dict, str]:
    """登录（必要时注册）并返回 (headers, user_id)。"""
    email = email or "admin@test.com"
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": "admin123"})
    if resp.status_code != 200:
        resp = client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "admin123", "name": "Test User"},
        )
        assert resp.status_code == 201, resp.text
    body = resp.json()
    return {"Authorization": f"Bearer {body['access_token']}"}, str(body["user"]["id"])


def _seed_task(user_id: str, xhs_user_id: str, *, result: dict | list | None = None) -> str:
    """直接写库创建分析任务（绕过网络爬虫），返回任务 id。"""

    async def _run() -> str:
        engine = create_async_engine(os.environ["DATABASE_URL"])
        try:
            Session = async_sessionmaker(engine, expire_on_commit=False)
            async with Session() as session:
                task = BloggerAnalysisTask(
                    user_id=uuid.UUID(user_id),
                    xhs_user_id=xhs_user_id,
                    status="success",
                    prescreen_passed=True,
                    follower_count=12000,
                    total_notes=30,
                    target_notes=30,
                    fetched_notes=30,
                    with_comments=False,
                    coverage=1.0,
                    confidence="high",
                    result=result,
                    error=None,
                )
                session.add(task)
                await session.commit()
                await session.refresh(task)
                return str(task.id)
        finally:
            await engine.dispose()

    return asyncio.run(_run())


def test_summary_requires_auth(client):
    resp = client.post(f"/api/v1/notes/analysis-tasks/{uuid.uuid4()}/summary")
    assert resp.status_code == 401


def test_summary_returns_200_structure(client, monkeypatch):
    headers, user_id = _auth(client, email=f"sum-ok-{uuid.uuid4().hex[:8]}@test.com")
    result = _sample_result()
    task_id = _seed_task(user_id, "xhs-sum-ok", result=result)

    async def fake_generate(result_arg: dict) -> dict:
        assert result_arg == result
        return {
            "summary": "种草能力强、垂直度高，建议合作。",
            "strengths": ["内容垂直度高"],
            "weaknesses": ["更新频率偏低"],
            "cooperate": True,
            "cooperate_reason": "建议合作",
        }

    monkeypatch.setattr("app.services.blogger_summary.generate_summary", fake_generate)
    resp = client.post(f"/api/v1/notes/analysis-tasks/{task_id}/summary", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"summary", "strengths", "weaknesses", "cooperate", "cooperate_reason"}
    assert body["summary"] == "种草能力强、垂直度高，建议合作。"
    assert body["strengths"] == ["内容垂直度高"]
    assert body["weaknesses"] == ["更新频率偏低"]
    assert body["cooperate"] is True
    assert body["cooperate_reason"] == "建议合作"


def test_summary_other_user_task_404(client, monkeypatch):
    headers, _ = _auth(client, email=f"sum-other-{uuid.uuid4().hex[:8]}@test.com")
    _, other_id = _auth(client, email=f"sum-other2-{uuid.uuid4().hex[:8]}@test.com")
    task_id = _seed_task(other_id, "xhs-other", result=_sample_result())

    async def fake_generate(result_arg: dict) -> dict:
        raise AssertionError("不应调用 AI")

    monkeypatch.setattr("app.services.blogger_summary.generate_summary", fake_generate)
    resp = client.post(f"/api/v1/notes/analysis-tasks/{task_id}/summary", headers=headers)
    assert resp.status_code == 404


def test_summary_not_found(client):
    headers, _ = _auth(client, email=f"sum-nf-{uuid.uuid4().hex[:8]}@test.com")
    resp = client.post(f"/api/v1/notes/analysis-tasks/{uuid.uuid4()}/summary", headers=headers)
    assert resp.status_code == 404


def test_summary_invalid_uuid_404(client):
    headers, _ = _auth(client, email=f"sum-bad-{uuid.uuid4().hex[:8]}@test.com")
    resp = client.post("/api/v1/notes/analysis-tasks/not-a-uuid/summary", headers=headers)
    assert resp.status_code == 404


def test_summary_generate_failure_502(client, monkeypatch):
    headers, user_id = _auth(client, email=f"sum-502-{uuid.uuid4().hex[:8]}@test.com")
    task_id = _seed_task(user_id, "xhs-sum-fail", result=_sample_result())

    async def boom(result_arg: dict) -> dict:
        raise RuntimeError("LLM 挂了")

    monkeypatch.setattr("app.services.blogger_summary.generate_summary", boom)
    resp = client.post(f"/api/v1/notes/analysis-tasks/{task_id}/summary", headers=headers)
    assert resp.status_code == 502
    assert "AI 总结生成失败：" in resp.json()["detail"]
    assert "LLM 挂了" in resp.json()["detail"]


def test_summary_non_dict_result_422(client, monkeypatch):
    headers, user_id = _auth(client, email=f"sum-422-{uuid.uuid4().hex[:8]}@test.com")
    task_id = _seed_task(user_id, "xhs-sum-list", result=[1, 2, 3])

    async def fake_generate(result_arg: dict) -> dict:
        raise AssertionError("不应调用 AI")

    monkeypatch.setattr("app.services.blogger_summary.generate_summary", fake_generate)
    resp = client.post(f"/api/v1/notes/analysis-tasks/{task_id}/summary", headers=headers)
    assert resp.status_code == 422
