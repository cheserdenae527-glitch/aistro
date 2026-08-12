"""批量创建博主分析任务端点测试（Task B1）— 真实粗筛 + 上限 50 + 评审修订。

运行方式：
    cd D:\two\backend
    pytest tests/test_analysis_task_batch.py -v

需要 Postgres 运行中（docker compose up -d）。prescreen_user / start_analysis_task
通过 monkeypatch 控制（不触发网络爬虫），用例通过 API 登录 + 直接读库验证落库行数。
"""
from __future__ import annotations

import asyncio
import os
import uuid
from unittest import mock

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.analysis_task import BloggerAnalysisTask


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


def _fetch_tasks(user_id: str) -> list[BloggerAnalysisTask]:
    """直接读库返回该用户的分析任务行。"""

    async def _run() -> list[BloggerAnalysisTask]:
        engine = create_async_engine(os.environ["DATABASE_URL"])
        try:
            Session = async_sessionmaker(engine, expire_on_commit=False)
            async with Session() as session:
                result = await session.execute(
                    select(BloggerAnalysisTask).where(
                        BloggerAnalysisTask.user_id == uuid.UUID(user_id)
                    )
                )
                return list(result.scalars().all())
        finally:
            await engine.dispose()

    return asyncio.run(_run())


def test_batch_requires_auth(client):
    resp = client.post("/api/v1/notes/analysis-tasks/batch", json={"bloggers": [{"user_id": "xhs-1"}]})
    assert resp.status_code == 401


def test_batch_all_passed_creates_tasks_and_starts_runner(client, monkeypatch):
    headers, user_id = _auth(client, email=f"batch-ok-{uuid.uuid4().hex[:8]}@test.com")
    called: list[str] = []

    async def fake_prescreen(user_id: str) -> dict:
        called.append(user_id)
        fans = {"xhs-1": 8000, "xhs-2": 12000, "xhs-fallback": 0}.get(user_id, 0)
        return {"passed": True, "reason": None, "fans": fans, "notes": 20, "avg_likes": 120.0}

    start_mock = mock.Mock()
    monkeypatch.setattr("app.services.analysis_task_runner.prescreen_user", fake_prescreen)
    monkeypatch.setattr("app.services.analysis_task_runner.start_analysis_task", start_mock)

    bloggers = [
        {"user_id": "xhs-1", "nickname": "博主一", "fans": 5000, "with_comments": True},
        {"user_id": "xhs-2", "nickname": "", "fans": 0, "with_comments": False},
        # prescreen 未返回粉丝数时回退到请求里的 fans
        {"user_id": "xhs-fallback", "nickname": "兜底号", "fans": 1234},
    ]
    resp = client.post("/api/v1/notes/analysis-tasks/batch", headers=headers, json={"bloggers": bloggers})
    assert resp.status_code == 200
    body = resp.json()
    assert body["rejected"] == []
    assert len(body["created"]) == 3
    for item, b in zip(body["created"], bloggers):
        assert item["xhs_user_id"] == b["user_id"]
        assert item["nickname"] == b["nickname"]
        assert item["status"] == "pending"
        assert item["task_id"]

    created_by_id = {it["xhs_user_id"]: it for it in body["created"]}
    assert created_by_id["xhs-1"]["follower_count"] == 8000  # prescreen 粉丝数优先
    assert created_by_id["xhs-1"]["notes"] == 20  # 粗筛 notes 透传
    assert created_by_id["xhs-fallback"]["follower_count"] == 1234  # prescreen fans=0 → 回退 b.fans

    tasks = _fetch_tasks(user_id)
    assert len(tasks) == 3
    by_id = {t.xhs_user_id: t for t in tasks}
    assert all(t.prescreen_passed for t in tasks)
    assert by_id["xhs-1"].follower_count == 8000
    assert by_id["xhs-1"].total_notes == 20  # total_notes 从粗筛结果写入任务行
    assert by_id["xhs-1"].with_comments is True
    assert by_id["xhs-2"].with_comments is False
    assert by_id["xhs-fallback"].follower_count == 1234

    assert called == ["xhs-1", "xhs-2", "xhs-fallback"]  # 串行逐个粗筛
    assert start_mock.call_count == 3  # 每个创建的任务都调度后台运行


def test_batch_mixed_passed_and_rejected(client, monkeypatch):
    headers, user_id = _auth(client, email=f"batch-mix-{uuid.uuid4().hex[:8]}@test.com")

    async def fake_prescreen(user_id: str) -> dict:
        if user_id == "xhs-bad":
            return {"passed": False, "reason": "粉丝数不足（100 < 1000）", "fans": 100, "notes": 3, "avg_likes": 10.0}
        return {"passed": True, "reason": None, "fans": 9000, "notes": 30, "avg_likes": 200.0}

    start_mock = mock.Mock()
    monkeypatch.setattr("app.services.analysis_task_runner.prescreen_user", fake_prescreen)
    monkeypatch.setattr("app.services.analysis_task_runner.start_analysis_task", start_mock)

    bloggers = [
        {"user_id": "xhs-good-1", "nickname": "好号一"},
        {"user_id": "xhs-bad", "nickname": "差号"},
        {"user_id": "xhs-good-2", "nickname": ""},
    ]
    resp = client.post("/api/v1/notes/analysis-tasks/batch", headers=headers, json={"bloggers": bloggers})
    assert resp.status_code == 200
    body = resp.json()
    assert [it["xhs_user_id"] for it in body["created"]] == ["xhs-good-1", "xhs-good-2"]
    assert all(it["status"] == "pending" for it in body["created"])
    assert body["rejected"] == [
        {"xhs_user_id": "xhs-bad", "nickname": "差号", "reason": "粉丝数不足（100 < 1000）"}
    ]
    # 拒绝者不落任何任务行
    tasks = _fetch_tasks(user_id)
    assert len(tasks) == 2
    assert {t.xhs_user_id for t in tasks} == {"xhs-good-1", "xhs-good-2"}
    assert start_mock.call_count == 2


