"""内容工坊渲染服务 — HTML 模板参数化 + Playwright 截图 1080x1440 PNG。

模板基于 skills/guizang-social-card-skill 的 Editorial / Swiss 视觉系统，
抽取出可参数化的单页模板（每页一个 .poster.xhs，1080x1440）。
"""
from __future__ import annotations

from pathlib import Path
from string import Template

from app.services.studio_themes import theme_css

TEMPLATE_DIR = Path(__file__).resolve().parents[2] / "assets" / "studio"

XHS_WIDTH = 1080
XHS_HEIGHT = 1440


def _load_template(name: str) -> Template:
    path = TEMPLATE_DIR / name
    return Template(path.read_text(encoding="utf-8"))


_EDITORIAL_TEMPLATE = _load_template("editorial_template.html")
_SWISS_TEMPLATE = _load_template("swiss_template.html")


def _escape(text: str) -> str:
    """HTML 转义，避免文案中的 < > & 破坏结构。"""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _kicker_html(template: str, is_cover: bool, category: str, shop_name: str, page_num: int) -> str:
    cat = _escape(category)
    shop = _escape(shop_name)
    if template == "swiss":
        if is_cover:
            return (
                '<div class="mono-top"><span class="sq"></span>'
                f"<span>{cat} / {shop}</span><span class=\"line\"></span></div>"
            )
        return (
            '<div class="mono-top"><span class="sq"></span>'
            f"<span>N°{page_num:02d}</span><span class=\"line\"></span>"
            f"<span>{shop}</span></div>"
        )
    if is_cover:
        return f'<div class="kicker"><span>{cat}</span><span class="rule"></span><span>{shop}</span></div>'
    return (
        f'<div class="kicker"><span>第 {page_num:02d} 页</span>'
        f'<span class="rule"></span><span>{shop}</span></div>'
    )


def _title_html(template: str, is_cover: bool, title: str) -> str:
    safe = _escape(title)
    if template == "swiss":
        cls = "swiss-cover-title" if is_cover else "swiss-page-title"
        return f'<h1 class="{cls}">{safe}</h1>'
    cls = "cover-title" if is_cover else "page-title"
    return f'<h1 class="{cls}">{safe}</h1>'


def _lead_html(template: str, is_cover: bool, topic: str) -> str:
    if not is_cover or not topic:
        return ""
    safe = _escape(topic)
    cls = "cover-lead" if template == "editorial" else "swiss-cover-lead"
    return f'<p class="{cls}">{safe}</p>'


def _image_html(template: str, is_cover: bool, url: str | None, note: str | None = None) -> str:
    if not url:
        return ""
    if template == "swiss":
        cls = "swiss-image" if is_cover else "swiss-content-image"
    else:
        cls = "image-frame" if is_cover else "content-image"
    note_html = ""
    if is_cover and note:
        note_html = f'<span class="img-note">{_escape(note)}</span>'
    return f'<div class="{cls}"><img src="{url}" alt="">{note_html}</div>'


def _list_html(template: str, is_cover: bool, bullets: list[str]) -> str:
    """要点列表（不含页脚）。"""
    if template == "swiss":
        if is_cover:
            chips = "".join(
                f'<span class="chip">{_escape(b)}</span>' for b in bullets
            )
            return f'<div class="swiss-bullets">{chips}</div>'
        lis = "".join(
            f'<li><span class="idx">{i + 1:02d}</span><span class="txt">{_escape(b)}</span></li>'
            for i, b in enumerate(bullets)
        )
        return f'<ul class="swiss-list">{lis}</ul>'
    if is_cover:
        chips = "".join(f'<span class="chip">{_escape(b)}</span>' for b in bullets)
        return f'<div class="bullets">{chips}</div>'
    lis = "".join(
        f'<li><span class="num">{i + 1}</span><span class="txt">{_escape(b)}</span></li>'
        for i, b in enumerate(bullets)
    )
    return f'<ul class="content-bullets">{lis}</ul>'


