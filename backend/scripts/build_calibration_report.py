"""
风控校准报告（方案 §1.4 / 附录 A）。

读取 services/crawler/xhs/scripts/crawl_request_log.jsonl，输出：
- 总请求数 / 结果分布（ok / network_error / risk_signal / circuit_open / http_error）
- 风控信号频率 = risk_signal / 总请求
- risk_type 分布（data_null / captcha / x_rap_param / login_expired / rate_limit / other）
- 熔断触发次数（circuit_open 记录数）
- 平均实际间隔 interval_before_ms

用法：
  python scripts/build_calibration_report.py                 # 只看 JSONL
  python scripts/build_calibration_report.py --ingest        # 同时幂等写入 crawl_request_log 表
  python scripts/build_calibration_report.py --days 7        # 只看最近 7 天
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import sys
import time
import uuid
from collections import Counter

_LOG_PATH = os.path.join(
    os.path.dirname(__file__), "..", "services", "crawler", "xhs", "scripts", "crawl_request_log.jsonl"
)


def _safe_console():
    """Windows GBK 控制台遇到特殊字符（如 \xa0）会崩，强制 UTF-8 输出。"""
    try:
        if sys.stdout and hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


_safe_console()

def load_records(path: str, days: int | None = None):
    cutoff = None
    if days:
        cutoff = (time.time() - days * 86400) * 1000
    records = []
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                if cutoff and int(r.get("ts_ms", 0)) < cutoff:
                    continue
                records.append(r)
    return records


def build_report(records) -> dict:
    total = len(records)
    by_result = Counter(r.get("result", "unknown") for r in records)
    risk_records = [r for r in records if r.get("result") == "risk_signal"]
    risk_types = Counter(r.get("risk_type") or "other" for r in risk_records)
    intervals = [r.get("interval_before_ms") for r in records if r.get("interval_before_ms") is not None]
    latencies = [r.get("latency_ms") for r in records if r.get("latency_ms") is not None]
    risk_rate = len(risk_records) / total if total else 0.0
    return {
        "total": total,
        "by_result": dict(by_result),
        "risk_signal_rate": round(risk_rate, 6),
        "risk_type_distribution": dict(risk_types),
        "circuit_opens": by_result.get("circuit_open", 0),
        "avg_interval_before_ms": round(sum(intervals) / len(intervals)) if intervals else None,
        "avg_latency_ms": round(sum(latencies) / len(latencies)) if latencies else None,
    }


def ingest(records) -> None:
    """用 asyncpg 幂等写入 crawl_request_log 表。"""
    import asyncio
    import asyncpg

    async def run():
        conn = await asyncpg.connect(
            host="localhost", port=5432, user="aistro", password="aistro", database="aistro"
        )
        try:
            inserted = 0
            for r in records:
                key_src = "|".join([
                    uuid.uuid4(),
                    r.get("channel", "redcrack"),
                    r.get("job_type", ""),
                    str(r.get("target", "")),
                    str(r.get("ts_ms", "")),
                    r.get("result", ""),
                    str(r.get("latency_ms", "")),
                ])
                record_key = hashlib.md5(key_src.encode("utf-8")).hexdigest()
                await conn.execute(
                    """
                    INSERT INTO crawl_request_log
                      (id, channel, job_type, target, result, risk_type, http_status,
                       latency_ms, interval_before_ms, proxy_used, error_message, record_key, created_at)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12, to_timestamp($13 / 1000.0))
                    ON CONFLICT (record_key) DO NOTHING
                    """,
                    r.get("channel", "redcrack"),
                    r.get("job_type", ""),
                    str(r.get("target", "")),
                    r.get("result", "ok"),
                    r.get("risk_type"),
                    r.get("http_status"),
                    r.get("latency_ms"),
                    r.get("interval_before_ms"),
                    r.get("proxy_used"),
                    (r.get("error_message") or "")[:500],
                    record_key,
                    int(r.get("ts_ms", time.time() * 1000)),
                )
                inserted += 1
            print(f"ingested {inserted} rows (ON CONFLICT DO NOTHING)")
        finally:
            await conn.close()

    asyncio.run(run())


def main() -> None:
    parser = argparse.ArgumentParser(description="风控校准报告")
    parser.add_argument("--log", default=_LOG_PATH, help="crawl_request_log.jsonl 路径")
    parser.add_argument("--days", type=int, default=None, help="只看最近 N 天")
    parser.add_argument("--ingest", action="store_true", help="同时幂等写入 crawl_request_log 表")
    args = parser.parse_args()

    records = load_records(args.log, args.days)
    report = build_report(records)

    print("=" * 50)
    print("风控校准报告")
    print("=" * 50)
    print(f"日志文件       : {args.log}")
    print(f"时间范围       : 最近 {args.days} 天" if args.days else "时间范围       : 全部")
    print(f"总请求数       : {report['total']}")
    print(f"结果分布       : {report['by_result']}")
    print(f"风控信号频率   : {report['risk_signal_rate']:.4%}")
    print(f"风险类型分布   : {report['risk_type_distribution']}")
    print(f"熔断触发次数   : {report['circuit_opens']}")
    print(f"平均实际间隔   : {report['avg_interval_before_ms']} ms" if report["avg_interval_before_ms"] is not None else "平均实际间隔   : -")
    print(f"平均请求耗时   : {report['avg_latency_ms']} ms" if report["avg_latency_ms"] is not None else "平均请求耗时   : -")
    print("=" * 50)

    if report["total"] == 0:
        print("提示：暂无观测记录。爬虫跑起来后会自动写入。")
    elif report["total"] < 500:
        print(f"提示：样本量 {report['total']} < 500，按方案 §1.4 尚不足以触发校准动作。")
    else:
        rate = report["risk_signal_rate"]
        if rate < 0.0005:
            print("校准建议：信号频率 < 0.5‰，可尝试放宽间隔 10-20%（需重置 7 天观察窗）。")
        elif rate < 0.002:
            print("校准建议：0.5‰–2‰，维持基线，继续观察。")
        elif rate < 0.005:
            print("校准建议：2‰–5‰，轻度收紧：间隔 +20%、批量 -20%。")
        elif rate < 0.01:
            print("校准建议：5‰–1%，明显收紧：间隔 +50%、单任务上限减半、优先走真实会话通道。")
        else:
            print("校准建议：> 1%，立即熔断 + 人工交接 + 回退到最保守档。")

    if args.ingest:
        ingest(records)


if __name__ == "__main__":
    main()
