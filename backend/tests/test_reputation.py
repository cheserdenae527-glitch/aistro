"""R1 口碑管理后端测试。

运行方式：
    cd D:\\two\\backend
    pytest tests/test_reputation.py -v

需要 Postgres + Redis 运行中。
"""
from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import asyncpg
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.models.review import Review
from crawler.base import CrawlResult


# ============================================================
# 基础 helper
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


def _register_user(client, email: str) -> dict:
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "admin123", "name": "Other User"},
    )
    assert resp.status_code == 201, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _create_shop(client, headers: dict | None = None) -> str:
    headers = headers or auth_headers(client)
    merchant = client.post(
        "/api/v1/merchants",
        json={"name": f"商家-{uuid.uuid4().hex[:8]}"},
        headers=headers,
    )
    assert merchant.status_code in (200, 201), merchant.text
    shop = client.post(
        f"/api/v1/merchants/{merchant.json()['id']}/shops",
        json={"name": f"门店-{uuid.uuid4().hex[:8]}", "category": "火锅"},
        headers=headers,
    )
    assert shop.status_code in (200, 201), shop.text
    return shop.json()["id"]


def _create_platform(client, shop_id: str, headers: dict | None = None) -> str:
    headers = headers or auth_headers(client)
    resp = client.post(
        f"/api/v1/shops/{shop_id}/platforms",
        json={
            "platform": "xiaohongshu",
            "platform_shop_id": f"xhs-{uuid.uuid4().hex[:12]}",
            "shop_name": "小红书",
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _insert_review(platform_shop_id: str, **fields) -> uuid.UUID:
    async def run() -> uuid.UUID:
        engine = create_async_engine(os.environ["DATABASE_URL"])
        try:
            async with AsyncSession(engine) as session:
                review = Review(platform_shop_id=platform_shop_id, **fields)
                session.add(review)
                await session.commit()
                await session.refresh(review)
                return review.id
        finally:
            await engine.dispose()

    return asyncio.run(run())


def _get_review(client, shop_id: str, rid: str, headers: dict) -> dict:
    resp = client.get(
        f"/api/v1/shops/{shop_id}/reviews?size=100", headers=headers
    )
    assert resp.status_code == 200, resp.text
    for item in resp.json()["items"]:
        if item["id"] == rid:
            return item
    raise AssertionError(f"review not found: {rid}")


def _note(note_id: str, title: str, desc: str) -> dict:
    return {
        "id": note_id,
        "xsec_token": "token123",
        "note_card": {
            "display_title": title,
            "desc": desc,
            "type": "normal",
            "user": {"user_id": f"user-{note_id}", "nickname": "探店博主", "avatar": ""},
            "interact_info": {
                "liked_count": 5,
                "collected_count": 2,
                "comment_count": 3,
                "shared_count": 1,
            },
            "corner_tag_info": [],
            "cover": {},
            "image_list": [],
        },
    }


def _comment(comment_id: str, content: str, nickname: str = "评论用户") -> dict:
    return {
        "id": comment_id,
        "user_info": {"user_id": f"user-{comment_id}", "nickname": nickname, "avatar": ""},
        "content": content,
        "like_count": 2,
        "create_time": "2026-08-01T10:00:00+08:00",
        "sub_comments": [],
    }


class FakeCrawler:
    def __init__(
        self,
        notes: list | None = None,
        comments: list | None = None,
        search_error: str | None = None,
        comments_error: str | None = None,
    ):
        self.notes = notes or []
        self.comments = comments or []
        self.search_error = search_error
        self.comments_error = comments_error

    def search_notes(self, query, limit=20, sort_type=0, note_type=0, time_range=0):
        if self.search_error:
            return CrawlResult(success=False, error=self.search_error)
        return CrawlResult(success=True, data=self.notes)

    def get_comments(self, note_url):
        if self.comments_error:
            return CrawlResult(success=False, error=self.comments_error)
        return CrawlResult(success=True, data=self.comments)


async def _no_rate_limit(*args, **kwargs):
    return True


def _stub_analyze(reviews, sentiment="negative", tags=None):
    return [
        SimpleNamespace(id=r.id, sentiment=sentiment, tags=tags or [])
        for r in reviews
    ]


async def _stub_reply(self, content, shop_name, category=None, positioning=None):
    return "谢谢反馈，我们下次会继续努力，欢迎再来！"


# ============================================================
# XHS 同步
# ============================================================


def test_sync_notes_dedup_and_keyword_alert(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.reviews.check_rate_limit", _no_rate_limit
    )
    monkeypatch.setattr(
        "app.services.review_sync.build_xhs_crawler",
        lambda: FakeCrawler(notes=[
            _note("n1", "探店", "这家店分量少，卫生差"),
            _note("n2", "好吃", "菜品很好，环境不错"),
        ]),
    )
    shop_id = _create_shop(client)
    headers = auth_headers(client)
    url = f"/api/v1/shops/{shop_id}/reviews/sync/xiaohongshu"

    first = client.post(url, json={"keyword": "火锅", "limit": 10}, headers=headers)
    assert first.status_code == 200, first.text
    assert first.json() == {"created": 2, "skipped": 0}

    second = client.post(url, json={"keyword": "火锅", "limit": 10}, headers=headers)
    assert second.status_code == 200, second.text
    assert second.json() == {"created": 0, "skipped": 2}

    listing = client.get(
        f"/api/v1/shops/{shop_id}/reviews?review_type=note", headers=headers
    ).json()
    assert listing["total"] == 2

    alerts = client.get(
        f"/api/v1/shops/{shop_id}/reviews/alerts", headers=headers
    ).json()
    assert len(alerts) == 1
    assert alerts[0]["alert_reason"]["type"] == "keyword"
    assert set(alerts[0]["alert_reason"]["keywords"]) >= {"分量少", "卫生差"}


def test_sync_comments_dedup_and_keyword_alert(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.reviews.check_rate_limit", _no_rate_limit
    )
    monkeypatch.setattr(
        "app.services.review_sync.build_xhs_crawler",
        lambda: FakeCrawler(
            notes=[_note("n1", "探店", "普通探店")],
            comments=[
                _comment("c1", "服务员态度差，等位太久"),
                _comment("c2", "味道不错，下次再来"),
            ],
        ),
    )
    shop_id = _create_shop(client)
    headers = auth_headers(client)
    notes_url = f"/api/v1/shops/{shop_id}/reviews/sync/xiaohongshu"
    client.post(notes_url, json={"keyword": "火锅"}, headers=headers)
    note = client.get(
        f"/api/v1/shops/{shop_id}/reviews?review_type=note", headers=headers
    ).json()["items"][0]

    comments_url = f"/api/v1/shops/{shop_id}/reviews/{note['id']}/sync-comments"
    first = client.post(comments_url, headers=headers)
    assert first.status_code == 200, first.text
    assert first.json() == {"created": 2, "skipped": 0}

    second = client.post(comments_url, headers=headers)
    assert second.status_code == 200, second.text
    assert second.json() == {"created": 0, "skipped": 2}

    listing = client.get(
        f"/api/v1/shops/{shop_id}/reviews?review_type=comment", headers=headers
    ).json()
    assert listing["total"] == 2

    alerts = client.get(
        f"/api/v1/shops/{shop_id}/reviews/alerts", headers=headers
    ).json()
    assert len(alerts) == 1
    assert alerts[0]["platform_review_id"] == "c1"
    assert set(alerts[0]["alert_reason"]["keywords"]) >= {"态度差", "服务员态度", "等位太久"}


def test_get_reviews_parent_filter(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.reviews.check_rate_limit", _no_rate_limit
    )
    monkeypatch.setattr(
        "app.services.review_sync.build_xhs_crawler",
        lambda: FakeCrawler(
            notes=[_note("n1", "探店", "普通探店")],
            comments=[
                _comment("c1", "好吃"),
                _comment("c2", "服务一般"),
            ],
        ),
    )
    shop_id = _create_shop(client)
    headers = auth_headers(client)
    client.post(
        f"/api/v1/shops/{shop_id}/reviews/sync/xiaohongshu",
        json={"keyword": "火锅"},
        headers=headers,
    )
    note = client.get(
        f"/api/v1/shops/{shop_id}/reviews?review_type=note", headers=headers
    ).json()["items"][0]
    client.post(
        f"/api/v1/shops/{shop_id}/reviews/{note['id']}/sync-comments",
        headers=headers,
    )
    resp = client.get(
        f"/api/v1/shops/{shop_id}/reviews?parent_review_id={note['id']}",
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert all(item["parent_review_id"] == note["id"] for item in data["items"])


def test_sync_error_cookie_and_token_distinction(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.reviews.check_rate_limit", _no_rate_limit
    )
    monkeypatch.setattr(
        "app.services.review_sync.build_xhs_crawler",
        lambda: FakeCrawler(search_error="登录状态已失效"),
    )
    shop_id = _create_shop(client)
    headers = auth_headers(client)
    resp = client.post(
        f"/api/v1/shops/{shop_id}/reviews/sync/xiaohongshu",
        json={"keyword": "火锅"},
        headers=headers,
    )
    assert resp.status_code == 502
    assert "登录态失效" in resp.json()["detail"]

    monkeypatch.setattr(
        "app.services.review_sync.build_xhs_crawler",
        lambda: FakeCrawler(
            notes=[_note("n1", "探店", "普通")],
            comments_error="xsec_token 已过期",
        ),
    )
    shop2 = _create_shop(client)
    client.post(
        f"/api/v1/shops/{shop2}/reviews/sync/xiaohongshu",
        json={"keyword": "火锅"},
        headers=headers,
    )
    note = client.get(
        f"/api/v1/shops/{shop2}/reviews?review_type=note", headers=headers
    ).json()["items"][0]
    resp2 = client.post(
        f"/api/v1/shops/{shop2}/reviews/{note['id']}/sync-comments",
        headers=headers,
    )
    assert resp2.status_code == 502
    assert "笔记链接已过期" in resp2.json()["detail"]


def test_sync_comments_independent_rate_keys(client, monkeypatch):
    monkeypatch.setattr(
        "app.services.review_sync.build_xhs_crawler",
        lambda: FakeCrawler(
            notes=[_note("n1", "笔记1", "普通"), _note("n2", "笔记2", "普通")],
            comments=[_comment("c1", "还不错")],
        ),
    )
    shop_id = _create_shop(client)
    headers = auth_headers(client)
    notes_url = f"/api/v1/shops/{shop_id}/reviews/sync/xiaohongshu"

    first = client.post(notes_url, json={"keyword": "火锅"}, headers=headers)
    assert first.status_code == 200, first.text

    notes = client.get(
        f"/api/v1/shops/{shop_id}/reviews?review_type=note", headers=headers
    ).json()["items"]
    for note in notes:
        resp = client.post(
            f"/api/v1/shops/{shop_id}/reviews/{note['id']}/sync-comments",
            headers=headers,
        )
        assert resp.status_code == 200, resp.text


# ============================================================
# batch-analyze
# ============================================================


def test_batch_analyze_over_20_returns_400(client):
    shop_id = _create_shop(client)
    headers = auth_headers(client)
    ids = [str(uuid.uuid4()) for _ in range(21)]
    resp = client.post(
        f"/api/v1/shops/{shop_id}/reviews/batch-analyze",
        json={"review_ids": ids},
        headers=headers,
    )
    assert resp.status_code == 400


def test_batch_analyze_rate_limit_429(client, monkeypatch):
    async def fake_analyze(self, reviews):
        return _stub_analyze(reviews, sentiment="positive", tags=["好"])

    monkeypatch.setattr(
        "app.ai.review_agent.ReviewAgent.analyze_batch", fake_analyze
    )
    shop_id = _create_shop(client)
    platform_shop_id = _create_platform(client, shop_id)
    headers = auth_headers(client)
    rid = str(_insert_review(
        platform_shop_id,
        review_type="comment",
        platform_review_id="r1",
        content="很好吃",
        reply_status="unreplied",
    ))
    url = f"/api/v1/shops/{shop_id}/reviews/batch-analyze"
    first = client.post(url, json={"review_ids": [rid]}, headers=headers)
    assert first.status_code == 200, first.text
    second = client.post(url, json={"review_ids": [rid]}, headers=headers)
    assert second.status_code == 429


def test_batch_analyze_partial_failure(client, monkeypatch):
    async def fake_analyze(self, reviews):
        if len(reviews) == 10:
            return _stub_analyze(reviews, sentiment="positive", tags=["好"])
        raise RuntimeError("llm down")

    monkeypatch.setattr(
        "app.api.v1.reviews.check_rate_limit", _no_rate_limit
    )
    monkeypatch.setattr(
        "app.ai.review_agent.ReviewAgent.analyze_batch", fake_analyze
    )
    shop_id = _create_shop(client)
    platform_shop_id = _create_platform(client, shop_id)
    headers = auth_headers(client)
    ids = [
        str(_insert_review(
            platform_shop_id,
            review_type="comment",
            platform_review_id=f"r{i}",
            content=f"内容{i}",
            reply_status="unreplied",
        ))
        for i in range(11)
    ]
    resp = client.post(
        f"/api/v1/shops/{shop_id}/reviews/batch-analyze",
        json={"review_ids": ids},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total"] == 11
    assert data["success_count"] == 10
    assert data["failed_count"] == 1


def test_batch_analyze_negative_trigger_and_positive_not_reset(client, monkeypatch):
    async def fake_negative(self, reviews):
        return _stub_analyze(reviews, sentiment="negative", tags=["分量少"])

    async def fake_positive(self, reviews):
        return _stub_analyze(reviews, sentiment="positive", tags=["好"])

    monkeypatch.setattr(
        "app.api.v1.reviews.check_rate_limit", _no_rate_limit
    )
    monkeypatch.setattr(
        "app.ai.review_agent.ReviewAgent.analyze_batch", fake_negative
    )
    shop_id = _create_shop(client)
    platform_shop_id = _create_platform(client, shop_id)
    headers = auth_headers(client)
    rid = str(_insert_review(
        platform_shop_id,
        review_type="comment",
        platform_review_id="neg1",
        content="分量太少了",
        reply_status="unreplied",
    ))
    url = f"/api/v1/shops/{shop_id}/reviews/batch-analyze"
    first = client.post(url, json={"review_ids": [rid]}, headers=headers)
    assert first.status_code == 200, first.text

    row = _get_review(client, shop_id, rid, headers)
    assert row["sentiment"] == "negative"
    assert row["alert_status"] == "triggered"
    assert row["alert_reason"] == {
        "type": "sentiment",
        "keywords": [],
        "sentiment": "negative",
    }

    monkeypatch.setattr(
        "app.ai.review_agent.ReviewAgent.analyze_batch", fake_positive
    )
    second = client.post(url, json={"review_ids": [rid]}, headers=headers)
    assert second.status_code == 200, second.text
    row = _get_review(client, shop_id, rid, headers)
    assert row["sentiment"] == "positive"
    assert row["alert_status"] == "triggered"
    assert row["alert_reason"]["type"] == "sentiment"


def test_batch_analyze_keyword_to_both_merge(client, monkeypatch):
    async def fake_negative(self, reviews):
        return _stub_analyze(reviews, sentiment="negative", tags=["分量少"])

    monkeypatch.setattr(
        "app.api.v1.reviews.check_rate_limit", _no_rate_limit
    )
    monkeypatch.setattr(
        "app.ai.review_agent.ReviewAgent.analyze_batch", fake_negative
    )
    shop_id = _create_shop(client)
    platform_shop_id = _create_platform(client, shop_id)
    headers = auth_headers(client)
    rid = str(_insert_review(
        platform_shop_id,
        review_type="comment",
        platform_review_id="both1",
        content="分量少",
        reply_status="unreplied",
        alert_status="triggered",
        alert_reason={"type": "keyword", "keywords": ["分量少"], "sentiment": None},
    ))
    resp = client.post(
        f"/api/v1/shops/{shop_id}/reviews/batch-analyze",
        json={"review_ids": [rid]},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    row = _get_review(client, shop_id, rid, headers)
    assert row["alert_reason"] == {
        "type": "both",
        "keywords": ["分量少"],
        "sentiment": "negative",
    }
    assert row["alert_status"] == "triggered"


def test_batch_analyze_acknowledged_locked(client, monkeypatch):
    async def fake_negative(self, reviews):
        return _stub_analyze(reviews, sentiment="negative", tags=["分量少"])

    monkeypatch.setattr(
        "app.api.v1.reviews.check_rate_limit", _no_rate_limit
    )
    monkeypatch.setattr(
        "app.ai.review_agent.ReviewAgent.analyze_batch", fake_negative
    )
    shop_id = _create_shop(client)
    platform_shop_id = _create_platform(client, shop_id)
    headers = auth_headers(client)
    reason = {"type": "keyword", "keywords": ["分量少"], "sentiment": None}
    rid = str(_insert_review(
        platform_shop_id,
        review_type="comment",
        platform_review_id="locked1",
        content="分量少",
        reply_status="unreplied",
        alert_status="acknowledged",
        alert_reason=reason,
    ))
    resp = client.post(
        f"/api/v1/shops/{shop_id}/reviews/batch-analyze",
        json={"review_ids": [rid]},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    row = _get_review(client, shop_id, rid, headers)
    assert row["sentiment"] == "negative"
    assert row["alert_status"] == "acknowledged"
    assert row["alert_reason"] == reason


# ============================================================
# AI 回复草稿
# ============================================================


def test_ai_reply_note_400(client):
    shop_id = _create_shop(client)
    platform_shop_id = _create_platform(client, shop_id)
    headers = auth_headers(client)
    rid = str(_insert_review(
        platform_shop_id,
        review_type="note",
        platform_review_id="note1",
        content="探店笔记",
        reply_status=None,
    ))
    resp = client.post(
        f"/api/v1/shops/{shop_id}/reviews/{rid}/ai-reply",
        headers=headers,
    )
    assert resp.status_code == 400


def test_ai_reply_comment_success(client, monkeypatch):
    monkeypatch.setattr(
        "app.ai.review_agent.ReviewAgent.generate_reply", _stub_reply
    )
    shop_id = _create_shop(client)
    platform_shop_id = _create_platform(client, shop_id)
    headers = auth_headers(client)
    rid = str(_insert_review(
        platform_shop_id,
        review_type="comment",
        platform_review_id="c-good",
        content="很好吃，环境也好",
        reply_status="unreplied",
    ))
    resp = client.post(
        f"/api/v1/shops/{shop_id}/reviews/{rid}/ai-reply",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["ai_reply"] == "谢谢反馈，我们下次会继续努力，欢迎再来！"
    row = _get_review(client, shop_id, rid, headers)
    assert row["reply_status"] == "ai_replied"
    assert row["ai_reply"] == "谢谢反馈，我们下次会继续努力，欢迎再来！"


def test_ai_reply_input_sensitive_422_does_not_consume_window(client, monkeypatch):
    shop_id = _create_shop(client)
    platform_shop_id = _create_platform(client, shop_id)
    headers = auth_headers(client)
    bad_rid = str(_insert_review(
        platform_shop_id,
        review_type="comment",
        platform_review_id="c-bad",
        content="推荐赌博平台",
        reply_status="unreplied",
    ))
    resp = client.post(
        f"/api/v1/shops/{shop_id}/reviews/{bad_rid}/ai-reply",
        headers=headers,
    )
    assert resp.status_code == 422

    monkeypatch.setattr(
        "app.ai.review_agent.ReviewAgent.generate_reply", _stub_reply
    )
    good_rid = str(_insert_review(
        platform_shop_id,
        review_type="comment",
        platform_review_id="c-clean",
        content="很好",
        reply_status="unreplied",
    ))
    resp2 = client.post(
        f"/api/v1/shops/{shop_id}/reviews/{good_rid}/ai-reply",
        headers=headers,
    )
    assert resp2.status_code == 200, resp2.text


def test_ai_reply_generated_sensitive_422_does_not_consume_window(client, monkeypatch):
    async def bad_reply(self, content, shop_name, category=None, positioning=None):
        return "赌博平台推广文案"

    async def good_reply(self, content, shop_name, category=None, positioning=None):
        return "谢谢反馈，欢迎再来！"

    monkeypatch.setattr(
        "app.ai.review_agent.ReviewAgent.generate_reply", bad_reply
    )
    shop_id = _create_shop(client)
    platform_shop_id = _create_platform(client, shop_id)
    headers = auth_headers(client)
    rid = str(_insert_review(
        platform_shop_id,
        review_type="comment",
        platform_review_id="c-draft",
        content="很好吃",
        reply_status="unreplied",
    ))
    url = f"/api/v1/shops/{shop_id}/reviews/{rid}/ai-reply"
    first = client.post(url, headers=headers)
    assert first.status_code == 422

    monkeypatch.setattr(
        "app.ai.review_agent.ReviewAgent.generate_reply", good_reply
    )
    second = client.post(url, headers=headers)
    assert second.status_code == 200, second.text


def test_ai_reply_rate_limit_429(client, monkeypatch):
    monkeypatch.setattr(
        "app.ai.review_agent.ReviewAgent.generate_reply", _stub_reply
    )
    shop_id = _create_shop(client)
    platform_shop_id = _create_platform(client, shop_id)
    headers = auth_headers(client)
    rid = str(_insert_review(
        platform_shop_id,
        review_type="comment",
        platform_review_id="c-rate",
        content="很好吃",
        reply_status="unreplied",
    ))
    url = f"/api/v1/shops/{shop_id}/reviews/{rid}/ai-reply"
    first = client.post(url, headers=headers)
    assert first.status_code == 200, first.text
    second = client.post(url, headers=headers)
    assert second.status_code == 429


# ============================================================
# 确认回复 / 预警状态机
# ============================================================


def test_reply_note_400_and_triggered_auto_ack(client):
    shop_id = _create_shop(client)
    platform_shop_id = _create_platform(client, shop_id)
    headers = auth_headers(client)
    note_rid = str(_insert_review(
        platform_shop_id,
        review_type="note",
        platform_review_id="note-x",
        content="探店",
        reply_status=None,
    ))
    resp = client.put(
        f"/api/v1/shops/{shop_id}/reviews/{note_rid}/reply",
        json={"reply_content": "谢谢"},
        headers=headers,
    )
    assert resp.status_code == 400

    comment_rid = str(_insert_review(
        platform_shop_id,
        review_type="comment",
        platform_review_id="c-alert",
        content="服务差",
        reply_status="unreplied",
        alert_status="triggered",
        alert_reason={"type": "keyword", "keywords": ["服务差"], "sentiment": None},
    ))
    resp2 = client.put(
        f"/api/v1/shops/{shop_id}/reviews/{comment_rid}/reply",
        json={"reply_content": "非常抱歉，我们会改进服务"},
        headers=headers,
    )
    assert resp2.status_code == 200, resp2.text
    assert resp2.json()["reply_status"] == "manual_replied"
    assert resp2.json()["alert_status"] == "acknowledged"
    assert resp2.json()["reply_content"] == "非常抱歉，我们会改进服务"


def test_reply_manual_replied_overwrite_updates_replied_at(client):
    shop_id = _create_shop(client)
    platform_shop_id = _create_platform(client, shop_id)
    headers = auth_headers(client)
    old_time = datetime(2020, 1, 1, tzinfo=timezone.utc)
    rid = str(_insert_review(
        platform_shop_id,
        review_type="comment",
        platform_review_id="c-overwrite",
        content="不错",
        reply_status="manual_replied",
        reply_content="旧回复",
        replied_at=old_time,
    ))
    resp = client.put(
        f"/api/v1/shops/{shop_id}/reviews/{rid}/reply",
        json={"reply_content": "新回复"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    row = resp.json()
    assert row["reply_content"] == "新回复"
    assert row["reply_status"] == "manual_replied"
    assert row["replied_at"] is not None
    assert datetime.fromisoformat(row["replied_at"].replace("Z", "+00:00")) > old_time


def test_alert_ack_state_machine(client):
    shop_id = _create_shop(client)
    platform_shop_id = _create_platform(client, shop_id)
    headers = auth_headers(client)
    triggered = str(_insert_review(
        platform_shop_id,
        review_type="comment",
        platform_review_id="ack-1",
        content="难吃",
        reply_status="unreplied",
        alert_status="triggered",
        alert_reason={"type": "sentiment", "keywords": [], "sentiment": "negative"},
    ))
    none_rid = str(_insert_review(
        platform_shop_id,
        review_type="comment",
        platform_review_id="ack-2",
        content="好吃",
        reply_status="unreplied",
        alert_status="none",
    ))
    base = f"/api/v1/shops/{shop_id}/reviews/alerts"
    first = client.post(f"{base}/{triggered}/ack", headers=headers)
    assert first.status_code == 200
    assert first.json()["alert_status"] == "acknowledged"
    second = client.post(f"{base}/{triggered}/ack", headers=headers)
    assert second.status_code == 200
    assert second.json()["alert_status"] == "acknowledged"

    none_resp = client.post(f"{base}/{none_rid}/ack", headers=headers)
    assert none_resp.status_code == 400


def test_get_reviews_alert_status_filter(client):
    shop_id = _create_shop(client)
    platform_shop_id = _create_platform(client, shop_id)
    headers = auth_headers(client)
    _insert_review(
        platform_shop_id,
        review_type="comment",
        platform_review_id="f-1",
        content="a",
        reply_status="unreplied",
        alert_status="triggered",
        alert_reason={"type": "keyword", "keywords": ["难吃"], "sentiment": None},
    )
    _insert_review(
        platform_shop_id,
        review_type="comment",
        platform_review_id="f-2",
        content="b",
        reply_status="unreplied",
        alert_status="acknowledged",
    )
    _insert_review(
        platform_shop_id,
        review_type="comment",
        platform_review_id="f-3",
        content="c",
        reply_status="unreplied",
        alert_status="none",
    )
    resp = client.get(
        f"/api/v1/shops/{shop_id}/reviews?alert_status=triggered",
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["total"] == 1
    assert resp.json()["items"][0]["platform_review_id"] == "f-1"


def test_summary_unreplied_counts_comment_only(client):
    shop_id = _create_shop(client)
    platform_shop_id = _create_platform(client, shop_id)
    headers = auth_headers(client)
    _insert_review(
        platform_shop_id,
        review_type="note",
        platform_review_id="s-note",
        content="探店",
        reply_status=None,
    )
    _insert_review(
        platform_shop_id,
        review_type="comment",
        platform_review_id="s-c1",
        content="好吃",
        reply_status="unreplied",
    )
    _insert_review(
        platform_shop_id,
        review_type="comment",
        platform_review_id="s-c2",
        content="服务差",
        reply_status="unreplied",
        alert_status="triggered",
        alert_reason={"type": "keyword", "keywords": ["服务差"], "sentiment": None},
    )
    _insert_review(
        platform_shop_id,
        review_type="comment",
        platform_review_id="s-c3",
        content="不错",
        reply_status="manual_replied",
        reply_content="谢谢",
    )
    _insert_review(
        platform_shop_id,
        review_type="rating_review",
        platform_review_id="s-r",
        content="四星",
        rating=4,
        reply_status="unreplied",
    )
    resp = client.get(
        f"/api/v1/shops/{shop_id}/reviews/summary", headers=headers
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["note_count"] == 1
    assert data["comment_count"] == 3
    assert data["rating_review_count"] == 1
    assert data["unreplied_count"] == 2
    assert data["alert_count"] == 1
    assert data["sentiment_counts"]["unanalyzed"] == 5


# ============================================================
# 鉴权
# ============================================================


def test_reputation_auth_401_and_cross_user_404(client):
    resp = client.get(f"/api/v1/shops/{uuid.uuid4()}/reviews")
    assert resp.status_code == 401

    admin_headers = auth_headers(client)
    other_headers = _register_user(
        client, f"other-{uuid.uuid4().hex[:8]}@test.com"
    )
    other_shop = _create_shop(client, other_headers)
    cross = client.get(
        f"/api/v1/shops/{other_shop}/reviews", headers=admin_headers
    )
    assert cross.status_code == 404


# ============================================================
# 迁移：历史数据回填 + 去重 + 唯一索引
# ============================================================


def test_reputation_migration_backfills_and_deduplicates():
    from alembic import command
    from alembic.config import Config

    schema = f"migration_{uuid.uuid4().hex[:10]}"
    db_url = os.environ["DATABASE_URL"]
    plain_url = db_url.replace("postgresql+asyncpg://", "postgresql://")

    async def create_schema() -> None:
        conn = await asyncpg.connect(plain_url)
        try:
            await conn.execute(f'CREATE SCHEMA "{schema}"')
        finally:
            await conn.close()

    async def drop_schema() -> None:
        conn = await asyncpg.connect(plain_url)
        try:
            await conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        finally:
            await conn.close()

    def run_alembic(target: str) -> None:
        cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        cfg.set_main_option("sqlalchemy.url", db_url)
        cfg.set_main_option("sqlalchemy_search_path", schema)
        command.upgrade(cfg, target)

    async def seed_legacy() -> uuid.UUID:
        conn = await asyncpg.connect(plain_url)
        try:
            await conn.execute(f'SET search_path TO "{schema}"')
            user_id = await conn.fetchval(
                "INSERT INTO users (id, email, password_hash, name, role) "
                "VALUES (gen_random_uuid(), $1, $2, $3, 'admin') RETURNING id",
                f"mig-{uuid.uuid4().hex[:8]}@test.com",
                "hash",
                "Migration",
            )
            merchant_id = await conn.fetchval(
                "INSERT INTO merchants (id, user_id, name) "
                "VALUES (gen_random_uuid(), $1, $2) RETURNING id",
                user_id,
                "迁移商家",
            )
            shop_id = await conn.fetchval(
                "INSERT INTO shops (id, merchant_id, name) "
                "VALUES (gen_random_uuid(), $1, $2) RETURNING id",
                merchant_id,
                "迁移门店",
            )
            platform_shop_id = await conn.fetchval(
                "INSERT INTO platform_shops "
                "(id, shop_id, platform, platform_shop_id, shop_name) "
                "VALUES (gen_random_uuid(), $1, 'xiaohongshu', 'ps-1', '门店') RETURNING id",
                shop_id,
            )
            await conn.execute(
                "INSERT INTO reviews "
                "(id, platform_shop_id, platform_review_id, reviewer_name, rating, content, reply_status) "
                "VALUES (gen_random_uuid(), $1, 'r-1', 'A', 4, '正常评价', 'unreplied'), "
                "(gen_random_uuid(), $1, 'r-1', 'B', 2, '重复评价', 'unreplied')",
                platform_shop_id,
            )
            return platform_shop_id
        finally:
            await conn.close()

    async def verify_migration(platform_shop_id: uuid.UUID) -> None:
        conn = await asyncpg.connect(plain_url)
        try:
            await conn.execute(f'SET search_path TO "{schema}"')

            count = await conn.fetchval("SELECT count(*) FROM reviews")
            assert count == 1, "重复历史评价应被去重"
            row = await conn.fetchrow(
                "SELECT review_type, alert_status, reply_status FROM reviews"
            )
            assert row["review_type"] == "rating_review"
            assert row["alert_status"] == "none"
            assert row["reply_status"] == "unreplied"

            try:
                await conn.execute(
                    "INSERT INTO reviews "
                    "(id, platform_shop_id, platform_review_id, review_type, content, reply_status, alert_status) "
                    "VALUES (gen_random_uuid(), $1, 'r-1', 'rating_review', '重复', 'unreplied', 'none')",
                    platform_shop_id,
                )
                raise AssertionError("唯一索引应阻止重复记录")
            except asyncpg.UniqueViolationError:
                pass

            await conn.execute(
                "INSERT INTO reviews "
                "(id, platform_shop_id, platform_review_id, review_type, content, reply_status, alert_status) "
                "VALUES (gen_random_uuid(), $1, 'n-1', 'note', '新笔记', NULL, 'none')",
                platform_shop_id,
            )
            note_count = await conn.fetchval(
                "SELECT count(*) FROM reviews WHERE review_type = 'note'"
            )
            assert note_count == 1
        finally:
            await conn.close()

    asyncio.run(create_schema())
    try:
        run_alembic("e5f0d1a2b3c4")
        platform_shop_id = asyncio.run(seed_legacy())
        run_alembic("head")
        asyncio.run(verify_migration(platform_shop_id))
    finally:
        asyncio.run(drop_schema())
