import asyncio, sys
sys.path.insert(0, r"D:\two\RedCrack")
from request.web.xhs_session import create_xhs_session
from loguru import logger

WEB_SESSION = "040069bb1813811e7c56d4cd43384bf34efae2"

async def show(name, res, n=300):
    text = await res.text()
    logger.success(f"{name} | status={res.status} | {text[:n]}")

async def main():
    xhs_session = await create_xhs_session(proxy="http://127.0.0.1:7890", web_session=WEB_SESSION)

    # 1. 账号信息
    try:
        res = await xhs_session.apis.auth.get_self_simple_info()
        await show("get_self_simple_info", res, 400)
    except Exception as e:
        logger.error(f"get_self_simple_info 失败: {e}")

    # 2. 搜索笔记
    try:
        res = await xhs_session.apis.note.search_notes("口红", page=1, page_size=5)
        await show("search_notes", res, 400)
        j = await res.json()
        items = (j.get("data") or {}).get("items") or []
        if items:
            first = items[0]
            note_id = first.get("id")
            xsec = first.get("xsec_token")
            logger.info(f"搜索结果第1条 note_id={note_id}")
            # 3. 用搜索结果里的笔记测详情+评论
            if note_id and xsec:
                try:
                    res = await xhs_session.apis.note.note_detail(note_id, xsec)
                    await show("note_detail(登录)", res, 200)
                except Exception as e:
                    logger.error(f"note_detail 失败: {e}")
                try:
                    res = await xhs_session.apis.comments.get_comments(note_id, xsec, "")
                    await show("comments(登录)", res, 200)
                except Exception as e:
                    logger.error(f"comments 失败: {e}")
            # 4. 搜索结果的作者 -> 用户主页
            user_card = first.get("user") or {}
            uid = user_card.get("user_id")
            logger.info(f"搜索作者 user_id={uid}")
            if uid:
                try:
                    res = await xhs_session.apis.note.search_user_notes(uid, num=5, cursor="")
                    await show("user_posted", res, 400)
                except Exception as e:
                    logger.error(f"user_posted 失败: {e}")
    except Exception as e:
        logger.error(f"search_notes 失败: {e}")

    await xhs_session.close_session()
    logger.success("=== 登录态测试完成 ===")

asyncio.run(main())
