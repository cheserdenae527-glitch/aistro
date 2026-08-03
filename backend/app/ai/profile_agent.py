"""Profile AI Agent — 调用 DeepSeek LLM 生成 4 套装修方案，含敏感词后处理。"""
from __future__ import annotations

import json
import re as std_re

from openai import AsyncOpenAI
from pydantic import ValidationError

from app.core.config import settings
from app.core.sensitive_filter import contains_blocked, filter_text
from app.schemas.profile import AiVariant, VariantColorScheme

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_BASE_URL,
        )
    return _client


_SYSTEM_PROMPT = """你是一个小红书主页装修设计师，同时也是主页体检师。设计前先过一遍体检标准：用户点进主页后，3 秒内能否看懂“你是谁、帮谁、解决什么、为什么可信、下一步做什么”。为一家餐饮门店设计 4 套完整的 Profile 装修方案。

主页体检标准：
1. 第一眼清晰度：昵称、简介一眼说明账号做什么
2. 目标用户：写清楚服务谁
3. 具体结果：讲清能帮用户解决什么
4. 信任材料：用经验、做法、边界建立可信，不编造背书
5. 转化动作：用户知道下一步是关注、评论、私信还是看置顶
6. 语气一致性：昵称、简介、头像/背景描述和配色统一
7. 视觉表达：配色协调、头像和背景图符合门店定位

要求：
1. 4 套方案风格差异明显（暖调/冷调/高级感/亲和感），id 分别为 A/B/C/D
2. 昵称：具体、有辨识度，第一眼就说明“卖什么或帮谁”，避免抽象词、堆叠词、夸张承诺；<= 20 字符（不允许 emoji），每套方案提供 3 个变体，字段名 nickname_options
3. 简介：短、具体、可判断，优先包含“我是谁/做什么、帮哪类人、解决什么问题、通过什么方式、下一步动作”，避免抽象价值观堆叠、过度承诺、无信息量自夸、只写情绪、同时服务太多人；<= 100 字符（允许 emoji 排版），真实有吸引力
4. 色系优先从下方预设中选取（匹配品类和风格）
   1. 暖冬橘: #E8793A / #FFF3EC / #D4520A / #2D1A0A (火锅/中式正餐)
   2. 森系绿: #4A8C5C / #F0F7F1 / #2D6A3F / #1A2D1F (轻食/沙拉/素食)
   3. 莫兰迪: #9B8E8A / #F5F2F0 / #7A6E6A / #3A3330 (甜品/咖啡)
   4. 日系奶油: #E8C37A / #FFFBF0 / #C49A3C / #4A3A1A (烘焙/面包/Brunch)
   5. 高级灰: #6B6B6B / #F7F7F7 / #4A4A4A / #1A1A1A (高端餐饮/西餐)
   6. 江湖红: #C93828 / #FFF0EE / #A82015 / #2A0A08 (川菜/湘菜/江湖菜)
   7. 清凉蓝: #5B8FB8 / #F0F6FA / #3D6D8E / #1A2A38 (日料/海鲜)
   8. 深夜紫: #7B5EA7 / #F5F0FA / #5E3F89 / #201838 (酒吧/居酒屋)
   如果确实没有匹配预设，再自创。字段名 color_scheme，内含 primary/secondary/accent/text/preset_name
5. avatar_prompt 用中文写图像生成提示词，描述适合该门店的头像 logo，包含主体、风格、配色、构图，方形构图，视觉气质必须和昵称、简介、配色一致。严禁写 --ar 参数
6. bg_prompt 用中文写图像生成提示词，描述符合该门店氛围的背景图，包含主体、风格、配色、构图，宽幅构图，视觉气质必须和昵称、简介、配色一致。严禁写 --ar 参数

输出纯 JSON（无代码块标记），字段名完全按以下格式：

{"variants":[{"id":"A","color_scheme":{"primary":"#xxx","secondary":"#xxx","accent":"#xxx","text":"#xxx","preset_name":"江湖红"},"nickname_options":["a","b","c"],"bio":"...","avatar_prompt":"...","bg_prompt":"..."}]}"""

