from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

def _load_env() -> None:
    """把 backend/.env 读进环境变量（setdefault：外部已设置的值优先）。"""
    env_file = ROOT / "backend" / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def is_old_format(result: dict) -> bool:
    """旧四维格式判定：dimensions 是 dict、无 seeding_depth、含旧维度键。"""
    dimensions = result.get("dimensions")
    if not isinstance(dimensions, dict):
        return False
    if "seeding_depth" in dimensions:
        return False
    return "trend" in dimensions or "content_stability" in dimensions


def recompute_result(task) -> dict:
    """用新引擎把旧 result 重算为新的五维结果，并注入顶层 nickname。"""
    from app.services.blogger_scoring import score_blogger

    old = task.result or {}
    notes = old.get("notes") or []
    cov = old.get("coverage") or {}
    follower_count = task.follower_count or 0
    total_notes = cov.get("total_notes") or task.total_notes or len(notes)
    sampled = bool(old.get("sampled", False))
    coverage_denominator = cov.get("sample_size") or None
    raw_history = old.get("follower_history") or []
    # 真实旧数据里 follower_history 可能是已汇总 dict（带 series），需还原为
    # score_blogger 期望的原始快照列表；已是 list 时原样透传。
    if isinstance(raw_history, dict):
        raw_history = raw_history.get("series") or []
    new_result = score_blogger(
        notes,
        follower_count=follower_count,
        total_notes=total_notes,
        sampled=sampled,
        coverage_denominator=coverage_denominator,
        follower_history=raw_history,
    )
    # 注入昵称（兼容运行器逻辑；score_blogger 结果本身不含顶层 nickname）
    new_result["nickname"] = old.get("nickname") or ""
    if not new_result["nickname"]:
        for n in notes:
            author = n.get("author") or {}
            if author.get("nickname"):
                new_result["nickname"] = author["nickname"]
                break
    return new_result


def _dim_keys(result: dict) -> list[str]:
    return sorted((result.get("dimensions") or {}).keys())


def _overall_score(result: dict):
    overall = result.get("overall") or {}
    return overall.get("score")


async def collect_old_tasks(dry_run: bool, limit: int | None = None) -> tuple[int, int]:
    """遍历 success/partial 任务，把旧格式行重算为五维并落库。

    dry_run=True 只打印预览；dry_run=False 且命中旧格式时才写库（循环后
    一次性 commit）。返回 (旧格式数, 跳过非旧格式数)。
    """
    from app.core.database import async_session_factory
    from app.models.analysis_task import BloggerAnalysisTask
    from sqlalchemy import select

    async with async_session_factory() as session:
        stmt = (
            select(BloggerAnalysisTask)
            .where(BloggerAnalysisTask.status.in_(["success", "partial"]))
            .order_by(BloggerAnalysisTask.created_at)
        )
        if limit:
            stmt = stmt.limit(limit)
        rows = (await session.execute(stmt)).scalars().all()

        old_count = 0
        skipped = 0
        updated = []
        for task in rows:
            old_result = task.result or {}
            if not is_old_format(old_result):
                skipped += 1
                continue
            old_count += 1
            new_result = recompute_result(task)
            if dry_run:
                print(
                    f"[dry-run] task={task.id} xhs={task.xhs_user_id} "
                    f"old_dims={_dim_keys(old_result)} new_dims={_dim_keys(new_result)} "
                    f"old_overall={_overall_score(old_result)} "
                    f"new_overall={_overall_score(new_result)}"
                )
                continue
            task.result = new_result
            task.fetched_notes = new_result.get("real_note_count", task.fetched_notes)
            # coverage 列是覆盖率浮点（运行器口径），完整 dict 在 result.coverage
            task.coverage = (new_result.get("coverage") or {}).get("coverage_rate")
            task.confidence = new_result.get("confidence")
            updated.append(task)

        if not dry_run and updated:
            await session.commit()

        if skipped:
            print(f"跳过非旧格式任务：{skipped}")
        return old_count, skipped


def main() -> None:
    parser = argparse.ArgumentParser(
        description="把旧版博主分析结果重算为新的五维格式（不传 --apply 只 dry-run）"
    )
    parser.add_argument("--dry-run", action="store_true", help="只打印预览，不写库（默认）")
    parser.add_argument("--apply", action="store_true", help="真正写库（必须显式传入）")
    parser.add_argument("--limit", type=int, default=None, help="最多检查的任务数")
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit 必须 >= 1")
    dry_run = not args.apply

    _load_env()
    old_count, skipped = asyncio.run(collect_old_tasks(dry_run=dry_run, limit=args.limit))
    action = "dry-run 预览" if dry_run else "已写库"
    print(f"完成：{action}，旧格式 {old_count} 条，跳过非旧格式 {skipped} 条")


if __name__ == "__main__":
    main()
