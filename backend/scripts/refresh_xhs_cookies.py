"""用 RedCrack 自动刷新小红书 Cookie 链（参考 019fdeec-cd04-79f1-82c1-2e5f731439ec 的爬虫机制）。

用法：
  python scripts/refresh_xhs_cookies.py                       # 游客模式刷新
  python scripts/refresh_xhs_cookies.py --web-session <值>    # 登录态刷新（需要真实 web_session）

说明：
- 依赖 D:/two/RedCrack（已克隆）与本地代理（默认 http://127.0.0.1:7890）
- 生成 a1 / webId / websectiga / gid / web_session / acw_tc 等完整 Cookie 链
- 写入 crawler_config.json 与 payload_user.json，供 Spider_XHS 运行时使用
- 游客模式只能访问信息流/详情/评论；搜索与用户主页需要登录态（传 --web-session）
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = PROJECT
REDCRACK = os.path.join(PROJECT, "RedCrack")
CONFIG = os.path.join(PROJECT, "backend", "services", "crawler", "xhs", "scripts", "crawler_config.json")
PAYLOAD = os.path.join(PROJECT, "backend", "services", "crawler", "xhs", "scripts", "payload_user.json")


def _build_cookie_header(cookies: dict) -> str:
    return "; ".join(f"{k}={v}" for k, v in cookies.items() if v is not None)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--web-session", default=None, help="真实登录 web_session；缺省为游客模式")
    parser.add_argument("--proxy", default="http://127.0.0.1:7890", help="代理地址")
    args = parser.parse_args()

    old_cwd = os.getcwd()
    try:
        os.chdir(REDCRACK)
        sys.path.insert(0, REDCRACK)
        from request.web.xhs_session import create_xhs_session

        session = await create_xhs_session(web_session=args.web_session, proxy=args.proxy)
        cookies = session.cookies
        header = _build_cookie_header(cookies)
        await session.close_session()
    finally:
        os.chdir(old_cwd)

    if not header:
        raise SystemExit("未生成任何 Cookie")

    cfg = json.loads(open(CONFIG, encoding="utf-8").read())
    cfg["cookies"] = header
    with open(CONFIG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    with open(PAYLOAD, "w", encoding="utf-8") as f:
        json.dump({"cookies_str": header}, f, ensure_ascii=False, indent=2)

    print("Cookie 已刷新，字段数:", len(cookies))
    print("摘要:", "; ".join(f"{k}=***" for k in cookies))


if __name__ == "__main__":
    asyncio.run(main())
