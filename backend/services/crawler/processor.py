"""
XHS 数据处理器 — 将爬虫原始数据转换为 AiRestro 结构化模型。"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any


def normalize_note(note: dict) -> dict[str, Any]:
    """将 XHS 笔记原始数据标准化为通用结构。"""
    nc = note.get("note_card", note)
    user = nc.get("user", {})
    interact = nc.get("interact_info", {})
    images = nc.get("image_list", [])

    image_urls = []
    for img in images:
        info_list = img.get("info_list", [])
        for info in info_list:
            if info.get("image_scene") == "WB_DFT":
                image_urls.append(info["url"])
                break
        else:
            if info_list:
                image_urls.append(info_list[0].get("url", ""))

    return {
        "platform_note_id": note.get("id", ""),
        "xsec_token": note.get("xsec_token", ""),
        "title": nc.get("display_title", nc.get("title", "")),
        "desc": nc.get("desc", ""),
        "type": nc.get("type", "normal"),
        "cover_url": (nc.get("cover", {}) or {}).get("url_default", ""),
        "image_urls": image_urls,
        "video_url": None,
        "author": {
            "id": user.get("user_id", ""),
            "nickname": user.get("nickname", user.get("nick_name", "")),
            "avatar": user.get("avatar", ""),
        },
        "stats": {
            "liked": int(interact.get("liked_count", 0)),
            "collected": int(interact.get("collected_count", 0)),
            "comments": int(interact.get("comment_count", 0)),
            "shared": int(interact.get("shared_count", 0)),
        },
        "tags": [t.get("text", "") for t in (nc.get("corner_tag_info", []) or [])],
        "crawled_at": datetime.now(timezone.utc).isoformat(),
        "raw": note,
    }


def normalize_comment(comment: dict, note_id: str = "") -> dict[str, Any]:
    """将 XHS 评论标准化。"""
    user_info = comment.get("user_info", {})
    return {
        "platform_comment_id": comment.get("id", ""),
        "note_id": note_id,
        "author": {
            "id": user_info.get("user_id", ""),
            "nickname": user_info.get("nickname", ""),
            "avatar": user_info.get("avatar", ""),
        },
        "content": comment.get("content", ""),
        "liked": int(comment.get("like_count", comment.get("liked_count", 0))),
        "created_at": comment.get("create_time", comment.get("created_at", "")),
        "sub_comments": [
            normalize_comment(sc, note_id)
            for sc in (comment.get("sub_comments", comment.get("target_comment", [])) or [])
        ],
        "crawled_at": datetime.now(timezone.utc).isoformat(),
        "raw": comment,
    }


def normalize_user(user_data: dict) -> dict[str, Any]:
    """将 XHS 用户信息标准化。"""
    basic = user_data.get("basic_info", user_data)
    return {
        "platform_user_id": basic.get("user_id", basic.get("id", "")),
        "nickname": basic.get("nickname", basic.get("nick_name", "")),
        "avatar": basic.get("avatar", basic.get("images", "")),
        "desc": basic.get("desc", ""),
        "gender": basic.get("gender", ""),
        "note_count": basic.get("note_count", 0),
        "follower_count": basic.get("follower_count", basic.get("fans_total", 0)),
        "following_count": basic.get("following_count", basic.get("follow_total", 0)),
        "crawled_at": datetime.now(timezone.utc).isoformat(),
        "raw": user_data,
    }


def format_crawl_result(notes: list[dict]) -> list[dict[str, Any]]:
    """批量将爬虫搜索结果格式化为 AiRestro 结构。"""
    return [normalize_note(n) for n in notes]


def summarize_for_db(
    normalized: dict[str, Any],
    shop_id: str | None = None,
    platform: str = "xiaohongshu",
) -> dict[str, Any]:
    """生成可存入 platform_shops 的结构（含 raw_json）。"""
    return {
        "platform": platform,
        "platform_shop_id": normalized["platform_note_id"],
        "shop_name": normalized["title"][:200] if normalized["title"] else "XHS Note",
        "shop_url": f"https://www.xiaohongshu.com/explore/{normalized['platform_note_id']}",
        "raw_json": normalized["raw"],
        "last_synced_at": datetime.now(timezone.utc),
    }


def summarize_review_for_db(
    normalized_comment: dict[str, Any],
    platform_shop_id: str,
) -> dict[str, Any]:
    """生成可存入 reviews 的结构。"""
    return {
        "platform_shop_id": platform_shop_id,
        "platform_review_id": normalized_comment["platform_comment_id"],
        "reviewer_name": normalized_comment["author"]["nickname"],
        "content": normalized_comment["content"],
        "reviewed_at": normalized_comment["created_at"],
        "sentiment": None,
        "reply_status": "unreplied",
    }
