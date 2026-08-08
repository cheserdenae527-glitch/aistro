import asyncio, sys
sys.path.insert(0, r"D:\two\RedCrack")
from request.web.xhs_session import create_xhs_session
from loguru import logger

async def main():
    xhs_session = await create_xhs_session(proxy="http://127.0.0.1:7890")
    res = await xhs_session.apis.note.get_homefeed(xhs_session.apis.note.homefeed_category_enum.RECOMMEND)
    j = await res.json()
    items = (j.get("data") or {}).get("items") or []
    first = next((it for it in items if it.get("model_type") == "note"), None)
    user_id = first["note_card"]["user"]["user_id"]
    logger.info(f"作者 user_id={user_id}")
    try:
        res = await xhs_session.apis.note.search_user_notes(user_id, num=5, cursor="")
        logger.success(f"user_posted | status={res.status} | {(await res.text())[:250]}")
    except Exception as e:
        logger.error(f"user_posted 失败: {e}")
    await xhs_session.close_session()

asyncio.run(main())
