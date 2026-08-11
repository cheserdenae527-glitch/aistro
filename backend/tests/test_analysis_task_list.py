"""分析任务只读列表端点测试（Task 11b）— 批量筛选视图的数据支撑。

运行方式：
    cd D:\two\backend
    pytest tests/test_analysis_task_list.py -v

需要 Postgres 运行中（docker compose up -d）。测试用例通过 API 登录 + 直接写库
构造任务数据，不触发网络爬虫。fixture 说明见 tests/conftest.py（client 为模块级
TestClient；auth_headers 按项目惯例以辅助函数实现，而非 conftest fixture）。
"""
from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone

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


def _seed_task(
    user_id: str,
    xhs_user_id: str,
    *,
    status: str = "success",
    result: dict | None = None,
    finished_at: datetime | None = None,
) -> str:
    """直接写库创建分析任务（绕过网络爬虫），返回任务 id。"""
    async def _run() -> str:
        engine = create_async_engine(os.environ["DATABASE_URL"])
        try:
            Session = async_sessionmaker(engine, expire_on_commit=False)
            async with Session() as session:
                task = BloggerAnalysisTask(
                    user_id=uuid.UUID(user_id),
                    xhs_user_id=xhs_user_id,
                    status=status,
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
                    finished_at=finished_at or datetime.now(timezone.utc),
                )
                session.add(task)
                await session.commit()
                await session.refresh(task)
                return str(task.id)
        finally:
            await engine.dispose()
    return asyncio.run(_run())


def test_list_analysis_tasks_requires_auth(client):
    resp = client.get("/api/v1/notes/analysis-tasks")
    assert resp.status_code == 401


def test_list_analysis_tasks_returns_items_and_nickname_fallback(client):
    headers, user_id = _auth(client)
    with_nick = _seed_task(
        user_id, "xhs-nick", result={"nickname": "美食博主", "overall": {"score": 88}}
    )
    no_nick = _seed_task(user_id, "xhs-plain", result={"overall": {"score": 70}})

    resp = client.get("/api/v1/notes/analysis-tasks", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert isinstance(body["items"], list)

    items = {it["id"]: it for it in body["items"]}
    assert items[with_nick]["nickname"] == "美食博主"
    assert items[with_nick]["xhs_user_id"] == "xhs-nick"
    assert items[no_nick]["nickname"] == ""  # result 无 nickname → 空字符串兜底
    assert items[no_nick]["status"] == "success"
    assert items[no_nick]["follower_count"] == 12000


def test_list_analysis_tasks_status_filter(client):
    headers, user_id = _auth(client)
    _seed_task(user_id, "xhs-ok", status="success")
    _seed_task(user_id, "xhs-fail", status="failed")

    resp = client.get("/api/v1/notes/analysis-tasks?status=success", headers=headers)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert items
    assert all(it["status"] == "success" for it in items)


def test_list_analysis_tasks_sorted_by_finished_at_desc(client):
    headers, user_id = _auth(client)
    old_id = _seed_task(user_id, "xhs-old", finished_at=datetime.now(timezone.utc) - timedelta(days=3))
    new_id = _seed_task(user_id, "xhs-new", finished_at=datetime.now(timezone.utc) - timedelta(days=1))

    resp = client.get("/api/v1/notes/analysis-tasks", headers=headers)
    assert resp.status_code == 200
    ids = [it["id"] for it in resp.json()["items"]]
    assert ids.index(new_id) < ids.index(old_id)


def test_list_analysis_tasks_limit_applied(client):
    headers, user_id = _auth(client)
    _seed_task(user_id, "xhs-limit-1")
    _seed_task(user_id, "xhs-limit-2")

    resp = client.get("/api/v1/notes/analysis-tasks?limit=1", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()["items"]) <= 1


def test_list_analysis_tasks_data_isolation(client):
    headers, user_id = _auth(client)
    other_email = f"other-{uuid.uuid4().hex[:8]}@test.com"
    _, other_id = _auth(client, email=other_email)
    _seed_task(other_id, "xhs-other", status="success")

    resp = client.get("/api/v1/notes/analysis-tasks", headers=headers)
    assert resp.status_code == 200
    assert all(it["xhs_user_id"] != "xhs-other" for it in resp.json()["items"])