def test_batch_prescreen_exception_rejected_others_still_processed(client, monkeypatch):
    headers, user_id = _auth(client, email=f"batch-exc-{uuid.uuid4().hex[:8]}@test.com")

    async def fake_prescreen(user_id: str) -> dict:
        if user_id == "xhs-crash":
            raise RuntimeError("boom")
        return {"passed": True, "reason": None, "fans": 7000, "notes": 25, "avg_likes": 150.0}

    start_mock = mock.Mock()
    monkeypatch.setattr("app.services.analysis_task_runner.prescreen_user", fake_prescreen)
    monkeypatch.setattr("app.services.analysis_task_runner.start_analysis_task", start_mock)

    bloggers = [
        {"user_id": "xhs-ok", "nickname": "好号"},
        {"user_id": "xhs-crash", "nickname": "异常号"},
        {"user_id": "xhs-ok2", "nickname": "好号二"},
    ]
    resp = client.post("/api/v1/notes/analysis-tasks/batch", headers=headers, json={"bloggers": bloggers})
    assert resp.status_code == 200
    body = resp.json()
    assert [it["xhs_user_id"] for it in body["created"]] == ["xhs-ok", "xhs-ok2"]
    assert body["rejected"] == [{"xhs_user_id": "xhs-crash", "nickname": "异常号", "reason": "粗筛异常"}]
    # 异常博主不落任务行，其余博主仍正常创建
    tasks = _fetch_tasks(user_id)
    assert len(tasks) == 2
    assert "xhs-crash" not in {t.xhs_user_id for t in tasks}
    assert start_mock.call_count == 2


def test_batch_duplicate_user_ids_deduped(client, monkeypatch):
    headers, user_id = _auth(client, email=f"batch-dup-{uuid.uuid4().hex[:8]}@test.com")
    called: list[str] = []

    async def fake_prescreen(user_id: str) -> dict:
        called.append(user_id)
        return {"passed": True, "reason": None, "fans": 5000, "notes": 18, "avg_likes": 90.0}

    start_mock = mock.Mock()
    monkeypatch.setattr("app.services.analysis_task_runner.prescreen_user", fake_prescreen)
    monkeypatch.setattr("app.services.analysis_task_runner.start_analysis_task", start_mock)

    bloggers = [
        {"user_id": "xhs-dup", "nickname": "重复号", "fans": 100},
        {"user_id": "xhs-ok", "nickname": "正常号"},
        {"user_id": "xhs-dup", "nickname": "重复号2", "fans": 999},  # 重复 → first-wins，只处理首个
    ]
    resp = client.post("/api/v1/notes/analysis-tasks/batch", headers=headers, json={"bloggers": bloggers})
    assert resp.status_code == 200
    body = resp.json()
    assert [it["xhs_user_id"] for it in body["created"]] == ["xhs-dup", "xhs-ok"]
    assert body["created"][0]["nickname"] == "重复号"  # first-wins 使用首个条目的昵称
    assert called == ["xhs-dup", "xhs-ok"]  # 重复 id 只粗筛一次
    assert len(_fetch_tasks(user_id)) == 2
    assert start_mock.call_count == 2


def test_batch_empty_bloggers_returns_422(client, monkeypatch):
    headers, _ = _auth(client, email=f"batch-empty-{uuid.uuid4().hex[:8]}@test.com")
    # 显式空列表 → pydantic min_length 校验
    resp = client.post("/api/v1/notes/analysis-tasks/batch", headers=headers, json={"bloggers": []})
    assert resp.status_code == 422
    # 缺省字段 → 处理器兜底拒绝空批，避免静默 no-op 200
    resp = client.post("/api/v1/notes/analysis-tasks/batch", headers=headers, json={})
    assert resp.status_code == 422


def test_batch_over_50_returns_422(client, monkeypatch):
    headers, _ = _auth(client, email=f"batch-422-{uuid.uuid4().hex[:8]}@test.com")
    bloggers = [{"user_id": f"xhs-{i}", "nickname": ""} for i in range(51)]
    resp = client.post("/api/v1/notes/analysis-tasks/batch", headers=headers, json={"bloggers": bloggers})
    assert resp.status_code == 422
    assert resp.json()["detail"] == "批量分析单次最多 50 个博主"
