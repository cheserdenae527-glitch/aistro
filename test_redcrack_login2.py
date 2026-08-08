import asyncio, sys, json
sys.path.insert(0, r"D:\two\RedCrack")
from request.web.xhs_session import create_xhs_session
from loguru import logger

WEB_SESSION = "040069bb1813811e7c56d4cd43384bf34efae2"
OWN_UID = "6a6c50c90000000013002c00"

async def main():
    xhs_session = await create_xhs_session(proxy="http://127.0.0.1:7890", web_session=WEB_SESSION)

    # 完整搜索响应
    try:
        res = await xhs_session.apis.note.search_notes("口红", page=1, page_size=20)
        full = json.dumps(await res.json(), ensure_ascii=False)
        logger.info(f"search full len={len(full)}")
        print(full[:800])
    except Exception as e:
        logger.error(f"search_notes 失败: {e}")

    # 自己的主页笔记
    try:
        res = await xhs_session.apis.note.search_user_notes(OWN_UID, num=10, cursor="")
        text = await res.text()
        logger.success(f"user_posted(自己) | status={res.status} | {text[:400]}")
    except Exception as e:
        logger.error(f"user_posted 失败: {e}")

    # 登录态 homefeed
    try:
        res = await xhs_session.apis.note.get_homefeed(xhs_session.apis.note.homefeed_category_enum.RECOMMEND)
        j = await res.json()
        n = len((j.get("data") or {}).get("items") or [])
        logger.success(f"homefeed(登录) | code={j.get('code')} items={n}")
    except Exception as e:
        logger.error(f"homefeed 失败: {e}")

    await xhs_session.close_session()

asyncio.run(main())
