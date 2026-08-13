"""报价锚点标定脚本（v1.12 设计 §10 阶段 C）。

从蒲公英「相似创作者」接口收集同层博主真实报价（图文/视频），按粉丝分层输出
P25/P50/P75，作为 scoring_config.cost.price_anchors 的标定来源。

用法：
  python scripts/calibrate_price_anchors.py                          # 种子 = DB 已分析博主
  python scripts/calibrate_price_anchors.py --seeds id1,id2,id3     # 显式指定种子博主

前置：JustOneAPI Token 有效且有余额（当前余额不足时会明确提示）。
说明：只读不改配置；每层样本 ≥30 才可信，否则仅作方向参考。
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "services"))

import asyncpg

from app.services.justoneapi_client import fetch_similar_kol


def _tier(fans: int) -> str:
    if fans < 10000:
        return "T1"
    if fans < 100000:
        return "T2"
    if fans < 1000000:
        return "T3"
    return "T4"


def _pct(vals: list[float], q: float) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    k = (len(s) - 1) * q
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def _fmt(v):
    return "-" if v is None else f"{v:.0f}"


async def _seeds_from_db() -> list[str]:
    conn = await asyncpg.connect(user="aistro", password="aistro", database="aistro", host="localhost", port=5432)
    rows = await conn.fetch(
        "SELECT DISTINCT xhs_user_id FROM blogger_analysis_tasks WHERE status IN ('success','partial')"
    )
    await conn.close()
    return [r["xhs_user_id"] for r in rows]


async def main() -> None:
    ap = argparse.ArgumentParser(description="报价锚点标定（蒲公英相似创作者）")
    ap.add_argument("--seeds", type=str, default="", help="种子博主 xhs_user_id，逗号分隔；缺省用 DB 已分析博主")
    args = ap.parse_args()

    seeds = [s.strip() for s in args.seeds.split(",") if s.strip()] if args.seeds else await _seeds_from_db()
    print(f"种子博主 {len(seeds)} 个：{', '.join(s[:10] for s in seeds[:10])}{'...' if len(seeds) > 10 else ''}")
    print("开始拉取相似创作者报价（每个种子约返回 4 个相似达人）...")

    from collections import defaultdict

    samples = []  # {uid, fans, pic, vid}
    seen: set[str] = set()
    errors = defaultdict(int)
    for seed in seeds:
        res = fetch_similar_kol(seed)
        if not res.get("ok"):
            errors[res.get("error") or "未知错误"] += 1
            continue
        for k in (res.get("data") or {}).get("kols") or []:
            uid = k.get("userId")
            fans = int(k.get("fansCount") or 0)
            if not uid or uid in seen:
                continue
            seen.add(uid)
            if fans < 1000:
                continue  # 只收 T1 及以上
            pic = k.get("picturePrice")
            vid = k.get("videoPrice")
            samples.append(
                {
                    "uid": uid,
                    "fans": fans,
                    "pic": float(pic) if pic else None,
                    "vid": float(vid) if vid else None,
                }
            )

    print(f"收集到去重相似达人 {len(samples)} 个")
    for err, n in errors.items():
        print(f"  ⚠ 种子失败 {n} 个：{err}")

    if not samples:
        print("无报价样本——请检查 JustOneAPI 余额/Token，或指定有效种子博主后重试")
        return

    tier_order = ["T1", "T2", "T3", "T4"]
    by_tier: dict[str, list[dict]] = defaultdict(list)
    for s in samples:
        by_tier[_tier(s["fans"])].append(s)

    print()
    print("=" * 70)
    print("分层报价分布（P25 / P50 / P75，元）")
    print("=" * 70)
    anchors = {}
    for t in tier_order:
        items = by_tier.get(t, [])
        pics = [x["pic"] for x in items if x["pic"] is not None and x["pic"] > 0]
        vids = [x["vid"] for x in items if x["vid"] is not None and x["vid"] > 0]
        print(f"【{t}】达人 {len(items)} 个（图文报价 {len(pics)} / 视频报价 {len(vids)}）")
        if not pics and not vids:
            print("   无报价样本")
            continue
        if pics:
            print(
                f"   图文 P25={_fmt(_pct(pics, .25))}  P50={_fmt(_pct(pics, .5))}  P75={_fmt(_pct(pics, .75))}"
            )
        if vids:
            print(
                f"   视频 P25={_fmt(_pct(vids, .25))}  P50={_fmt(_pct(vids, .5))}  P75={_fmt(_pct(vids, .75))}"
            )
        n_pic, n_vid = len(pics), len(vids)
        if n_pic >= 30 and n_vid >= 30:
            anchors[t] = {"picture": round(_pct(pics, .5)), "video": round(_pct(vids, .5))}
            print(f"   → 建议 price_anchor：{anchors[t]}")
        else:
            print(f"   → 样本不足（图文 {n_pic} / 视频 {n_vid}，每项 ≥30 才可信），仅作方向参考")

    if anchors:
        print()
        print("建议回填 scoring_config.cost.price_anchors：")
        print(json.dumps({"price_anchors": anchors}, ensure_ascii=False, indent=2))
    print()
    print("说明：P50 作为图文中位报价锚点；P25-P75 可作为 fair_price 合理带参照。")


if __name__ == "__main__":
    import json

    asyncio.run(main())
