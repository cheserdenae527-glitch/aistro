"""
阶段 2：Beav 知识库 → AiRestro note_details 导入 + 互动指标回填（方案 v1.4 §4 阶段 2 / §5）。

行为：
1. 扫描 Beav 落盘目录（默认 C:\\Users\\29842\\.beav\\knowledge\\redbook），读 meta.json + content.md；
2. 跳过非小红书条目（captureKind 不在 xhs-note/xhs-video）；
3. 映射成 XHS note_card 形状 → processor.normalize_note() 归一化；
4. 幂等 upsert 到 note_details（已存在且带 full_stats 的 API 数据不被 Beav 弱数据降级覆盖）；
5. --backfill：对缺失互动指标/发布时间的条目，用现有 XhsCrawler.get_note_detail 回填（走 gate 节流 + 风控不重试）。

用法：
  python scripts/import_beav_knowledge.py                          # 仅导入（不联网）
  python scripts/import_beav_knowledge.py --backfill               # 导入 + 互动指标回填
  python scripts/import_beav_knowledge.py --root <beav知识库目录>
  python scripts/import_beav_knowledge.py --limit 50 --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import io as _io
import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone

# 让 backend/services 可导入（crawler.*）
_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SERVICES = os.path.join(_BACKEND, "services")
for _p in (_BACKEND, _SERVICES):
    if _p not in sys.path:
        sys.path.insert(0, _p)

def _safe_console():
    """Windows GBK 控制台遇到特殊字符（如 \xa0）会崩，强制 UTF-8 输出。"""
    try:
        if sys.stdout and hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


_safe_console()

from crawler.processor import normalize_note  # noqa: E402
from crawler.config import get_cookie  # noqa: E402

_XHS_KINDS = {"xhs-note", "xhs-video"}
_USER_ID_RE = re.compile(r"/user/profile/([^/?#]+)")


# ── Beav meta.json → XHS note_card 形状 ─────────────────────────────

def parse_user_id(author_url: str) -> str:
    m = _USER_ID_RE.search(author_url or "")
    return m.group(1) if m else "unknown"


def parse_xsec_token(source_url: str) -> str:
    try:
        from urllib.parse import urlparse, parse_qs
        return parse_qs(urlparse(source_url or "").query).get("xsec_token", [""])[0]
    except Exception:
        return ""


def read_content_md(note_dir: str) -> str:
    p = os.path.join(note_dir, "content.md")
    try:
        with _io.open(p, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return ""


def beav_meta_to_note(meta: dict, content_md: str) -> dict:
    """把 Beav meta.json 映射为 XHS API note_card 形状（processor.normalize_note 可消费）。"""
    note_id = str(meta.get("externalId") or meta.get("dedupeKey") or "").strip()
    title = str(meta.get("title") or "").strip()
    desc = str(meta.get("description") or content_md or "").strip()
    author = str(meta.get("author") or "").strip()
    author_url = str(meta.get("authorUrl") or "").strip()
    avatar = str(meta.get("authorAvatarUrl") or "") or None
    source_url = str(meta.get("sourceUrl") or meta.get("sourceLink") or "").strip()
    stats = meta.get("stats") or {}
    images = meta.get("images") or []
    video_url = str(meta.get("videoUrl") or "") or None
    created_at = meta.get("createdAt") or ""
    ts_ms = None
    if isinstance(created_at, str) and created_at:
        try:
            ts_ms = int(datetime.fromisoformat(created_at.replace("Z", "+00:00")).timestamp() * 1000)
        except Exception:
            ts_ms = None

    image_list = []
    for img in images:
        image_list.append({"info_list": [{"url": img, "image_scene": "WB_DFT"}]})

    video = None
    if video_url:
        video = {"media": {"stream": {"hd": [{"master_url": video_url, "video_bitrate": 0}]}}}

    note_card = {
        "display_title": title,
        "title": title,
        "desc": desc,
        "type": "video" if str(meta.get("type") or meta.get("captureKind")) == "xhs-video" else "normal",
        "user": {"user_id": parse_user_id(author_url), "nickname": author, "avatar": avatar},
        "interact_info": {
            "liked_count": int(stats.get("likes") or 0),
            "collected_count": int(stats.get("collects") or 0),
            "comment_count": int(stats.get("comments") or 0),
        },
        "image_list": image_list,
        "video": video,
        "time": ts_ms,
    }
    note = {
        "id": note_id,
        "xsec_token": parse_xsec_token(source_url),
        "note_card": note_card,
        # Beav 附加信息保留在 raw 里，detail_json 自包含
        "source_url": source_url,
        "capture_kind": str(meta.get("captureKind") or ""),
        "beav_id": str(meta.get("id") or ""),
        "local_images": images,
        "local_video": str(meta.get("video") or "") or None,
        "beav_created_at": created_at,
        "beav_tags": meta.get("tags") or [],
    }
    return note


def needs_backfill(normalized: dict) -> bool:
    st = normalized.get("stats") or {}
    all_zero = not st.get("liked") and not st.get("collected") and not st.get("comments")
    no_time = normalized.get("published_at") is None
    return all_zero or no_time


# ── DB（asyncpg，幂等 upsert，避免降级覆盖 full_stats 数据）────────

def _db_dsn() -> str:
    return os.environ.get("AISTRO_DATABASE_URL", "postgresql://aistro:aistro@localhost:5432/aistro")


async def _upsert_notes(notes: list[dict]) -> dict:
    """notes: list of {xhs_user_id, platform_note_id, detail_json}"""
    import asyncpg
    conn = await asyncpg.connect(_db_dsn())
    inserted = updated = skipped = 0
    try:
        for n in notes:
            existing = await conn.fetchrow(
                "SELECT detail_json FROM note_details WHERE xhs_user_id=$1 AND platform_note_id=$2",
                n["xhs_user_id"], n["platform_note_id"],
            )
            existing_obj = None
            if existing and existing["detail_json"]:
                try:
                    existing_obj = json.loads(existing["detail_json"]) if isinstance(existing["detail_json"], str) else existing["detail_json"]
                except Exception:
                    existing_obj = None
            if existing_obj and existing_obj.get("full_stats"):
                skipped += 1  # 已有 API 完整数据，不降级
                continue
            payload = json.dumps(n["detail_json"], ensure_ascii=False)
            result = await conn.execute(
                """
                INSERT INTO note_details (id, xhs_user_id, platform_note_id, detail_json, fetched_at)
                VALUES ($1, $2, $3, $4::jsonb, now())
                ON CONFLICT (xhs_user_id, platform_note_id)
                DO UPDATE SET detail_json = EXCLUDED.detail_json, fetched_at = now()
                """,
                uuid.uuid4(), n["xhs_user_id"], n["platform_note_id"], payload,
            )
            if "UPDATE" in result:
                updated += 1
            else:
                inserted += 1
    finally:
        await conn.close()
    return {"inserted": inserted, "updated": updated, "skipped_full_stats": skipped}


async def _fetch_existing_full_stats(conn, note_id: str, user_id: str):
    row = await conn.fetchrow(
        "SELECT detail_json FROM note_details WHERE xhs_user_id=$1 AND platform_note_id=$2",
        user_id, note_id,
    )
    if row and row["detail_json"]:
        try:
            obj = json.loads(row["detail_json"]) if isinstance(row["detail_json"], str) else row["detail_json"]
        except Exception:
            obj = None
        if obj and obj.get("full_stats"):
            return obj
    return None
    return None


# ── 主流程 ─────────────────────────────────────────────────────────

def scan_beav(root: str) -> list[dict]:
    items = []
    if not os.path.isdir(root):
        return items
    for name in sorted(os.listdir(root)):
        d = os.path.join(root, name)
        if not os.path.isdir(d):
            continue
        meta_path = os.path.join(d, "meta.json")
        if not os.path.isfile(meta_path):
            continue
        try:
            with _io.open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
        except Exception:
            continue
        kind = str(meta.get("captureKind") or meta.get("type") or "")
        items.append({"dir": d, "name": name, "meta": meta, "kind": kind, "content_md": read_content_md(d)})
    return items


def main() -> None:
    parser = argparse.ArgumentParser(description="Beav 知识库导入 + 互动指标回填")
    parser.add_argument("--root", default=r"C:\Users\29842\.beav\knowledge\redbook", help="Beav 小红书知识库目录")
    parser.add_argument("--backfill", action="store_true", help="导入后对缺失互动指标的条目调接口回填")
    parser.add_argument("--limit", type=int, default=0, help="最多处理条数（0=全部）")
    parser.add_argument("--dry-run", action="store_true", help="只扫描并打印计划，不写库")
    args = parser.parse_args()

    items = scan_beav(args.root)
    xhs_items = [it for it in items if it["kind"] in _XHS_KINDS]
    skipped_kinds = [it for it in items if it["kind"] not in _XHS_KINDS]
    print(f"扫描目录       : {args.root}")
    print(f"总条目         : {len(items)}（跳过非小红书 {len(skipped_kinds)}：{[it['kind'] for it in skipped_kinds]}）")
    print(f"小红书条目     : {len(xhs_items)}")

    if args.limit:
        xhs_items = xhs_items[: args.limit]

    notes = []
    for it in xhs_items:
        meta = it["meta"]
        note = beav_meta_to_note(meta, it["content_md"])
        normalized = normalize_note(note)
        normalized["beav_imported_at"] = datetime.now(timezone.utc).isoformat()
        normalized["full_stats"] = False
        notes.append({
            "xhs_user_id": (normalized.get("author") or {}).get("id") or "unknown",
            "platform_note_id": normalized["platform_note_id"],
            "detail_json": normalized,
            "_source_url": note.get("source_url", ""),
            "_needs_backfill": needs_backfill(normalized),
        })

    if args.dry_run:
        print("\n[dry-run] 计划导入：")
        for n in notes:
            print(f"  - {n['platform_note_id']}  {n['detail_json'].get('title','')[:40]}  需要回填={n['_needs_backfill']}")
        return

    result = asyncio.run(_upsert_notes(notes))
    print(f"导入完成       : 新增 {result['inserted']} / 更新 {result['updated']} / 跳过已有完整数据 {result['skipped_full_stats']}")

    if args.backfill:
        backfill_notes = [n for n in notes if n["_needs_backfill"]]
        print(f"待回填         : {len(backfill_notes)} 条（likes/收藏/评论全 0 或缺发布时间）")
        cookie = get_cookie()
        if not cookie:
            print("!! 未找到 Cookie（crawler_config.json 或 payload_user.json），跳过回填")
            return
        from crawler.xhs import XhsCrawler
        crawler = XhsCrawler(cookie)
        ok = fail = 0
        failures = []
        for n in backfill_notes:
            url = n["_source_url"]
            if not url:
                fail += 1
                failures.append((n["platform_note_id"], "缺 source_url"))
                continue
            result_crawl = crawler.get_note_detail(url)
            if result_crawl.success and isinstance(result_crawl.data, dict):
                raw = result_crawl.data
                # 与 analysis_task_runner 相同：从详情响应提取笔记对象
                payload = raw.get("data")
                items = []
                if isinstance(payload, dict) and isinstance(payload.get("items"), list):
                    items = [it for it in payload["items"] if isinstance(it, dict)]
                elif raw.get("note_card"):
                    items = [raw]
                if items:
                    full = normalize_note(items[0])
                    full["full_stats"] = True
                    full["beav_imported_at"] = datetime.now(timezone.utc).isoformat()
                    asyncio.run(_upsert_notes([{
                        "xhs_user_id": n["xhs_user_id"],
                        "platform_note_id": n["platform_note_id"],
                        "detail_json": full,
                    }]))
                    ok += 1
                    print(f"  回填成功 {n['platform_note_id']}  {full['title'][:30]}  stats={full['stats']} published={full['published_at']}")
                    continue
            fail += 1
            failures.append((n["platform_note_id"], result_crawl.error or "解析失败"))
            print(f"  回填失败 {n['platform_note_id']}  {result_crawl.error or '解析失败'}")
        print(f"回填完成       : 成功 {ok} / 失败 {fail}")
        if failures:
            print("失败明细（前 10）:")
            for note_id, err in failures[:10]:
                print(f"  - {note_id}: {err}")


if __name__ == "__main__":
    main()
