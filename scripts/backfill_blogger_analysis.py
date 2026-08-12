"""一次性回填脚本：把旧版博主分析结果（旧四维）重算为新的五维格式。

背景：blogger_analysis_tasks 里部分 success/partial 行是重构前生成的，
result.dimensions 是旧四维（trend/content_stability/interaction_quality/
sustained_operation），stage 为 null，新前端按 dimensions.seeding_depth 等
展示会空白。本脚本用新引擎 score_blogger 对旧 result 里已有的真实数据
（notes/coverage/sampled/follower_history）重算，得到新五维结果并落库。

用法（在仓库根目录）：
    python scripts/backfill_blogger_analysis.py            # 仅 dry-run 预览
    python scripts/backfill_blogger_analysis.py --apply    # 真正写库（必须显式）
    python scripts/backfill_blogger_analysis.py --limit 5  # 只看前 5 条

安全：不传 --apply 绝不写库，只打印 [dry-run] 行；逐任务异常隔离，单行失败
不影响其余行，重跑幂等（format_version 标记 + 新 decision 结构识别新格式）。
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

# 新五维结果顶层格式版本标记：重算时写入，重跑时据此幂等识别。
FORMAT_VERSION = "v2_seeding"


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


def _is_new_format(result: dict) -> bool:
    """新五维格式判定：format_version 标记 / seeding_depth 维度 / 新 decision。

    注意：旧四维结果的 decision 也可能含 recommendation（旧结构只有
    grass_level/growth_level/quadrant/recommendation/status），因此不能只凭
    recommendation 判断；新 decision 一定带 low_quality（所有分支都有）。
    转换后数据不足的行 dimensions 为空 dict，但带新 decision / format_version，
    靠后两者识别，保证脚本重跑幂等。
    """
    if not isinstance(result, dict):
        return False
    if result.get("format_version") == FORMAT_VERSION:
        return True
    dimensions = result.get("dimensions")
    has_new_dims = isinstance(dimensions, dict) and "seeding_depth" in dimensions
    decision = result.get("decision")
    has_new_decision = isinstance(decision, dict) and "low_quality" in decision
    return has_new_dims or has_new_decision


def is_old_format(result: dict) -> bool:
    """旧格式（可回填）判定：不是新格式即可转换。"""
    return not _is_new_format(result)


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
    # 显式格式版本标记：重跑幂等不依赖隐式的 low_quality 约定。
    new_result["format_version"] = FORMAT_VERSION
    return new_result


def _dim_keys(result: dict) -> list[str]:
    dimensions = result.get("dimensions")
    if not isinstance(dimensions, dict):
        return []
    return sorted(dimensions.keys())


def _overall_score(result: dict):
    overall = result.get("overall") or {}
    return overall.get("score")


def _process_one(task, dry_run: bool) -> str:
    """处理单个任务，返回状态标签：dry_run / updated / skipped_new / skipped_bad / error。

    异常隔离：recompute_result 抛错时只打印日志并返回 "error"，不向调用方
    抛出，保证循环继续（重跑幂等，后续 --apply 重试即可）。
    """
    old_result = task.result
    if not isinstance(old_result, dict):
        print(f"[skip] task={task.id} xhs={task.xhs_user_id} result 非 dict，跳过")
        return "skipped_bad"
    if not is_old_format(old_result):
        return "skipped_new"
    try:
        new_result = recompute_result(task)
    except Exception as exc:  # noqa: BLE001
        print(f"[error] task={task.id} xhs={task.xhs_user_id} 重算失败: {exc}")
        return "error"
    if dry_run:
        print(
            f"[dry-run] task={task.id} xhs={task.xhs_user_id} "
            f"old_dims={_dim_keys(old_result)} new_dims={_dim_keys(new_result)} "
            f"old_overall={_overall_score(old_result)} "
            f"new_overall={_overall_score(new_result)}"
        )
        return "dry_run"
    task.result = new_result
    task.fetched_notes = new_result.get("real_note_count", task.fetched_notes)
    # coverage 列是覆盖率浮点（运行器口径），完整 dict 在 result.coverage
    task.coverage = (new_result.get("coverage") or {}).get("coverage_rate")
    task.confidence = new_result.get("confidence")
    return "updated"


def _apply_to_tasks(tasks, dry_run: bool) -> tuple[int, int, list]:
    """纯循环助手：逐任务处理，返回 (旧格式数, 跳过非旧格式数, 待提交列表)。

    error 行计入旧格式数（确实需要重试），但不进待提交列表。
    """
    old_count = 0
    skipped = 0
    updated = []
    for task in tasks:
        status = _process_one(task, dry_run)
        if status in ("skipped_new", "skipped_bad"):
            skipped += 1
        else:
            old_count += 1
            if status == "updated":
                updated.append(task)
    return old_count, skipped, updated


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

        old_count, skipped, updated = _apply_to_tasks(rows, dry_run)
        if not dry_run and updated:
            await session.commit()

        if skipped:
            print(f"跳过非旧格式任务：{skipped}")
        return old_count, skipped


def main() -> None:
    parser = argparse.ArgumentParser(
        description="把旧版博主分析结果重算为新的五维格式（默认只 dry-run，--apply 才写库）"
    )
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
