"""从导出的笔记 CSV 导入真实详情缓存，并做首轮互动率标定。

用法：
  python scripts/calibrate_from_csv.py --input "D:/小红书笔记.csv"

步骤：
1. 把 CSV 中每篇笔记标准化后写入 note_details（按 博主ID+笔记ID 去重，分析任务可直接复用）
2. 对每位博主调用 user/info 补粉丝数（受风控门禁约束）
3. 按粉丝分层输出篇均互动率百分位，落盘 reports/calibration_from_csv.csv

注意：CSV 每位博主通常只有 1 篇笔记，只能标定"篇均互动率"口径；
"优质笔记占比/类型标准化"需要同一博主多篇样本，需另跑 calibrate_thresholds.py 抓详情。
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import io
import os
import sys
import urllib.parse
from collections import defaultdict
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "services"))

from app.core.database import async_session_factory
from app.services.analysis_task_runner import _upsert_detail
from app.services.blogger_scoring import _weighted
from crawler.config import get_cookie, get_proxy_pool
from crawler.processor import _parse_count
from crawler.xhs import XhsCrawler


def normalize_row(row: dict) -> dict:
    link = row.get("笔记链接", "")
    token = urllib.parse.parse_qs(urllib.parse.urlparse(link).query).get("xsec_token", [""])[0]
    published = None
    try:
        published = datetime.strptime(row.get("发布时间", "").strip(), "%Y-%m-%d %H:%M").isoformat()
    except ValueError:
        pass
    images = [u.strip() for u in (row.get("笔记图片链接") or "").splitlines() if u.strip()]
    tags = [t.strip() for t in (row.get("笔记话题") or "").split(";") if t.strip()]
    return {
        "platform_note_id": row.get("笔记ID", ""),
        "xsec_token": token,
        "title": row.get("笔记标题", ""),
        "desc": row.get("笔记内容", ""),
        "type": "video" if row.get("笔记类型") == "视频" else "normal",
        "cover_url": row.get("笔记封面链接", "") or "",
        "image_urls": images,
        "video_url": row.get("笔记视频链接", "") or "",
        "author": {"id": row.get("博主ID", ""), "nickname": row.get("博主昵称", ""), "avatar": ""},
        "stats": {
            "liked": _parse_count(row.get("点赞量")),
            "collected": _parse_count(row.get("收藏量")),
            "comments": _parse_count(row.get("评论量")),
            "shared": _parse_count(row.get("分享量")),
        },
        "tags": tags,
        "published_at": published,
        "full_stats": True,
    }


def read_rows(path: str) -> list[dict]:
    raw = open(path, "rb").read()
    text = None
    for enc in ("utf-8-sig", "gb18030"):
        try:
            text = raw.decode(enc)
            break
        except (UnicodeDecodeError, UnicodeError):
            continue
    if text is None:
        raise SystemExit("无法识别 CSV 编码")
    return list(csv.DictReader(io.StringIO(text)))


async def import_rows(rows: list[dict]) -> int:
    count = 0
    async with async_session_factory() as db:
        for row in rows:
            uid = row.get("博主ID", "")
            nid = row.get("笔记ID", "")
            if not uid or not nid:
                continue
            await _upsert_detail(db, uid, nid, normalize_row(row))
            count += 1
        await db.commit()
    return count


async def fetch_fans(uid: str, nickname: str = "") -> int | None:
    crawler = XhsCrawler(get_cookie(), proxy_pool=get_proxy_pool(), min_delay=1.0, max_delay=2.0, max_retries=1)
    from app.services.xhs_user_resolver import resolve_user_profile
    profile = await resolve_user_profile(crawler, uid, nickname=nickname)
    if profile.get("ok"):
        return profile.get("fans")
    return None


def _pct(vals: list[float], q: float) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    idx = min(len(s) - 1, int(q * len(s)))
    return round(s[idx], 3)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=r"D:\小红书笔记.csv")
    args = parser.parse_args()

    rows = read_rows(args.input)
    imported = await import_rows(rows)
    print(f"导入 note_details：{imported} 篇")

    by_blogger: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        uid = row.get("博主ID", "")
        if uid:
            by_blogger[uid].append(normalize_row(row))

    stats = []
    for uid, notes in by_blogger.items():
        fans = await fetch_fans(uid, nickname=notes[0]["author"]["nickname"])
        if not fans:
            print(f"skip {uid}（粉丝数获取失败）")
            continue
        rate = sum(_weighted(n["stats"]) for n in notes) / fans / len(notes) * 100.0
        stats.append({
            "uid": uid,
            "nickname": notes[0]["author"]["nickname"],
            "fans": fans,
            "notes": len(notes),
            "rate": round(rate, 4),
        })
        print(f"ok {uid} fans={fans} rate={rate:.3f}%")

    tiers = {"T1": (1000, 10000), "T2": (10000, 100000), "T3": (100000, 1000000), "T4": (1000000, None)}
    os.makedirs(os.path.join(ROOT, "reports"), exist_ok=True)
    out_path = os.path.join(ROOT, "reports", "calibration_from_csv.csv")
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["uid", "nickname", "fans", "notes", "rate"])
        writer.writeheader()
        writer.writerows(stats)

    for name, (lo, hi) in tiers.items():
        group = [r for r in stats if r["fans"] >= lo and (hi is None or r["fans"] < hi)]
        if not group:
            continue
        rates = [r["rate"] for r in group]
        print(f"\n[{name}] n={len(group)}")
        print(f"  篇均互动率 P10/P25/P50/P75/P90: {_pct(rates,0.1)}/{_pct(rates,0.25)}/{_pct(rates,0.5)}/{_pct(rates,0.75)}/{_pct(rates,0.9)}")
    print(f"\n已保存：{out_path}")


if __name__ == "__main__":
    asyncio.run(main())

