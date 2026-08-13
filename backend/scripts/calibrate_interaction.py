"""互动类锚点标定脚本（v1.12 设计 §10 阶段 A）。

从 DB 已完成的博主分析任务里取真实样本（result.notes），按博主去重取最新，
按粉丝分层输出互动率/收藏率/爆文率分布，与当前 scoring_config 初值对比。

用法：
  python scripts/calibrate_interaction.py            # 全量已分析样本
  python scripts/calibrate_interaction.py --min-fans 1000 --max-fans 100000   # 只看 T2

说明：只读不改配置；输出为建议值，人工复核后再回填 crawler_config.json / scoring_config。
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "services"))

import asyncpg

from app.services.scoring_config import load_scoring_config, clear_scoring_config_cache


def _tier(fans: int) -> str:
    if fans < 10000:
        return "T1"
    if fans < 100000:
        return "T2"
    if fans < 1000000:
        return "T3"
    return "T4"


def _weighted(st: dict) -> float:
    return (
        int(st.get("liked", 0) or 0) * 1
        + int(st.get("collected", 0) or 0) * 4
        + int(st.get("comments", 0) or 0) * 5
        + int(st.get("shared", 0) or 0) * 6
    )


def _pct(vals: list[float], q: float) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    k = (len(s) - 1) * q
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def _fmt(v, digits=3):
    return "-" if v is None else f"{v:.{digits}f}"


async def main() -> None:
    ap = argparse.ArgumentParser(description="互动类锚点标定（读 DB 已分析真实样本）")
    ap.add_argument("--min-fans", type=int, default=0)
    ap.add_argument("--max-fans", type=int, default=10**12)
    args = ap.parse_args()

    clear_scoring_config_cache()
    cfg = load_scoring_config()
    tiers_cfg = cfg["tiers"]

    conn = await asyncpg.connect(user="aistro", password="aistro", database="aistro", host="localhost", port=5432)
    rows = await conn.fetch(
        "SELECT xhs_user_id, follower_count, status, finished_at, result "
        "FROM blogger_analysis_tasks WHERE status IN ('success','partial') ORDER BY finished_at"
    )
    await conn.close()

    # 按博主去重取最新
    latest: dict[str, dict] = {}
    for r in rows:
        xid = r["xhs_user_id"]
        if xid not in latest or (r["finished_at"] or 0) > (latest[xid]["finished_at"] or 0):
            latest[xid] = dict(r)

    buckets: dict[str, list[dict]] = defaultdict(list)
    skipped = {"old_format": 0, "no_notes": 0, "no_fans": 0, "fans_range": 0}
    for r in latest.values():
        fans = int(r["follower_count"] or 0)
        res = r["result"]
        if isinstance(res, str):
            try:
                res = json.loads(res)
            except Exception:
                res = None
        if not isinstance(res, dict):
            skipped["old_format"] += 1
            continue
        dims = res.get("dimensions")
        if not isinstance(dims, dict) or "seeding_depth" not in dims:
            skipped["old_format"] += 1
            continue
        notes = res.get("notes") or []
        if not notes:
            skipped["no_notes"] += 1
            continue
        if fans <= 0:
            skipped["no_fans"] += 1
            continue
        if not (args.min_fans <= fans <= args.max_fans):
            skipped["fans_range"] += 1
            continue
        stats_list = [n.get("stats") or {} for n in notes if isinstance(n, dict)]
        if not stats_list:
            skipped["no_notes"] += 1
            continue
        n = max(1, len(stats_list))
        weighted = sum(_weighted(s) for s in stats_list) / n
        interaction_rate_pct = weighted / fans * 100
        collects_pct = sum(int(s.get("collected", 0) or 0) for s in stats_list) / n / fans * 100
        # 爆文率：加权互动 >= 账号中位数×3
        ws = sorted(_weighted(s) for s in stats_list)
        med = statistics.median(ws) if ws else 0
        viral = sum(1 for w in ws if med > 0 and w >= med * 3) / n
        buckets[_tier(fans)].append(
            {
                "xid": r["xhs_user_id"][:10],
                "fans": fans,
                "ir_pct": interaction_rate_pct,
                "collect_pct": collects_pct,
                "viral": viral,
                "finished": r["finished_at"].strftime("%m-%d %H:%M") if r["finished_at"] else "",
            }
        )

    print("=" * 72)
    print(f"真实样本标定预览 ｜ 去重博主 {len(latest)} 个（跳过：旧格式 {skipped['old_format']} / 无笔记 {skipped['no_notes']} / 无粉丝 {skipped['no_fans']} / 粉丝范围 {skipped['fans_range']}）")
    print("=" * 72)
    tier_order = ["T1", "T2", "T3", "T4"]
    for t in tier_order:
        items = buckets[t]
        irs = [x["ir_pct"] for x in items]
        cols = [x["collect_pct"] for x in items]
        virs = [x["viral"] for x in items]
        cur_min_healthy = (tiers_cfg.get(t) or {}).get("min_healthy")
        print()
        print(f"【{t}】样本 {len(items)} 个")
        if not items:
            print("   无样本——该层无法标定，需刻意补样本")
            continue
        print(f"   当前初值 min_healthy = {cur_min_healthy}")
        print(
            f"   互动率%（全样本） P10={_fmt(_pct(irs, .1))}  P25={_fmt(_pct(irs, .25))}  P50={_fmt(_pct(irs, .5))}  P75={_fmt(_pct(irs, .75))}  P90={_fmt(_pct(irs, .9))}"
        )
        # 稳健版：剔除互动率 > 100%（疑似异常/极小账号/刷量）后的分布
        rob = [x for x in items if x["ir_pct"] <= 100.0]
        if len(rob) != len(items):
            rirs = [x["ir_pct"] for x in rob]
            rcols = [x["collect_pct"] for x in rob]
            print(f"   互动率%（剔除 {len(items) - len(rob)} 个 >100% 异常） P10={_fmt(_pct(rirs, .1))}  P25={_fmt(_pct(rirs, .25))}  P50={_fmt(_pct(rirs, .5))}  P75={_fmt(_pct(rirs, .75))}")
            print(
                f"   篇均收藏率%（稳健） P25={_fmt(_pct(rcols, .25), 2)}  P50={_fmt(_pct(rcols, .5), 2)}  P75={_fmt(_pct(rcols, .75), 2)}"
            )
        else:
            print(
                f"   篇均收藏率% P25={_fmt(_pct(cols, .25), 2)}  P50={_fmt(_pct(cols, .5), 2)}  P75={_fmt(_pct(cols, .75), 2)}"
            )
        print(f"   爆文率% P50={_fmt(_pct(virs, .5) * 100, 1)}")
        print("   明细:")
        for x in sorted(items, key=lambda y: -y["ir_pct"]):
            print(
                f"     {x['xid']}  fans={x['fans']:>8,}  互动率={x['ir_pct']:.2f}%  收藏率={x['collect_pct']:.2f}%  爆文率={x['viral']*100:.0f}%  {x['finished']}"
            )
        if len(rob) >= 8:
            print(f"   → 建议 min_healthy ≈ 稳健 P10 = {_pct([x['ir_pct'] for x in rob], .1):.3f}（低于视为不健康）")
        elif len(rob) >= 3:
            print(f"   → 稳健样本 {len(rob)} 个，仅作方向参考；每层 ≥30 才算可信标定")
        elif len(items) >= 3:
            print(f"   → 样本 {len(items)} 个，仅作方向参考；每层 ≥30 才算可信标定")
        else:
            print("   → 样本不足，无法给出建议值")

    print()
    print("说明：标定只覆盖互动类锚点（min_healthy/收藏率分档）。报价锚点需蒲公英相似创作者接口（当前余额不足）。")
    print("回填：人工复核后将 min_healthy 写入 crawler_config.json 的 blogger_scoring.tiers.<T>（或 scoring_config 默认值）。")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