def _foot_html(template: str, is_cover: bool, shop_name: str, page_num: int, page_total: int) -> str:
    """页脚（封面为底部面板容器，内容页为页脚条）。"""
    shop = _escape(shop_name)
    page = f"{page_num:02d} / {page_total:02d}"
    if template == "swiss":
        if is_cover:
            return (
                '<div class="swiss-cover-panel">'
                f'<div class="swiss-foot"><span class="brand">{shop}</span><span>{page}</span></div>'
                "</div>"
            )
        return (
            f'<div class="swiss-content-foot"><span class="brand">{shop}</span>'
            f"<span>{page}</span></div>"
        )
    if is_cover:
        return (
            '<div class="cover-panel">'
            f'<div class="foot"><span class="brand">{shop}</span><span>{page}</span></div>'
            "</div>"
        )
    return (
        f'<div class="content-foot"><span class="brand">{shop}</span>'
        f"<span>{page}</span></div>"
    )


def build_page_html(
    *,
    template: str,
    theme: str,
    title: str,
    bullets: list[str],
    image_url: str | None,
    shop_name: str,
    category: str,
    topic: str,
    page_num: int,
    page_total: int,
    is_cover: bool,
) -> str:
    """构建单页卡组 HTML。

    封面：kicker → title → lead → image → 要点面板(含页脚)
    内容页：kicker → title → 要点列表 → image → 页脚条
    """
    tpl = _SWISS_TEMPLATE if template == "swiss" else _EDITORIAL_TEMPLATE
    if is_cover:
        body = (
            _kicker_html(template, True, category, shop_name, page_num)
            + _title_html(template, True, title)
            + _lead_html(template, True, topic)
            + _image_html(template, True, image_url)
            + f'<div class="{"swiss-" if template == "swiss" else ""}cover-panel">'
            + _list_html(template, True, bullets)
            + _foot_html(template, True, shop_name, page_num, page_total)
            + "</div>"
        )
    else:
        body = (
            _kicker_html(template, False, category, shop_name, page_num)
            + '<div class="content-row">'
            + '<div class="text-col">'
            + _title_html(template, False, title)
            + _list_html(template, False, bullets)
            + "</div>"
            + '<div class="img-col">'
            + _image_html(template, False, image_url)
            + "</div>"
            + "</div>"
            + _foot_html(template, False, shop_name, page_num, page_total)
        )
    return tpl.substitute(
        theme_css=theme_css(template, theme),
        kicker_html="",
        title_html="",
        lead_html="",
        image_html="",
        bullets_html=body,
    )


def render_pages(htmls: list[str]) -> list[dict]:
    """用 Playwright 渲染多页 HTML，返回 [{png, metrics}]。

    metrics: {client_height, scroll_height, overflow, bottom_gap}
    """
    from playwright.sync_api import sync_playwright

    results: list[dict] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(
            args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"]
        )
        ctx = browser.new_context(
            viewport={"width": XHS_WIDTH, "height": XHS_HEIGHT},
            device_scale_factor=1,
        )
        try:
            for html in htmls:
                page = ctx.new_page()
                try:
                    page.set_content(html, wait_until="networkidle", timeout=15000)
                except Exception:
                    # 网络受限时（如字体 CDN 不可达）降级为 load + 短等待
                    page.set_content(html, wait_until="load", timeout=15000)
                    page.wait_for_timeout(600)
                metrics = page.evaluate(
                    """() => {
                        const poster = document.querySelector('.poster');
                        const foot = document.querySelector('.foot, .swiss-foot, .content-foot, .swiss-content-foot');
                        const er = poster.getBoundingClientRect();
                        const fr = foot.getBoundingClientRect();
                        return {
                            client_height: poster.clientHeight,
                            scroll_height: poster.scrollHeight,
                            overflow: poster.scrollHeight - poster.clientHeight,
                            bottom_gap: Math.max(0, Math.round(er.bottom - fr.bottom)),
                        };
                    }"""
                )
                png = page.screenshot()
                page.close()
                results.append({"png": png, "metrics": metrics})
        finally:
            ctx.close()
            browser.close()
    return results

