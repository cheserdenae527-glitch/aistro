import asyncio, sys
sys.path.insert(0, r"D:\two\RedCrack")
from request.web.xhs_session import create_xhs_session
from loguru import logger

async def main():
    xhs_session = await create_xhs_session(proxy="http://127.0.0.1:7890")
    logger.info("cookies: " + str(dict(xhs_session.cookies.items())))
    res = await xhs_session.apis.note.get_homefeed(xhs_session.apis.note.homefeed_category_enum.FOOD)
    logger.success("homefeed status=" + str(res.status))
    print((await res.text())[:500])
    await xhs_session.close_session()

asyncio.run(main())
