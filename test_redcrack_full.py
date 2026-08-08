import asyncio, sys
sys.path.insert(0, r"D:\two\RedCrack")
from request.web.xhs_session import create_xhs_session
from loguru import logger

async def show(name, res, n=400):
    text = await res.text()
    logger.success(f"{name} | status={res.status} | {text[:n]}")

async def main():
    xhs_session = await create_xhs_session(proxy="http://127.0.0.1:7890")

    res = await xhs_session.apis.note.get_homefeed(xhs_session.apis.note.homefeed_category_enum.FOOD)
    j = await res.json()
    items = (j.get("data") or {}).get("items") or []
    first = next((it for it in items if it.get("model_type") == "note"), None)
    note_id = first["id"]
    xsec_token = first["xsec_token"]
    logger.info(f"取到第1条笔记 id={note_id} xsec_token={xsec_token}")
    await show("homefeed", res, 160)

    res = await xhs_session.apis.note.note_detail(note_id, xsec_token)
    await show("note_detail", res, 260)

    res = await xhs_session.apis.comments.get_comments(note_id, xsec_token, "")
    await show("comments", res, 260)

    res = await xhs_session.apis.note.search_notes("口红", page=1, page_size=5)
    await show("search_notes", res, 260)

    await xhs_session.close_session()
    logger.success("=== 全部测试完成 ===")

asyncio.run(main())
