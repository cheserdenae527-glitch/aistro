"""订阅调度与更新标记测试（纯逻辑，不需要数据库/网络）。"""
from __future__ import annotations

from app.models.subscription import Subscription
from app.schemas.subscription import SubscriptionStatusItem


def _sub(note_count: int = 0, notified: int = 0) -> Subscription:
    return Subscription(
        xhs_user_id="u1",
        nickname="博主",
        note_count=note_count,
        notified_note_count=notified,
    )


def test_has_update_flag_rule():
    from app.api.v1.subscriptions import _has_update

    assert _has_update(_sub(note_count=10, notified=10)) is False
    assert _has_update(_sub(note_count=11, notified=10)) is True
    assert _has_update(_sub(note_count=5, notified=10)) is False


def test_status_item_shape():
    item = SubscriptionStatusItem(subscribed=True, subscription_id=None, has_update=True)
    assert item.subscribed is True
    assert item.has_update is True


def test_scheduler_config_defaults():
    from crawler.config import DEFAULT_CONFIG, load_config

    assert "subscription_refresh_interval_hours" in DEFAULT_CONFIG
    assert "subscription_refresh_batch_size" in DEFAULT_CONFIG
    cfg = load_config()
    assert cfg.get("subscription_refresh_interval_hours", 12) == 12
    assert cfg.get("subscription_refresh_batch_size", 20) == 20


def test_scheduler_module_importable():
    from app.services.subscription_scheduler import SubscriptionScheduler

    assert SubscriptionScheduler is not None