_SECTION_PROMPT_SYSTEM = """你是一个平台账号装修设计师。只输出一条中文生图提示词正文。

要求：
1. 头像提示词：适合餐饮门店的 Logo / 头像图，包含主体、风格、配色、构图，方形构图，视觉气质与门店定位、昵称简介一致
2. 背景图提示词：适合餐饮门店主页的氛围背景图，包含主体、风格、配色、构图，宽幅构图，视觉气质与门店定位、昵称简介一致
3. 提示词必须完整、可直接交给生图模型使用，100-200 字
4. 严禁写 --ar 参数，严禁输出 JSON、编号、解释或 markdown
"""

_HEALTH_SYSTEM_PROMPT = """你是小红书主页体检师。判断用户点进主页后，能否在 3 秒内看懂：你是谁、帮谁、解决什么、为什么可信、下一步做什么。

体检维度：
1. 第一眼清晰度：昵称、简介是否马上说明账号做什么
2. 目标用户：是否写清楚服务谁
3. 具体结果：是否讲清能帮用户解决什么
4. 信任材料：经验、作品、方法、边界，但绝不编造背书
5. 转化动作：用户是否知道下一步该关注、评论、私信还是看置顶
6. 语气一致性：昵称、简介、头像/背景描述和配色是否统一
7. 视觉表达：配色是否协调、头像和背景图描述是否符合定位

简介原则：短、具体、可判断，优先包含我是谁/做什么、帮哪类人、解决什么问题、通过什么方式、下一步动作。避免抽象价值观堆叠、过度承诺、无信息量自夸、只写情绪、同时服务太多人。

要求：
- 只基于用户提供的信息判断，不编造粉丝量、转化率、用户画像、案例或背书
- 不承诺涨粉、成交、爆款或平台算法结果
- 输出纯 JSON（无代码块标记）：{"first_impression":"一句话第一眼判断","strengths":["优点1","优点2"],"weaknesses":["不足1","不足2"],"suggestions":["建议1","建议2"]}
- strengths、weaknesses、suggestions 各 2-4 条，每条不超过 50 字
"""

_JSON_FENCE_RE = std_re.compile(r"```(?:json)?\s*|\s*```")


async def generate_variants(
    category: str, style: str, price_range: str
) -> tuple[list[AiVariant], str]:
    client = _get_client()
    user_msg = (
        f"门店信息：\n- 品类：{category}\n- 风格关键词：{style}\n- 人均价格：{price_range}"
    )

    response = await client.chat.completions.create(
        model=settings.DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.8,
        max_tokens=3000,
    )

    raw = response.choices[0].message.content or "{}"
    clean = _JSON_FENCE_RE.sub("", raw).strip()

    try:
        data = json.loads(clean)
    except json.JSONDecodeError:
        match = std_re.search(r"\{[\s\S]*\}", clean)
        if match:
            try:
                data = json.loads(match.group(0))
            except json.JSONDecodeError:
                data = {}
        else:
            data = {}

    raw_variants = data.get("variants") or data.get("schemes") or []
    variants = _sanitize_variants(raw_variants)

    return variants, raw


