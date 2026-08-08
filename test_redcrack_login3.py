import asyncio, sys, json
sys.path.insert(0, r"D:\two\RedCrack")
from request.web.xhs_session import create_xhs_session
from loguru import logger

WEB_SESSION = "040069bb1813811e7c56d4cd43384bf34efae2"
URL = "https://edith.xiaohongshu.com/api/sns/web/v1/user_posted"

async def main():
    xhs_session = await create_xhs_session(proxy="http://127.0.0.1:7890", web_session=WEB_SESSION)

    # homefeed 取作者 + xsec_token
    res = await xhs_session.apis.note.get_homefeed(xhs_session.apis.note.homefeed_category_enum.RECOMMEND)
    j = await res.json()
    items = (j.get("data") or {}).get("items") or []
    first = next((it for it in items if it.get("model_type") == "note"), None)
    u = first["note_card"]["user"]
    uid, uxsec = u["user_id"], u.get("xsec_token")
    logger.info(f"作者 user_id={uid} xsec_token={uxsec}")

    # 不带 xsec_token（走仓库现成方法）
    try:
        res = await xhs_session.apis.note.search_user_notes(uid, num=5, cursor="")
        logger.success(f"user_posted(无xsec) | {(await res.text())[:200]}")
    except Exception as e:
        logger.error(f"user_posted(无xsec) 失败: {e}")

    # 带 xsec_token（手动构造 params）
    try:
        params = {
            "num": 5, "cursor": "",
            "user_id": uid,
            "image_formats": "jpg,webp,avif",
            "xsec_token": uxsec,
            "xsec_source": "pc_feed",
        }
        res = await xhs_session.request("get", url=URL, params=params)
        text = await res.text()
        logger.success(f"user_posted(带xsec) | status={res.status} | {text[:300]}")
    except Exception as e:
        logger.error(f"user_posted(带xsec) 失败: {e}")

    await xhs_session.close_session()

asyncio.run(main())
