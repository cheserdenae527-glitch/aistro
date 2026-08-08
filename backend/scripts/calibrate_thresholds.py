"""阈值标定脚本（DESIGN-BLOGGER-SCORING-REALDATA.md §8）。

用法：
  python scripts/calibrate_thresholds.py --accounts 账号1,账号2,... [--notes 50]

对每个账号做全量/部分真实详情抓取，按粉丝分层输出：
  - 篇均互动率（%）
  - 优质笔记占比（%）
并给出 P10/P25/P50/P75/P90 百分位，供人工回填 crawler_config.json 的分层阈值。

说明：脚本不修改任何配置；跑批会消耗真实详情请求，请配合风控门禁节奏。
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "services"))

from crawler.config import get_cookie, get_proxy_pool, get_delay_settings
from crawler.processor import normalize_note
from crawler.xhs import XhsCrawler
from app.services.blogger_scoring import _type_standardized, _weighted, _parse_dt, CN_TZ


def _pct(vals: list[float], q: float) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    idx = min(len(s) - 1, int(q * len(s)))
    return round(s[idx], 3)


async def analyze_account(uid: str, sample_limit: int) -> dict | None:
    cookie = get_cookie()
    proxies = get_proxy_pool()
    min_d, max_d, retries = get_delay_settings()
    crawler = XhsCrawler(cookie, proxy_pool=proxies, min_delay=min_d, max_delay=max_d, max_retries=1)

    user_url = f"https://www.xiaohongshu.com/user/profile/{uid}"
    notes_result = await asyncio.to_thread(crawler.get_user_notes, user_url)
    if not notes_result.success:
        return {"uid": uid, "fans": None, "rate": None, "quality_ratio": None, "sample": None, "error": str(notes_result.error)}
    raw = notes_result.data or []
    nickname = ""
    for n in raw:
        if isinstance(n, dict):
            u = n.get("user") or {}
            if isinstance(u, dict):
                nickname = u.get("nickname") or u.get("nick_name") or u.get("name") or ""
                if nickname:
                    break
    from app.services.xhs_user_resolver import resolve_user_profile
    profile = await resolve_user_profile(crawler, uid, nickname=nickname)
    fans = profile.get("fans", 0)
    real: list[dict] = []
    now = datetime.now(CN_TZ)
    for n in raw[:sample_limit]:
        n.setdefault("id", n.get("note_id", ""))
        nid = n.get("id", "")
        token = n.get("xsec_token", "")
        if not nid or not token:
            continue
        url = f"https://www.xiaohongshu.com/explore/{nid}?xsec_token={token}&xsec_source=pc_user"
        detail = await asyncio.to_thread(crawler.get_note_detail, url)
        payload = detail.data
        items = []
        if isinstance(payload, dict):
            inner = payload.get("data", {}) if isinstance(payload.get("data"), dict) else payload
            items = inner.get("items") or []
        if items:
            norm = normalize_note(items[0])
            if _parse_dt(norm.get("published_at")) is not None:
                real.append(norm)
    if not real or fans <= 0:
        return {"uid": uid, "fans": fans if fans else None, "rate": None, "quality_ratio": None, "sample": 0, "error": "信息不足或抓取失败"}
    cutoff = now - timedelta(days=90)
    recent = [n for n in real if _parse_dt(n["published_at"]) >= cutoff]
    if not recent:
        return None
    total_w = sum(_weighted(n["stats"]) for n in recent)
    rate = total_w / fans / len(recent) * 100.0
    std = _type_standardized(real)
    quality_ratio = sum(1 for v in std if v >= 200) / len(real) * 100.0
    return {"uid": uid, "fans": fans, "rate": rate, "quality_ratio": quality_ratio, "sample": len(real), "error": None}


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--accounts", required=True, help="逗号分隔的小红书用户 ID")
    parser.add_argument("--notes", type=int, default=50, help="每个账号抓取详情上限")
    args = parser.parse_args()

    uids = [u.strip() for u in args.accounts.split(",") if u.strip()]
    rows = []
    for uid in uids:
        row = await analyze_account(uid, args.notes)
        if row and row.get("rate") is not None:
            rows.append(row)
            print(f"ok {uid} fans={row['fans']} rate={row['rate']:.3f}% quality={row['quality_ratio']:.1f}% sample={row['sample']}")
        else:
            print(f"skip {uid}（{((row or {}).get('error')) or '信息不足或抓取失败'}）")

    tiers = {"T1": (1000, 10000), "T2": (10000, 100000), "T3": (100000, 1000000), "T4": (1000000, None)}
    for name, (lo, hi) in tiers.items():
        group = [r for r in rows if r["fans"] >= lo and (hi is None or r["fans"] < hi)]
        if not group:
            continue
        rates = [r["rate"] for r in group]
        quals = [r["quality_ratio"] for r in group]
        print(f"\n[{name}] n={len(group)}")
        print(f"  篇均互动率 P10/P25/P50/P75/P90: {_pct(rates,0.1)}/{_pct(rates,0.25)}/{_pct(rates,0.5)}/{_pct(rates,0.75)}/{_pct(rates,0.9)}")
        print(f"  优质笔记占比 P10/P25/P50/P75/P90: {_pct(quals,0.1)}/{_pct(quals,0.25)}/{_pct(quals,0.5)}/{_pct(quals,0.75)}/{_pct(quals,0.9)}")


if __name__ == "__main__":
    asyncio.run(main())


