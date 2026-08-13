"""分层补样本脚本：用相似创作者接口拉同量级达人，筛出未分析的目标层名单。

用法：
  python scripts/collect_tier_samples.py                          # 只看覆盖与待分析名单
  python scripts/collect_tier_samples.py --analyze                # 对目标层名单发起批量分析
  python scripts/collect_tier_samples.py --tiers T1,T3,T4 --per-tier 30

数据流：DB 已分析博主作种子 → 蒲公英相似创作者拉达人 → 按粉丝分层 → 去重（排除已分析）
→ 每层挑未分析达人 → （--analyze）POST /notes/analysis-tasks/batch 发起真实分析。
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import urllib.request
from collections import defaultdict

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


async def _analyzed_ids() -> set[str]:
    conn = await asyncpg.connect(user="aistro", password="aistro", database="aistro", host="localhost", port=5432)
    rows = await conn.fetch("SELECT DISTINCT xhs_user_id FROM blogger_analysis_tasks")
    await conn.close()
    return {r["xhs_user_id"] for r in rows}


async def _seeds() -> list[str]:
    conn = await asyncpg.connect(user="aistro", password="aistro", database="aistro", host="localhost", port=5432)
    rows = await conn.fetch(
        "SELECT DISTINCT xhs_user_id FROM blogger_analysis_tasks WHERE status IN ('success','partial')"
    )
    await conn.close()
    return [r["xhs_user_id"] for r in rows]


def _post_batch(bloggers: list[dict]) -> dict:
    from app.core.security import create_access_token
    from datetime import timedelta

    token = create_access_token({"sub": "f327ccd7-f5d8-4991-af7e-6867c57edfca"}, timedelta(minutes=30))
    import json as _json

    body = _json.dumps({"bloggers": bloggers}).encode("utf-8")
    req = urllib.request.Request(
        "http://127.0.0.1:8000/api/v1/notes/analysis-tasks/batch",
        data=body,
        method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        return _json.loads(r.read().decode("utf-8"))


async def main() -> None:
    ap = argparse.ArgumentParser(description="分层补样本（相似创作者）")
    ap.add_argument("--tiers", type=str, default="T1,T3,T4", help="目标层，逗号分隔")
    ap.add_argument("--per-tier", type=int, default=30, help="每层最多发起多少个")
    ap.add_argument("--max-fans", type=int, default=0, help="排除粉丝超过该值的博主（0=不限）；避开明星大 V 防风控")
    ap.add_argument("--batch", type=int, default=0, help="分批大小（0=一次全发）；分批可降低风控触发概率")
    ap.add_argument("--analyze", action="store_true", help="发起批量分析")
    args = ap.parse_args()
    targets = {t.strip() for t in args.tiers.split(",") if t.strip()}

    seeds = await _seeds()
    analyzed = await _analyzed_ids()
    print(f"种子博主 {len(seeds)} 个，已分析博主 {len(analyzed)} 个")

    # 拉相似创作者
    cand: dict[str, dict] = {}
    errors = defaultdict(int)
    for seed in seeds:
        res = fetch_similar_kol(seed)
        if not res.get("ok"):
            errors[res.get("error") or "未知错误"] += 1
            continue
        for k in (res.get("data") or {}).get("kols") or []:
            uid = k.get("userId")
            fans = int(k.get("fansCount") or 0)
            if not uid or uid in cand or fans < 1000:
                continue
            cand[uid] = {
                "user_id": uid,
                "nickname": k.get("name") or uid,
                "fans": fans,
                "avatar": k.get("headPhoto"),
            }
    print(f"相似创作者去重候选 {len(cand)} 个")
    for err, n in errors.items():
        print(f"  ⚠ 种子失败 {n} 个：{err}")

    by_tier: dict[str, list[dict]] = defaultdict(list)
    for c in cand.values():
        if c["user_id"] in analyzed:
            continue
        if args.max_fans and c["fans"] > args.max_fans:
            continue
        by_tier[_tier(c["fans"])].append(c)

    print()
    for t in ["T1", "T2", "T3", "T4"]:
        un = by_tier.get(t, [])
        mark = " ← 目标层" if t in targets else ""
        print(f"【{t}】未分析候选 {len(un)} 个{mark}")

    to_analyze: list[dict] = []
    for t in targets:
        un = sorted(by_tier.get(t, []), key=lambda x: -x["fans"])
        picked = un[: args.per_tier]
        to_analyze.extend(picked)
        print(f"  → {t} 将发起 {len(picked)} 个：{', '.join(x['nickname'][:10] for x in picked[:8])}{'...' if len(picked) > 8 else ''}")

    if not to_analyze:
        print("目标层无未分析候选——请补充种子或换层")
        return

    if not args.analyze:
        print()
        print("（未发起分析。加 --analyze 执行批量分析）")
        return

    print()
    if args.batch and len(to_analyze) > args.batch:
        batches = [to_analyze[i:i + args.batch] for i in range(0, len(to_analyze), args.batch)]
    else:
        batches = [to_analyze]
    for bi, batch in enumerate(batches, 1):
        print(f"[批次 {bi}/{len(batches)}] 发起批量分析 {len(batch)} 个博主 ...")
        resp = _post_batch(batch)
        print(f"  创建 {len(resp.get('created', []))} 个任务，拒绝 {len(resp.get('rejected', []))} 个")
        for r in resp.get("rejected", []):
            print(f"  拒绝 {r.get('nickname')}: {r.get('reason')}")
        if bi < len(batches):
            print("  等待风控冷却 180s ...")
            import time as _time
            _time.sleep(180)


if __name__ == "__main__":
    asyncio.run(main())
