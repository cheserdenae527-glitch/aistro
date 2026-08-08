"""导入导出的笔记 CSV 到 note_details 缓存（不抓取、不补粉丝）。

用法：
  python scripts/import_notes_csv.py --input "D:/WORK/29842/Documents/小红书笔记 (1).csv"
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "services"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from app.core.database import async_session_factory
from app.services.analysis_task_runner import _upsert_detail
from calibrate_from_csv import read_rows, normalize_row


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="小红书笔记 CSV 路径")
    args = parser.parse_args()

    rows = read_rows(args.input)
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
    print(f"导入 note_details：{count} 篇")


if __name__ == "__main__":
    asyncio.run(main())
