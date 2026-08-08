"""一次性跑完候选池剩余账号的真实数据标定（断点续跑 + 失败重试一轮）。

用法：
  python scripts/run_calibration_all.py --notes 10 --batch 20

- 从 reports/calibration_pool.csv 读取候选账号
- 已成功账号跳过；失败账号首轮结束后重试一轮（attempt=2）
- 每账号结果即时追加到 reports/calibration_full.csv，中断后重跑会自动续上
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import os
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "services"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from calibrate_thresholds import analyze_account  # noqa: E402

POOL = os.path.join(ROOT, "reports", "calibration_pool.csv")
BATCH1 = os.path.join(ROOT, "reports", "calibration_batch1.csv")
OUTPUT = os.path.join(ROOT, "reports", "calibration_full.csv")
FIELDS = ["uid", "nickname", "status", "attempt", "fans", "rate", "quality_ratio", "sample", "error", "run_at"]


def tier_of(fans: int | None) -> str:
    if fans is None:
        return "U"
    if fans >= 1000000:
        return "T4"
    if fans >= 100000:
        return "T3"
    if fans >= 10000:
        return "T2"
    if fans >= 1000:
        return "T1"
    return "U"


def read_csv(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_output(rows: list[dict]) -> None:
    with open(OUTPUT, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


def load_state() -> dict[str, dict]:
    state: dict[str, dict] = {}
    # 第一批已完成数据视为成功（attempt=1）
    for r in read_csv(BATCH1):
        state[r["uid"]] = {
            "uid": r["uid"], "nickname": r.get("nickname", ""), "status": "success", "attempt": 1,
            "fans": r.get("fans", ""), "rate": r.get("rate_percent", r.get("rate", "")),
            "quality_ratio": r.get("quality_ratio", ""), "sample": r.get("sample", ""),
            "error": "", "run_at": "2026-08-07",
        }
    for r in read_csv(OUTPUT):
        row = dict(r)
        if row.get("status") == "failed" and ("Cookie" in row.get("error", "") or "失效" in row.get("error", "") or "过期" in row.get("error", "")):
            # Cookie 类失败是环境问题，不是账号数据问题；下次运行时重新首轮
            row["attempt"] = "0"
        state[r["uid"]] = row
    return state


def build_batches(uids: list[str], tier_map: dict[str, str], batch_size: int) -> list[list[str]]:
    groups: dict[str, list[str]] = {"T1": [], "T2": [], "T3": [], "T4": [], "U": []}
    for uid in uids:
        groups[tier_map.get(uid, "U")].append(uid)
    batches: list[list[str]] = []
    cur: list[str] = []
    idx = {k: 0 for k in groups}
    order = ["T1", "T2", "T3", "T4", "U"]
    while any(idx[k] < len(groups[k]) for k in order):
        for k in order:
            if idx[k] < len(groups[k]):
                cur.append(groups[k][idx[k]])
                idx[k] += 1
                if len(cur) >= batch_size:
                    batches.append(cur)
                    cur = []
    if cur:
        batches.append(cur)
    return batches


async def run_pass(uids: list[str], tier_map: dict[str, str], notes: int, state: dict[str, dict], attempt: int) -> list[str]:
    failed: list[str] = []
    for i, uid in enumerate(uids, 1):
        result = await analyze_account(uid, notes)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if result and result.get("rate") is not None:
            state[uid] = {"uid": uid, "nickname": "", "status": "success", "attempt": attempt, "fans": result["fans"], "rate": result["rate"], "quality_ratio": result["quality_ratio"], "sample": result["sample"], "error": "", "run_at": now}
            print(f"[{attempt}][{i}/{len(uids)}] ok {uid} fans={result['fans']} rate={result['rate']:.3f} quality={result['quality_ratio']:.1f} sample={result['sample']}", flush=True)
        else:
            failed.append(uid)
            err = (result or {}).get("error") or "抓取失败或信息不足"
            state[uid] = {"uid": uid, "nickname": "", "status": "failed", "attempt": attempt, "fans": "", "rate": "", "quality_ratio": "", "sample": "", "error": err, "run_at": now}
            print(f"[{attempt}][{i}/{len(uids)}] fail {uid}（{err}）", flush=True)
        if i % 5 == 0 or i == len(uids):
            write_output([state[u] for u in state])
    return failed


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--notes", type=int, default=10)
    parser.add_argument("--batch", type=int, default=20)
    args = parser.parse_args()

    pool = read_csv(POOL)
    state = load_state()
    tier_map = {r["uid"]: tier_of(int(r["fans"]) if r.get("fans") else None) for r in pool}

    # 首轮：未跑过的账号
    first = [r["uid"] for r in pool if r["uid"] not in state or state[r["uid"]]["status"] == "failed" and int(state[r["uid"]].get("attempt", 0) or 0) < 1]
    # 待重试：attempt=1 且失败的账号
    retry = [uid for uid, st in state.items() if st["status"] == "failed" and int(st.get("attempt", 0) or 0) == 1 and uid in tier_map]
    # 从首轮集合中剔除 attempt>=1 的失败（它们归 retry）
    first = [uid for uid in first if uid not in retry]

    if first:
        print(f"首轮待跑 {len(first)}", flush=True)
        for bi, batch in enumerate(build_batches(first, tier_map, args.batch), 1):
            print(f"--- 首轮批次 {bi}（{len(batch)}）---", flush=True)
            await run_pass(batch, tier_map, args.notes, state, attempt=1)

    # 首轮结束后，把本轮新增的失败账号纳入重试（attempt=1 -> attempt=2）
    retry = [uid for uid, st in state.items() if st["status"] == "failed" and int(st.get("attempt", 0) or 0) == 1 and uid in tier_map]
    if retry:
        print(f"重试 {len(retry)}", flush=True)
        await run_pass(retry, tier_map, args.notes, state, attempt=2)

    write_output([state[u] for u in state])
    ok = sum(1 for st in state.values() if st["status"] == "success")
    fail = sum(1 for st in state.values() if st["status"] == "failed")
    print(f"完成：成功 {ok}，失败 {fail}，输出 {OUTPUT}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