def _sanitize_variants(raw_variants: list) -> list[AiVariant]:
    """把 LLM 原始输出清洗为可入库的 AiVariant 列表。

    规则（SPEC-PROFILE 7.8）：
    - nickname_options 剔除敏感词；若全部被剔除，variant 标记 filtered=True
    - bio 命中敏感词时替换为占位符并标记 bio_flagged=True
    - 不足 4 套时补空 variant（filtered=True），保证前端卡片数量稳定
    """
    variants: list[AiVariant] = []

    for v in raw_variants[:4]:
        if not isinstance(v, dict):
            continue
        vid = v.get("id", chr(65 + len(variants)))
        nickname_options = [
            n
            for n in (v.get("nickname_options") or v.get("nickname_variants") or [])
            if not contains_blocked(n)
        ]
        bio_raw = v.get("bio", "")
        bio_clean, bio_flagged = filter_text(bio_raw)
        variant_filtered = not nickname_options

        try:
            cs = v.get("color_scheme") or v.get("colors") or {}
            color_scheme = VariantColorScheme(
                primary=cs.get("primary", "#6B6B6B"),
                secondary=cs.get("secondary", "#F7F7F7"),
                accent=cs.get("accent", "#4A4A4A"),
                text=cs.get("text", "#1A1A1A"),
                preset_name=cs.get("preset_name"),
            )
        except ValidationError:
            color_scheme = VariantColorScheme(
                primary="#6B6B6B", secondary="#F7F7F7", accent="#4A4A4A", text="#1A1A1A",
            )

        variants.append(AiVariant(
            id=str(vid),
            color_scheme=color_scheme,
            nickname_options=nickname_options,
            bio=bio_clean,
            avatar_prompt=v.get("avatar_prompt", ""),
            bg_prompt=v.get("bg_prompt", ""),
            filtered=variant_filtered,
            bio_flagged=bio_flagged,
        ))

    while len(variants) < 4:
        variants.append(AiVariant(
            id=chr(65 + len(variants)),
            color_scheme=VariantColorScheme(
                primary="#6B6B6B", secondary="#F7F7F7", accent="#4A4A4A", text="#1A1A1A",
            ),
            nickname_options=[], bio="", avatar_prompt="", bg_prompt="", filtered=True,
        ))

    return variants


async def generate_section_prompt(
    section: str, category: str, style: str, price_range: str
) -> str:
    """生成单条提示词（头像或背景图），不触发生图。"""
    section_label = "头像" if section == "avatar" else "背景图"
    user_msg = (
        f"生成一条「{section_label}」生图提示词。\n"
        f"门店信息：\n- 品类：{category}\n- 风格关键词：{style}\n- 人均价格：{price_range}"
    )

    response = await _get_client().chat.completions.create(
        model=settings.DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": _SECTION_PROMPT_SYSTEM},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.9,
        max_tokens=500,
    )

    raw = response.choices[0].message.content or ""
    clean = _JSON_FENCE_RE.sub("", raw).strip()
    clean = std_re.sub(r"^(头像|背景图)?[：:]\s*", "", clean)
    return clean[:1000]


async def run_profile_health_check(
    nickname: str,
    bio: str,
    avatar_prompt: str,
    bg_prompt: str,
    color_primary: str | None,
    color_secondary: str | None,
    color_accent: str | None,
    color_text: str | None,
    has_avatar: bool,
    has_bg: bool,
) -> dict:
    """按主页体检 7 维度分析当前预览内容，返回优点/不足/建议。"""
    user_msg = f"""当前主页预览内容：
- 昵称：{nickname or "（空）"}
- 简介：{bio or "（空）"}
- 头像图片：{"已设置" if has_avatar else "未设置"}
- 背景图片：{"已设置" if has_bg else "未设置"}
- 头像生图提示词：{avatar_prompt or "（空）"}
- 背景图提示词：{bg_prompt or "（空）"}
- 主色：{color_primary or "（空）"}
- 辅色：{color_secondary or "（空）"}
- 点缀色：{color_accent or "（空）"}
- 文字色：{color_text or "（空）"}"""

    response = await _get_client().chat.completions.create(
        model=settings.DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": _HEALTH_SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.5,
        max_tokens=900,
    )

    raw = response.choices[0].message.content or "{}"
    clean = _JSON_FENCE_RE.sub("", raw).strip()
    try:
        data = json.loads(clean)
    except json.JSONDecodeError:
        match = std_re.search(r"\{[\s\S]*\}", clean)
        if match:
            try:
                data = json.loads(match.group(0))
            except json.JSONDecodeError:
                data = {}
        else:
            data = {}

    def _clean_list(key: str) -> list[str]:
        items = data.get(key) or []
        if not isinstance(items, list):
            return []
        return [str(i).strip()[:80] for i in items if str(i).strip()][:4]

    return {
        "first_impression": str(data.get("first_impression") or "").strip()[:200],
        "strengths": _clean_list("strengths"),
        "weaknesses": _clean_list("weaknesses"),
        "suggestions": _clean_list("suggestions"),
    }
