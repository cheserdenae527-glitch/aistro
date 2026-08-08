"""小红书设计知识库 — 静态加载、标签检索与提示词上下文拼接。"""
from __future__ import annotations

import json
from pathlib import Path

_KNOWLEDGE_DIR = Path(__file__).resolve().parents[2] / "knowledge" / "xhs"
_DEFAULT_STYLE_ID = "gao_ji"
_cache: dict | None = None


def _read_json(name: str):
    with open(_KNOWLEDGE_DIR / name, encoding="utf-8") as f:
        return json.load(f)


def _load() -> dict:
    global _cache
    if _cache is None:
        _cache = {
            "styles": _read_json("styles.json"),
            "rules": _read_json("rules.json"),
            "templates": _read_json("templates.json"),
            "category_map": _read_json("category_map.json"),
        }
    return _cache


def reset_cache() -> None:
    global _cache
    _cache = None


def _norm(value: str) -> str:
    return (value or "").strip().lower()


def _style_keyword_hits(style: dict, keywords: list[str]) -> int:
    tags = {_norm(t) for t in style.get("style_tags", [])}
    aliases = {_norm(a) for a in style.get("aliases", [])}
    name = _norm(style.get("name", ""))
    hits = 0
    for kw in keywords:
        k = _norm(kw)
        if k == name or k in tags or k in aliases:
            hits += 1
    return hits


def _category_default_ids(category: str | None) -> list[str]:
    if not category:
        return []
    cmap = _load()["category_map"]
    target = _norm(category)
    for key, ids in cmap.items():
        if _norm(key) == target:
            return ids
    return []


def _palette_hit(style: dict, palette_hint: str | None) -> bool:
    if not palette_hint:
        return False
    hint = _norm(palette_hint)
    for p in style.get("color_palettes", []):
        for key in ("primary", "secondary", "accent", "text"):
            if _norm(p.get(key, "")) == hint:
                return True
    return False


def _score_style(
    style: dict,
    category: str | None,
    keywords: list[str],
    palette_hint: str | None,
    defaults: list[str],
) -> tuple[int, int]:
    score = 0
    if style["id"] in defaults:
        score += 3  # 与 category_tags 命中互斥，不叠加
    else:
        cats = {_norm(t) for t in style.get("category_tags", [])}
        if category and _norm(category) in cats:
            score += 2
    score += 2 * _style_keyword_hits(style, keywords)
    if _palette_hit(style, palette_hint):
        score += 1
    default_rank = defaults.index(style["id"]) if style["id"] in defaults else 99
    return score, default_rank


def retrieve(
    category: str | None = None,
    style_keywords: list[str] | None = None,
    palette_hint: str | None = None,
    limit: int = 3,
) -> dict:
    data = _load()
    keywords = [k for k in (style_keywords or []) if k]
    defaults = _category_default_ids(category)
    ranked = sorted(
        (
            (_score_style(s, category, keywords, palette_hint, defaults), s)
            for s in data["styles"]
        ),
        key=lambda x: (-x[0][0], x[0][1]),
    )
    positive = [(sc, s) for sc, s in ranked if sc[0] > 0]
    top = [s for _, s in positive[:limit]]
    if not top:
        fallback_ids = defaults or _load()["category_map"].get("默认") or [_DEFAULT_STYLE_ID]
        by_id = {s["id"]: s for s in data["styles"]}
        top = [by_id[sid] for sid in fallback_ids[:limit] if sid in by_id]
    templates = data["templates"]
    return {
        "styles": [
            {
                "id": s["id"],
                "name": s["name"],
                "description": s["description"],
                "color_palettes": s["color_palettes"],
                "avatar_rules": s["avatar_rules"],
                "bg_rules": s["bg_rules"],
                "avoid": s["avoid"],
            }
            for s in top
        ],
        "templates": {
            s["id"]: templates[s["id"]] for s in top if s["id"] in templates
        },
        "rules": data["rules"],
        "category": category or "",
    }


def build_knowledge_context(
    category: str | None = None,
    style_keywords: list[str] | None = None,
    section: str | None = None,
    palette_hint: str | None = None,
    limit: int = 3,
) -> str:
    payload = retrieve(category, style_keywords, palette_hint, limit)
    lines: list[str] = []
    if payload["styles"]:
        lines.append("【设计风格库】")
        for s in payload["styles"]:
            palette = "；".join(
                f"主{p['primary']}辅{p['secondary']}点{p['accent']}文{p['text']}"
                for p in s["color_palettes"]
            )
            lines.append(
                f"- {s['name']}：{s['description']} 配色：{palette} "
                f"头像要点：{s['avatar_rules']} 背景要点：{s['bg_rules']} 避坑：{s['avoid']}"
            )
    if payload["templates"]:
        lines.append("【提示词模板】")
        for s in payload["styles"]:
            tpl = payload["templates"].get(s["id"])
            if not tpl:
                continue
            if section != "bg":
                lines.append(f"- {s['name']} 头像模板：{tpl.get('avatar_template', '')}")
            if section != "avatar":
                lines.append(f"- {s['name']} 背景模板：{tpl.get('bg_template', '')}")
    if payload["rules"]:
        lines.append("【通用设计规则】")
        lines.extend(f"- {r['rule']}" for r in payload["rules"])
    return "\n".join(lines)


def _fill_template(template: str, category: str, style_name: str, palette: dict) -> str:
    palette_text = " ".join(
        str(palette.get(k, "")) for k in ("primary", "secondary", "accent", "text")
    ).strip() or "暖色系"
    return (
        template.replace("{category}", category or "餐饮门店")
        .replace("{style}", style_name or "设计")
        .replace("{palette}", palette_text)
        .replace("{subject}", "门店招牌")
    )


def enrich_clone_schemes(result: dict) -> dict:
    """复刻方案校准：配色对齐知识风格、补齐缺失提示词并附上命中的知识风格。"""
    keywords = result.get("style_keywords") or []
    used_styles: list[str] = []
    for scheme in result.get("schemes") or []:
        cs = scheme.get("color_scheme") or {}
        payload = retrieve(
            category=result.get("category"),
            style_keywords=keywords,
            palette_hint=cs.get("primary"),
            limit=1,
        )
        if not payload["styles"]:
            continue
        style = payload["styles"][0]
        tpl = payload["templates"].get(style["id"])
        if not tpl:
            continue
        if style["name"] not in used_styles:
            used_styles.append(style["name"])
        palette = (style.get("color_palettes") or [{}])[0]
        scheme["color_scheme"] = {
            "primary": palette.get("primary", cs.get("primary", "")),
            "secondary": palette.get("secondary", cs.get("secondary", "")),
            "accent": palette.get("accent", cs.get("accent", "")),
            "text": palette.get("text", cs.get("text", "")),
        }
        cs = scheme["color_scheme"]
        if not scheme.get("avatar_prompt") and tpl.get("avatar_template"):
            scheme["avatar_prompt"] = _fill_template(
                tpl["avatar_template"], result.get("category"), style["name"], cs
            )
        if not scheme.get("bg_prompt") and tpl.get("bg_template"):
            scheme["bg_prompt"] = _fill_template(
                tpl["bg_template"], result.get("category"), style["name"], cs
            )
    result["knowledge_styles"] = used_styles
    return result
