# 实施计划：性价比 + 受众画像增量 —— Task 2/3 详细设计（伪代码 + 测试用例矩阵）

> 对应设计：`docs/superpowers/specs/2026-08-12-blogger-cost-audience-analysis-design.md` v1.8
> 本文件仅细化改动最重、分支最多的两个任务；其余 Task 待评审通过后按 §11 拆解补齐
> 状态：供评审（重点确认两个标注点：①图文/视频报价合并规则；②tier_key 分层映射）

---

## 0. 公共约定

### 0.1 tier_key 分层映射
配置里的绝对阈值/赞藏区间/商单密度阈值按更细的 key 分层（T1 再按 <5k/≥5k 拆）：
```
def _tier_key(fans: int) -> str:
    if fans < 5000:   return "T1_lt5k"
    if fans < 10000:  return "T1_ge5k"
    if fans < 100000: return "T2"
    if fans < 1000000:return "T3"
    return "T4"
```
> 与现有 `_tier_for`（返回 T1-T4，用于互动率基准/报价锚点）并存：`_tier_key` 专用于 §3.2 绝对门槛与 §4.2 分层区间/商单密度；`_tier_for` 用于 min_healthy/read_rate/price_anchor。

### 0.2 配置读取
`cfg = load_scoring_config()`；新增段 `authenticity` / `cost` / `absolute_thresholds`，均已在设计 §9 定义。

---

## Task 2：真实性闸门 `_authenticity_gate`

### 2.1 签名与返回
```python
def _authenticity_gate(
    notes: list[dict],              # 真实样本（与五维同一批，近90天）
    follower_count: int,
    comment_analysis: dict | None,  # with_comments 时才有
    pgy_meta: dict | None,          # {"business_note_count": int, "total_notes": int, ...}
    cfg: dict,                      # load_scoring_config()
) -> dict:
    """多维信号打分制真实性闸门。"""
    return {
        "passed": bool,
        "score": int,               # 累计权重分（0-100 内）
        "direct_fail": bool,        # 强信号（fake_ratio）命中
        "hits": [{"id": str, "weight": int, "detail": str}, ...],  # 命中的子信号，供 UI/人工复核
    }
```

### 2.2 伪代码
```python
def _authenticity_gate(notes, follower_count, comment_analysis, pgy_meta, cfg):
    a_cfg = cfg["authenticity"]
    threshold = int(a_cfg["threshold"])            # 50
    signals = a_cfg["signals"]
    score, hits, direct_fail = 0, [], False

    # —— 信号1：刷量结构异常（强信号，直接判）——
    # 复用 v1.3 闸门2 计算：fake_ratio（高赞低藏藏）+ collect_inversion（赞藏比倒挂）
    fake_ratio = _compute_fake_ratio(notes, cfg["gate"])     # 见现有实现
    collect_inversion = _collect_like_inversion_hit(notes, follower_count, _tier_for(follower_count))
    if fake_ratio > float(cfg["gate"]["fake_ratio"]) or collect_inversion:
        hits.append({"id": "fake_ratio", "weight": 30, "detail": f"fake_ratio={fake_ratio:.2f} 或 赞藏倒挂"})
        score += 30
        direct_fail = True

    # —— 信号2：赞藏量级双向异常（按层区间，任一命中记满20，不叠加）——
    key = _tier_key(follower_count)
    band = signals["collect_like_band"]["bands"][key]        # e.g. T2 -> [0.008, 0.06]
    _fans = max(1, follower_count)                            # 除零防御（v1.9）
    avg_cl = (sum(n["stats"]["collected"]+n["stats"]["liked"] for n in notes) / max(1, len(notes))) / _fans
    cl_floor = float(signals["collect_like_band"]["collect_like_floor"])   # 0.2（藏/赞结构）
    # 藏/赞结构比：median(藏/赞)
    ratio_list = [n["stats"]["collected"]/max(1, n["stats"]["liked"]) for n in notes if n["stats"]["liked"] > 0]
    median_cl_ratio = statistics.median(ratio_list) if ratio_list else 0.0
    hit2 = None
    if avg_cl < band[0]:
        hit2 = f"篇均(赞+藏)/粉丝={avg_cl:.4f} < 下界{band[0]}"
    elif avg_cl > band[1]:
        hit2 = f"篇均(赞+藏)/粉丝={avg_cl:.4f} > 上界{band[1]}"
    if median_cl_ratio < cl_floor:
        hit2 = (hit2 + "；" if hit2 else "") + f"藏/赞中位={median_cl_ratio:.3f} < {cl_floor}"
    if hit2:
        hits.append({"id": "collect_like_band", "weight": 20, "detail": hit2})
        score += 20                      # 任一命中记满 20，不叠加

    # —— 信号3：水评占比（comment_analysis 可用时）——
    if comment_analysis and float(comment_analysis.get("spam_ratio", 0.0)) >= float(cfg["gate"]["spam_ratio_threshold"]):
        hits.append({"id": "spam_ratio", "weight": 15, "detail": f"水评占比={comment_analysis['spam_ratio']:.2f}"})
        score += 15

    # —— 信号4：篇均点赞绝对值下限（按层）——
    abs_likes = sum(int(n["stats"]["liked"] or 0) for n in notes) / len(notes)
    min_likes = float(cfg["absolute_thresholds"][key]["likes"])
    if abs_likes < min_likes:
        hits.append({"id": "abs_likes_floor", "weight": 10, "detail": f"篇均赞={abs_likes:.1f} < 层下限{min_likes}"})
        score += 10

    # —— 信号5：商单密度（低权重，按层放宽）——
    if pgy_meta and pgy_meta.get("business_note_count") and pgy_meta.get("total_notes"):
        density = int(pgy_meta["business_note_count"]) / max(1, int(pgy_meta["total_notes"]))
        max_ratio = float(signals["commerce_density"]["max_ratio"][_tier_for(follower_count)["tier_name"]])  # T1-T4 名
        if density > max_ratio:
            hits.append({"id": "commerce_density", "weight": 5, "detail": f"商单占比={density:.0%} > 层阈值{max_ratio:.0%}"})
            score += 5

    # —— 信号6：评论模板重复度（B档，with_comments）——
    # v1.9 语义澄清：template_repeat_ratio 只统计【无实际语义的模板短语】——
    #   "蹲链接""求推荐""已关注""支持""太棒了" 等；
    # 必须排除【有真实问询意图的重复内容】——"在哪""多少钱""求同款""怎么去""人均多少"
    #   （这些是高价值种草信号，与种草深度模块的评论意向信号同源，误判会反噬种草评分）。
    if comment_analysis:
        repeat = float(comment_analysis.get("template_repeat_ratio", 0.0))   # 已按上述语义过滤后的占比
        if repeat >= float(a_cfg.get("comment_repeat_threshold", 0.3)):
            hits.append({"id": "comment_repeat", "weight": 15, "detail": f"无语义模板重复占比={repeat:.2f}"})
            score += 15

    # —— 信号7/8/9/10：C档占位（数据可得后启用）——
    # same_brand_repeat(10) / like_rate_band(0) / fans_content_match(0) / organic_share(0)
    # 实施时按配置里 weight>0 且数据已接入的信号循环通用化，避免写死

    passed = (not direct_fail) and (score < threshold)   # score == threshold 判不通过
    return {"passed": passed, "score": score, "direct_fail": direct_fail, "hits": hits}
```

### 2.3 测试用例矩阵
| # | 用例 | 构造 | 期望 |
|---|---|---|---|
| T2-01 | 健康 T2 号 | 互动率达标、赞藏区间内、无商单/评论异常 | passed=True, score=0 |
| T2-02 | 刷量号（强信号） | fake_ratio>阈值 | passed=False, direct_fail=True（走 v1.3 闸门2 不合作） |
| T2-03 | T4 大号赞藏比值低但真实 | avg_cl=0.003 落在 T4 区间 [0.002,0.012] 内 | 信号2 不命中，passed=True（**不误判**） |
| T2-04 | T1 小号赞藏比值高但真实（T1_lt5k） | fans=3000, avg_cl=0.18 > T1_lt5k 上界 0.15 | 命中信号2（高于上界），score=20 <50，passed=True（仅提示） |
| T2-04b | T1 中号（≥5k）用 T1_ge5k 区间 | fans=8000, avg_cl=0.13 > T1_ge5k 上界 0.12 | 命中信号2，score=20，passed=True（验证分层 key 正确） |
| T2-05a | T4 头部专业达人商单 45%（低于阈值） | fans=200w, density=0.45 < T4 阈值 0.50 | 不命中，passed=True（不误伤头部） |
| T2-05b | **商单密度==阈值边界**（钉死 `>` 非 `>=`） | density=0.50 == T4 阈值 0.50 | **不触发**（严格大于），passed=True |
| T2-05c | 商单密度刚过阈值 | density=0.51 > 0.50 | 触发 weight5，总分<50，passed=True（仅提示） |
| T2-06 | 商单密度命中（T2） | fans=5w, density=0.3 > T2 阈值 0.25 | 命中 weight5，总分<50，passed=True（仅提示） |
| T2-07 | 组合命中超阈值（非致命） | 信号2(20)+信号3(15)+信号4(10)+信号6(15)=60 | passed=False（进 caution，不反推报价） |
| T2-08 | 组合命中=50 边界 | score==threshold | passed=False（≥ 阈值判不通过） |
| T2-09 | 无 with_comments | comment_analysis=None | 信号3/6 跳过，不阻塞 |
| T2-10 | 无 pgy 数据 | pgy_meta=None | 信号5 跳过，不阻塞 |
| T2-11 | T1 分层 key | fans=4999 vs 5000 | 用不同绝对下限（10 vs 20） |
| T2-12 | 藏/赞比<0.2 与区间命中并存 | avg_cl 正常但藏/赞=0.1 | 命中信号2 一次，score+20 不叠加 |

---

## Task 3：性价比 `_score_cost_effectiveness`

### 3.1 签名与返回
```python
def _score_cost_effectiveness(
    notes: list[dict],
    follower_count: int,
    tier: dict,                     # _tier_for 结果（含 tier_name）
    pgy_price: dict | None,         # {"picture_price": float, "video_price": float, "lower_price": float}
    pgy_meta: dict | None,          # {"read_mid": int|None, "click_mid": int, "inter_mid": int}
    authenticity: dict,             # _authenticity_gate 结果
    cfg: dict,
) -> dict:
    """返回与设计 §4.6 一致的 dimensions.cost_effectiveness。"""
```

### 3.2 伪代码
```python
def _score_cost_effectiveness(notes, follower_count, tier, pgy_price, pgy_meta, authenticity, cfg):
    c_cfg = cfg["cost"]
    # —— 真实性闸门未过：直接 0 分，不反推报价 ——
    if not authenticity["passed"]:
        return {"score": 0, "confidence": "high",
                "detail": {"authenticity": "failed", "reason": "authenticity_failed",
                           "authenticity_signals": authenticity["hits"]}}

    # —— 无报价：降级（不参与总分）——
    pic = (pgy_price or {}).get("picture_price") or 0
    vid = (pgy_price or {}).get("video_price") or 0
    lower = (pgy_price or {}).get("lower_price")
    if pic <= 0 and vid <= 0:
        return {"score": None, "confidence": "low", "detail": {"reason": "no_price"}}

    # —— 置信度：样本 <10 降 medium ——
    conf = "high" if len(notes) >= 10 else "medium"

    # ① quality_q
    weighted = sum(1*liked + 4*collected + 5*comments + 6*shared for n in notes) / len(notes)
    interaction_rate = weighted / follower_count                      # 0-1
    interaction_rate_pct = interaction_rate * 100
    quality_q = min(1.0, interaction_rate_pct / float(tier["min_healthy"]))

    # ② exposure_est（优先 pgy 阅读字段，否则 粉丝×read_rate）
    read_rate = float(c_cfg["read_rates"][tier["tier_name"]])
    exposure_est = (pgy_meta or {}).get("read_mid") or (follower_count * read_rate)

    # ③ 逐类型计算（图文/视频分别算，见 3.3 标注点①）
    results = {}
    for ntype, price, factor in (("picture", pic, float(c_cfg["type_factor"]["picture"])),
                                 ("video", vid, float(c_cfg["type_factor"]["video"]))):
        if price <= 0:
            results[ntype] = None
            continue
        # CPM/CPE（仅展示）
        cpm = price / (exposure_est / 1000) if exposure_est else None
        cpe = price / (exposure_est * interaction_rate) if exposure_est and interaction_rate else None
        # fair_price + price_score
        anchor = float(c_cfg["price_anchors"][tier["tier_name"]][ntype])
        fair = anchor * (0.4 + 0.6 * quality_q)
        ratio = price / fair
        price_score = _interp(c_cfg["points"], ratio)               # [(0.6,100),(1.0,70),(1.5,40),(2.0,10)]
        # 质量门槛封顶
        cap = 30 if quality_q < 0.3 else (50 if quality_q < 0.5 else 100)
        price_score = min(price_score, cap)
        # 建议报价（双口径）
        read_unit = float(c_cfg["read_unit"][tier["tier_name"]])
        inter_unit = float(c_cfg["inter_unit"][tier["tier_name"]])
        read_value = exposure_est / 1000 * read_unit
        inter_value = exposure_est * interaction_rate * inter_unit
        if quality_q >= 0.5:
            discount = 0.5 + 0.5 * quality_q
            value_ceiling = max(read_value, inter_value) * discount * factor
            bid = (0.6 * inter_value + 0.4 * read_value) * discount * factor * 0.9
        elif quality_q >= 0.3:
            discount = 0.5 * quality_q
            value_ceiling = max(read_value, inter_value) * discount * factor
            bid = (0.6 * inter_value + 0.4 * read_value) * discount * factor * 0.9
        else:
            value_ceiling = bid = None      # 数据质量不足，不反推
        # 市场融合 + 商家友好
        if bid is not None:
            bid = bid * c_cfg["fusion"]["data"] + anchor * c_cfg["fusion"]["anchor"] * 0.9
            value_ceiling = value_ceiling * c_cfg["fusion"]["data"] + anchor * c_cfg["fusion"]["anchor"]
            bid_range = [round(bid * c_cfg["range"][0]), round(bid * c_cfg["range"][1])]
        # lower_price 联动
        lower_warning = None
        if lower and bid is not None and bid < float(lower):
            lower_warning = f"博主自报底价 {lower} 高于系统建议 {round(bid)}，可能不接受该价位"
        results[ntype] = {"score": price_score, "cpm": cpm, "cpe": cpe, "fair": fair,
                          "ratio": ratio, "suggested_bid": bid, "range": bid_range,
                          "value_ceiling": value_ceiling, "lower_warning": lower_warning}

    # ④ 合并总分（v1.9 分差制，取代 min，见 3.3 标注点①）
    scores = [r["score"] for r in results.values() if r]
    gap_flag = False
    if not scores:
        overall_score = None
    elif len(scores) == 1:
        overall_score = round(scores[0], 1)          # 仅一种类型有报价
    else:
        diff = abs(scores[0] - scores[1])
        if diff < 20:
            # 分差小 → 按 type_factor 加权平均（图文 0.8 / 视频 1.0）
            w_pic, w_vid = c_cfg["type_factor"]["picture"], c_cfg["type_factor"]["video"]
            overall_score = round((scores[0]*w_pic + scores[1]*w_vid) / (w_pic + w_vid), 1)
        else:
            # 分差大 → max×0.85（比纯 max 保守）+ 显式分歧提示，不掩盖差异
            overall_score = round(max(scores) * 0.85, 1)
            gap_flag = True

    # ⑤ 行业基准旁证（展示）
    industry = _industry_benchmarks(exposure_est, interaction_rate_pct, notes, c_cfg)

    # ⑥ CPM 交叉校验分级
    audit = None
    click_mid = (pgy_meta or {}).get("click_mid")
    if click_mid and results.get("picture") and results["picture"]["cpm"]:
        cpm_platform = pic / (click_mid / 1000)
        r = max(cpm_platform, results["picture"]["cpm"]) / max(1, min(cpm_platform, results["picture"]["cpm"]))
        if r > c_cfg["cpm_mismatch"]["red"]: audit = "red"
        elif r > c_cfg["cpm_mismatch"]["yellow"]: audit = "yellow"

    return {"score": overall_score, "confidence": conf,
            "detail": {"authenticity": "passed", "authenticity_signals": authenticity["hits"],
                       "picture_price": pic, "video_price": vid, "lower_price": lower,
                       "fair_picture": ..., "fair_video": ..., "suggested_bid_picture": ...,
                       "suggested_range_picture": ..., "suggested_bid_video": ..., "suggested_range_video": ...,
                       "value_ceiling_picture": ..., "value_ceiling_video": ...,
                       "lower_price_warning": ..., "cpm": ..., "cpe": ..., "cpm_platform": ...,
                       "type_score_gap_flag": gap_flag,          // v1.9：图文/视频分差≥20 时为 true
                       "audit_flag": audit, "quality_q": quality_q,
                       "price_ratio_picture": ..., "anchor_tier": tier["tier_name"],
                       "exposure_source": "pgy_read" if (pgy_meta or {}).get("read_mid") else "read_rate_est",
                       "industry_benchmarks": industry}}
```

### 3.3 标注点（需评审确认）
1. **图文/视频合并规则（v1.9 分差制）**：
   - 仅一种有报价 → 总分 = 该类型分（T3-08）
   - 两者都有且分差 <20 → 按 type_factor 加权平均（图文 0.8 / 视频 1.0）
   - 两者都有且分差 ≥20 → `overall = max(图文, 视频) × 0.85`，`type_score_gap_flag=true`，
     UI/AI 总结提示"图文与视频性价比差异较大，建议按投放类型分别评估"，把是否谨慎交回人工，
     而不是用合并公式替使用者悄悄决定。
   - 不使用 min（会系统性低估"图文超值/视频一般"类账号，且在默认无 merchant_profile 场景影响面大）。
2. **无 read_mid 时 CPM 基准**：用 `粉丝×read_rate` 估算，`exposure_source="read_rate_est"`；`audit_flag` 的交叉校验仅在 `click_mid` 可用时启用。

### 3.4 测试用例矩阵
| # | 用例 | 构造 | 期望 |
|---|---|---|---|
| T3-01 | 正常 T2 有报价 | quality_q=0.85, pic=1500, vid=2500 | score 中高；bid_picture≈1100 < value_ceiling≈1290；range 合理 |
| T3-02 | 刷量号 | authenticity.passed=False | score=0, 不反推报价, detail.reason=authenticity_failed |
| T3-03 | 无报价 | pic=vid=0 | score=None, confidence=low（不参与总分） |
| T3-04 | 无报价但有点击中位数 | pic=0, click_mid 有 | 仍反推建议报价, confidence=medium（降级路径） |
| T3-05 | 质量极差 | quality_q=0.2 | cap=30；bid/value_ceiling=None（数据质量不足） |
| T3-06 | 质量中差 | quality_q=0.4 | cap=50；折扣走 low_band（0.5×q） |
| T3-07 | 建议价低于底价 | bid=800 < lower=1000 | lower_price_warning 提示 |
| T3-08 | 只开通图文报价 | vid=0 | 仅 picture 有 sub-score，总分=图文分 |
| T3-09 | CPM 交叉校验 yellow | cpm_platform/cpm=3x | audit_flag=yellow |
| T3-10 | CPM 交叉校验 red | cpm_platform/cpm=6x | audit_flag=red |
| T3-11 | 样本 <10 | len(notes)=8 | confidence=medium（权重减半） |
| T3-12 | 封顶边界 | quality_q=0.3 / 0.5 | 分别 cap=30 / cap=50 |
| T3-13 | 图文/视频分差≥20 | pic=85, vid=40, diff=45 | overall=85×0.85=72.3, type_score_gap_flag=true（不再 min 判死） |
| T3-14 | 图文/视频分差<20 加权平均 | pic=70, vid=80, diff=10 | overall=(70×0.8+80×1.0)/1.8≈75.6, gap_flag=false |
| T3-15 | 仅图文有报价 | vid=0 | overall=图文分（沿用） |
| T3-16 | 行业旁证 | cpe=3.2 | cpe_band="优秀"（图文/视频各自分档） |

---

## Task 4：受众画像 `_score_audience_profile`

### 4.1 签名与返回
```python
def _score_audience_profile(
    notes: list[dict],          # 真实样本（与五维同一批，近90天）
    tier: dict,                 # _tier_for 结果（含 tier_name: T1-T4）
    cfg: dict,                  # load_scoring_config()
) -> dict:
    """返回设计 §5.6 的 audience 结构 + 垂直度深化所需分数。"""
    return {
        "dominant_level": str | None,     # 大众/中端/高端/奢华；无信号时 None
        "level_distribution": dict,       # {层级: 占比}
        "avg_price_band": list | None,    # [P25, P75] 人均区间；价格样本 <3 时 None
        "top_categories": list,           # Top3 品类（计数降序）
        "top_scenes": list,               # Top3 场景
        "merchant_tiers": list,           # 交叉映射 §3.4
        "signal_notes": int,              # 有任一信号的笔记数（置信度依据）
        "confidence": str,                # high | low（signal_notes < min_signal_notes → low）
        "verticality_audience_score": float,  # 受众层级集中度 0-100（供 verticality 集成）
    }
```

### 4.2 伪代码
```python
import re, statistics

def _score_audience_profile(notes, tier, cfg):
    a_cfg = cfg["audience"]
    min_signal = int(a_cfg["min_signal_notes"])              # 5
    neg_words = a_cfg["negative_words"]                      # ["别","避雷","踩雷","不值",...]
    exclude_words = a_cfg["price_exclude_words"]             # ["卡路里","优惠","满减","限量",...]
    level_kw = a_cfg["level_keywords"]                       # {奢华:[...], 高端:[...], 中端:[...], 大众:[...]}
    cat_kw = a_cfg["category_keywords"]                      # {火锅:[...], 甜品:[...], ...}
    scene_kw = a_cfg["scene_keywords"]
    price_pattern = re.compile("|".join(a_cfg["price_patterns"]))
    tier_name = tier["tier_name"]                            # T1-T4

    price_hits: list[int] = []
    level_counts = {k: 0 for k in level_kw}                  # {"大众":0,"中端":0,"高端":0,"奢华":0}
    cat_counts, scene_counts = {}, {}
    signal_notes = 0

    for n in notes:
        text = f"{n.get('title','')}\n{n.get('desc','')}\n{' '.join(n.get('tags',[]) or [])}"
        # —— ① 负面语义前置过滤（v1.6）：命中负面词 → 整篇排除 ——
        if any(w in text for w in neg_words):
            continue

        # —— per-note 信号标记（v1.10 修复：绝不用累计容器判断，避免跨笔记污染）——
        note_has_price = note_has_level = note_has_cat = note_has_scene = False

        # —— ② 价格信号：正则 + 同句排除词（句界 = 。！？；\n，逗号不算）——
        for sentence in re.split(r"[。！？；\n]", text):
            for m in price_pattern.finditer(sentence):
                if any(w in sentence for w in exclude_words):
                    continue                        # 同句含排除词（如"满100减20""880卡路里"）→ 跳过该数字
                try:
                    price_hits.append(int(m.group(1)))
                    note_has_price = True
                except (IndexError, ValueError):
                    continue

        # —— ③ 层级信号：按"首个出现位置"决定主导层级（确定性，测试可钉死）——
        best_pos, best_level = None, None
        for level, kws in level_kw.items():
            for kw in kws:
                pos = text.find(kw)
                if pos != -1 and (best_pos is None or pos < best_pos):
                    best_pos, best_level = pos, level
        if best_level:
            level_counts[best_level] += 1
            note_has_level = True

        # —— ④ 品类 / 场景信号（可多命中）——
        for cat, kws in cat_kw.items():
            if any(kw in text for kw in kws):
                cat_counts[cat] = cat_counts.get(cat, 0) + 1
                note_has_cat = True
        for sc, kws in scene_kw.items():
            if any(kw in text for kw in kws):
                scene_counts[sc] = scene_counts.get(sc, 0) + 1
                note_has_scene = True

        if note_has_price or note_has_level or note_has_cat or note_has_scene:
            signal_notes += 1

    # —— 置信度 ——
    confidence = "high" if signal_notes >= min_signal else "low"

    # —— 聚合：层级分布 ——
    total_level = sum(level_counts.values())
    level_distribution = {k: round(v / total_level, 4) for k, v in level_counts.items()} if total_level else {}
    dominant_level = max(level_distribution, key=level_distribution.get) if level_distribution else None

    # —— 聚合：人均价格区间（P25-P75，样本 <3 → None）——
    avg_price_band = None
    if len(price_hits) >= 3:
        prices = sorted(price_hits)
        p25 = _percentile(prices, 25)
        p75 = _percentile(prices, 75)
        avg_price_band = [p25, p75]

    # —— 聚合：Top3 品类/场景 ——
    top_categories = [k for k, _ in sorted(cat_counts.items(), key=lambda x: -x[1])[:3]]
    top_scenes = [k for k, _ in sorted(scene_counts.items(), key=lambda x: -x[1])[:3]]

    # —— 交叉映射 merchant_tiers（§3.4 / §9 merchant_tier_map）——
    merchant_tiers = []
    if dominant_level:
        merchant_tiers = a_cfg["merchant_tier_map"].get(tier_name, {}).get(dominant_level, [])

    # —— 受众层级集中度（垂直度深化，>70% 满分 / <40% 0 分，中间插值）——
    concentration = level_distribution.get(dominant_level, 0.0) if dominant_level else 0.0
    verticality_audience_score = _interp([(0.4, 0.0), (0.7, 100.0)], concentration) if concentration else 0.0

    return {
        "dominant_level": dominant_level,
        "level_distribution": level_distribution,
        "avg_price_band": avg_price_band,
        "top_categories": top_categories,
        "top_scenes": top_scenes,
        "merchant_tiers": merchant_tiers,
        "signal_notes": signal_notes,
        "confidence": confidence,
        "verticality_audience_score": round(verticality_audience_score, 1),
    }

def _percentile(sorted_values: list[int], pct: int) -> int:
    if not sorted_values:
        return 0
    k = (len(sorted_values) - 1) * pct / 100.0
    f, c = int(k), min(int(k) + 1, len(sorted_values) - 1)
    return int(sorted_values[f] + (sorted_values[c] - sorted_values[f]) * (k - f))
```

### 4.3 实现注意（易错点）
1. **signal_notes 计数（v1.10 已修复）**：伪代码已改为 per-note 布尔标记（`note_has_price/level/cat/scene`）累加；**绝不允许**用累计容器（`price_hits/cat_counts/scene_counts` 是否非空）判断——那会让一旦出现过信号的账号后续所有笔记都被误计入，置信度保护失效。T4-21 专门钉死此点防回归。
2. **价格排除词按"同句"判定**：句界 = `。！？；换行`，逗号不算——"人均80元，限量供应"（同句）→ 跳过；"人均80元。限量供应"（不同句）→ 保留。测试 T4-03 钉死。
3. **层级主导用"首个出现位置"**：保证确定性；测试 T4-05 固定输入顺序可复现。
4. **dominant_level 为空**（全部被负面过滤或无关键词）：merchant_tiers=[]、avg_price_band 可独立有值（价格信号与层级信号互不影响）；confidence 仍按 signal_notes 判定。

### 4.4 测试用例矩阵
| # | 用例 | 构造 | 期望 |
|---|---|---|---|
| T4-01 | 负面语义过滤 | 笔记含"人均300，踩雷别去" | 整篇排除：价格/层级/品类信号均不计入 |
| T4-02 | 价格噪音-同句 | "满100减20"（含"满减"） | 跳过，price_hits 不含 100 |
| T4-03 | 价格噪音-同句 vs 跨句 | "人均80元，限量供应" vs "人均80元。限量供应" | 前者跳过；后者保留 80 |
| T4-04 | 卡路里排除 | "880卡路里" | 跳过 880 |
| T4-05 | 层级主导-首个位置 | text="这家在商场里，小吃不错"（中端"商场"在 大众"小吃"之前） | 记为中端 1 次（不记大众） |
| T4-06 | 层级分布与 dominant | 30篇大众/10篇中端 | dominant=大众, 分布 0.75/0.25 |
| T4-07 | 置信度 low | signal_notes=3 <5 | confidence=low（仅展示不评分） |
| T4-08 | 价格区间 P25/P75 | prices=[50,60,80,100,200] | [60, 100] |
| T4-09 | 价格样本 <3 | price_hits=2 | avg_price_band=None |
| T4-10 | 交叉映射 T3+大众 | tier=T3, dominant=大众 | merchant_tiers=["区域连锁快餐","大众品牌"] |
| T4-11 | 交叉映射 T3+高端 | tier=T3, dominant=高端 | merchant_tiers=["区域头部","精品品牌"] |
| T4-12 | 交叉映射 无 dominant | 全部被负面过滤 | merchant_tiers=[], dominant=None |
| T4-13 | 集中度 0.8 | dominant 占比 0.8 | verticality_audience_score=100 |
| T4-14 | 集中度 0.5 | dominant 占比 0.5 | 插值 ≈ (0.5-0.4)/(0.7-0.4)×100 ≈ 33.3 |
| T4-15 | 集中度 0.3 | dominant 占比 0.3 | 0 |
| T4-16 | Top3 排序 | 火锅5/甜品3/咖啡2/奶茶1 | top_categories=["火锅","甜品","咖啡"] |
| T4-17 | 品类空 | 无任何品类关键词 | top_categories=[]（不报错） |
| T4-18 | tags 参与拼接 | 关键词只出现在 tags | 命中（tags 已并入 text） |
| T4-19 | 纯价格无层级 | 仅"人均80元"无层级词 | avg_price_band 有值、dominant=None、merchant_tiers=[] |
| T4-20 | 多篇聚合稳定 | 同输入重复调用 | 结果确定（无随机性） |
| T4-21 | **signal_notes 不受历史累计污染（防回归）** | 3 篇有信号（价格/层级/品类各一篇）+ 7 篇完全无任何信号（无价格/无层级词/无品类场景词/不含负面词） | `signal_notes == 3`（不是 10）；若实现误用累计容器判断，此条失败 |

### 4.5 与 verticality 集成（Task 5 边界）
- `food_verticality` 改为：`0.7 × 品类垂直度（现有） + 0.3 × verticality_audience_score`
- 受众画像 `confidence=low` 时：verticality_audience_score 不参与（0.3 权重回落到品类垂直度），insights 提示"受众画像样本不足，垂直度仅按品类评估"
- 测试：verticality 集成后 T1 品垂直+受众分散 vs 受众集中的分差（待 Task 5 细化）


## Task 7：score_blogger 集成 + 置信度归一化（最高优先级，牵动全局）

### 7.1 集成点（在 score_blogger 内、闸门1 通过且 tier 已知之后）
```python
tier = _tier_for(follower_count)
cfg = load_scoring_config()

# —— v1.11 集成：真实性闸门 / 受众画像 / 性价比 ——
authenticity = _authenticity_gate(real, follower_count, comment_analysis, pgy_meta, cfg)
audience     = _score_audience_profile(real, tier, cfg)
pgy_price    = (pgy_meta or {}).get("price")           # {"picture_price","video_price","lower_price"}
cost         = _score_cost_effectiveness(real, follower_count, tier, pgy_price, pgy_meta, authenticity, cfg)

# dimensions 追加 cost_effectiveness（score None 时由通用归一化剔除）
dimensions["cost_effectiveness"] = {
    "score": cost["score"], "confidence": cost["confidence"], "detail": cost["detail"],
}

# 顶层 audience + verticality.detail 内嵌
base["audience"] = audience
dimensions["verticality"]["detail"]["audience"] = audience

# 垂直度集成（Task 5）：0.7×品类 + 0.3×集中度；画像 low 时回落纯品类
if audience["confidence"] == "high":
    dimensions["verticality"]["score"] = round(
        0.7 * dimensions["verticality"]["score"] + 0.3 * audience["verticality_audience_score"], 1)
else:
    base["insights"].append("受众画像样本不足，垂直度仅按品类评估")

base["confidence"] = _overall_confidence(dimensions, coverage_conf)   # cost None 计 low，走非核心单 low 特例
```

### 7.2 权重归一化（§6.2 通用公式，替换现有 growth_trend 特判）
```python
weights = dict(cfg["weights"])        # 含 cost_effectiveness: 0.10
w_eff: dict[str, float] = {}
for k, w in weights.items():
    dim = dimensions[k]
    if dim.get("score") is None:
        continue                                      # 无数据 → 剔除
    w_eff[k] = w * (0.5 if dim.get("confidence") != "high" else 1.0)   # low/medium 均 ×0.5
denom = sum(w_eff.values())
if denom <= 0:
    # 沿用：overall=None + score_suppressed + insufficient_data
    ...
overall = sum(dimensions[k]["score"] * w_eff[k] for k in w_eff) / denom
overall = round(overall, 1)
level, desc = _level_for(overall)
```
> 说明：该公式天然兼容现状——growth_trend 无快照（low 但有内容趋势分）→ ×0.5；growth_trend score=None → 剔除；无报价 cost（score None）→ 剔除。

### 7.3 `_overall_confidence` 调整
- `_NONCORE` 增加 `cost_effectiveness`（无报价 score None 计 low 时，作为唯一 low 非核心维度触发"整体 medium"特例，不拖低整体置信度）。
- 其余逻辑不变（§7 通用汇总规则：min + 单非核心 low 特例）。

### 7.4 测试用例矩阵
| # | 用例 | 构造 | 期望 |
|---|---|---|---|
| T7-01 | 完整数据 | 五维 high + cost high | overall 按 w_eff 正确（分母含 cost 0.10） |
| T7-02 | 无报价 | cost score=None, confidence=low | cost 剔除、分母归一化；_overall_confidence 因 cost 单非核心 low → medium（其余 high） |
| T7-03 | cost medium（样本<10） | cost confidence=medium | cost 权重 ×0.5 计入 |
| T7-04 | growth_trend low（无快照） | 保留分数 | 权重 ×0.5（沿用现状，验证统一公式不破坏） |
| T7-05 | growth_trend score=None | 无内容趋势 | 剔除 |
| T7-06 | authenticity failed | cost score=0 | cost 以 0 计入（整体被压低），decision 加 authenticity_failed 红旗 |
| T7-07 | audience high | 集中度 0.8 | verticality = 0.7×品类 + 0.3×100 |
| T7-08 | audience low | 样本不足 | verticality 纯品类，insights 提示 |
| T7-09 | 全维度 score=None | 极端缺数据 | overall=None + insufficient_data（沿用） |
| T7-10 | 配置权重和=1 | weights 校验 | 1.00（0.25+0.20+0.15+0.15+0.15+0.10） |
| T7-11 | 多 low 组合 | cost low + growth low | _overall_confidence=low（非单 low 特例不触发） |
| T7-12 | 向后兼容 | 不传 pgy/comment（老路径） | cost 走无报价降级、audience 低置信，行为不崩；五维总分与旧逻辑一致 |

---

## Task 6：merchant_profile 匹配 `_audience_match`（次优先，需先定公式）

### 6.1 签名与返回
```python
def _audience_match(audience: dict, merchant_profile: dict | None, tier: dict, cfg: dict) -> dict:
    """返回设计 §7.3 的 audience.match。"""
    return {
        "has_profile": bool,
        "score": int | None,                 # 0-100；无 profile 或无可比子项时为 None
        "sub_scores": {"price_overlap": int|None, "category_overlap": int|None,
                       "level_match": int|None, "city_match": int|None},
        "mismatches": [str],                 # 子项分 < match_threshold 的说明
    }
```

### 6.2 四个子项公式（权重：客单价 0.40 / 品类 0.25 / 层级 0.25 / 城市 0.10）
```
① 客单价重叠度 price_overlap（0-100）
   区间 [a1,a2] = audience.avg_price_band；[t1,t2] = merchant_profile.target_price_band
   —— 区间-区间（t1 < t2）——
   overlap = max(0, min(a2,t2) - max(a1,t1))
   union   = max(a2,t2) - min(a1,t1)
   score   = round(overlap / union * 100) if union > 0 else 100
   —— 单点目标价（t1 == t2，v1.12 特殊分支）——
   若点 p=t1 落在 [a1,a2] 内（含边界）→ score = 100
   否则（p < a1 或 p > a2）：
     dist  = min(|p-a1|, |p-a2|)；width = a2 - a1
     score = max(0, round((1 - dist/width) * 100)) if width > 0 else 0
   —— 零宽双方（a1==a2 且 t1==t2）→ 相等 100，否则 0
   任一侧缺失（avg_price_band=None / target_price_band 空）→ 该子项不参与，权重重分配

② 品类交集 category_overlap（0-100）
   hit = |audience.top_categories ∩ target_categories|
   score = round(hit / len(target_categories) * 100)
   target_categories 空 → 不参与

③ 层级一致度 level_match（0-100）
   dominant_level vs target_merchant_tier（大众/中端/高端/奢华）
   相同=100；相邻（大众↔中端、中端↔高端、高端↔奢华）=60；隔一级=20；隔两级=0
   任一侧为空 → 不参与

④ 城市适配度 city_match（0-100）
   tier → 期望体量：T1=本地, T2=区域, T3=区域/全国（双目标）, T4=全国
   city_scope（本地/区域/全国）vs 期望：
   - 单目标（T1/T2/T4）：完全=100；相邻（本地↔区域、区域↔全国）=60；跨级=20
   - 双目标（T3，v1.12 明确）：命中区域或全国**任一** → 100；都不命中时按**到最近一个期望值**的序数距离
     （例：city_scope=本地 vs T3 → 到最近的"区域"为相邻 → 60）
   city_scope 空 → 不参与

合并：提供子项集合 S，match = Σ(score_i × w_i) / Σw_i（按提供的子项归一化）
判定：match < match_threshold(60) → audience_mismatch 红旗（信息型，不进 caution）
```

### 6.3 测试用例矩阵
| # | 用例 | 构造 | 期望 |
|---|---|---|---|
| T6-01 | 客单价完全重叠 | [60,150] vs [60,150] | price_overlap=100 |
| T6-02 | 客单价部分重叠 | [60,150] vs [100,200] | overlap=50/union=140 → 35.7→36 |
| T6-03 | 客单价无重叠 | [60,100] vs [150,200] | 0 |
| T6-04 | 客单价包含关系 | [50,200] vs [80,120] | overlap=40/union=150 → 26.7→27 |
| T6-05 | 品类交集 2/3 | target=[火锅,烧烤,甜品], top=[火锅,甜品,咖啡] | 66.7→67 |
| T6-06 | 品类无交集 | 无共同品类 | 0 |
| T6-07 | 层级一致度 | 相同/相邻/隔一级 | 100 / 60 / 20 |
| T6-08 | 城市适配 | 本地 vs T1 / 全国 vs T1 | 100 / 20 |
| T6-09 | 缺失子项权重重分配 | 仅客单价+品类提供 | 只按这两项权重归一化 |
| T6-10 | 无 profile | merchant_profile=None | has_profile=false, score=None |
| T6-11 | 加权合并示例（算式修正 v1.12） | price=35×0.4+cat=50×0.25+level=100×0.25+city=60×0.1 = 14+12.5+25+6 = 57.5 | score=58 <60 → mismatch 触发 |
| T6-12 | avg_price_band=None | 画像无价格信号 | price 子项跳过，其余归一化 |
| T6-13a | 单点目标价落在区间内 | target=[50,50], band=[30,80] | price_overlap=100（50 在区间内，直觉"完全匹配"） |
| T6-13b | 单点目标价在区间外 | target=[50,50], band=[20,40] | dist=10, width=20 → score=50 |
| T6-13c | 单点目标价贴边界 | target=[50,50], band=[20,50] | 含边界 → 100 |
| T6-14 | 边界恰好 60 | match=60 | 不触发 mismatch（≥ 阈值） |
| T6-15 | T3 双目标城市 | city_scope=区域 vs T3 / 全国 vs T3 / 本地 vs T3 | 100 / 100 / 60（到最近期望"区域"相邻） |

---

## 其余 Task 概述（逻辑简单/接线/依赖真实数据，暂不细化到伪代码）

### Task 1：配置落盘（概述）
- `scoring_config.py` DEFAULT_SCORING_CONFIG 新增 `cost` / `audience` / `authenticity` / `absolute_thresholds` 段 + `weights` 增 `cost_effectiveness: 0.10`（§9 全量字段）
- `crawler_config.json` 的 `blogger_scoring` 段可覆盖示例 + `clear_scoring_config_cache()` 热更新
- 测试：缺失段回退默认 / 锚点升序校验 / 权重和=1 校验

### Task 5：verticality 集成（概述）
- `food_verticality` 结果 → `0.7×品类垂直度 + 0.3×verticality_audience_score`（audience high 时）
- audience low → 纯品类 + insights 提示
- 测试：T5-01 品垂直+受众集中（高）/ T5-02 品垂直+受众分散（中）/ T5-03 audience low 回落 / T5-04 边界 0%/100%

### Task 8：决策 / 红旗 / insights / AI 联动（概述）
- decision.reasons 追加：性价比结论 + 建议报价区间 + 受众画像（dominant_level/merchant_tiers）+ 匹配结论（有 profile 时）
- 红旗接线：`overpriced_low_quality`（cost<40 且 quality_q<0.5）/ `authenticity_failed`（进 caution）/ `audience_mismatch`（信息型）
- 优先合作档位：原条件 且 性价比∈{高,极高}（有报价时）且 匹配≥60（有 profile 时）
- AI 总结 prompt 注入：建议报价 + 受众画像 + 匹配提示
- 测试：T8-01~T8-06（各红旗触发、档位升降、summary 文案含建议报价）

### Task 9：前端（概述，依赖后端接口）
- 性价比卡片：建议出价区间 + 价值上限 + lower_price 提示 + 行业旁证 + audit_flag 徽标
- 受众画像区块：层级分布条形 + 人均区间 + 商家适配 + merchant_profile 输入（目标客单价/品类/层级/城市）
- 单号分析与批量筛选表格：新增性价比分、建议报价、dominant_level 列
- 验证：tsc / eslint / build

### Task 10：标定脚本（概述，依赖真实数据，可后置）
- 相似创作者报价标定：拉同层博主真实报价 → P25/P50/P75 替换 §3.3 锚点
- 分层参数标定：绝对下限/赞藏区间/商单密度阈值 ← 真实样本 P10/P25/P90
- 权重回测：历史合作效果 vs v1.11 总分，验证 0.25/0.15 权重调整；未完成前标 `weights_pending_calibration`


## 4. 评审结论与定稿（v1.9）
1. **图文/视频合并规则**：已按评审改为分差制（分差<20 加权平均 / ≥20 max×0.85 + gap_flag），弃用 min。✅ 已定稿
2. **`comment_repeat_threshold`=0.3**：数值保留；`template_repeat_ratio` 语义已澄清——只统计无语义模板短语，排除"在哪/多少钱/求同款"等问询意图内容，避免与种草深度评论意向信号冲突。✅ 已定稿
3. **T1_lt5k/T1_ge5k 拆分**：保留（两档阈值/区间数值差近一倍，拆分维护成本低）。✅ 已定稿
4. **C档（信号7/8/9/10）通用化实现**：按"配置 weight>0 且数据已接入"通用循环 + 独立判定函数。✅ 已定稿
5. 新增：signal2 除零防御（follower_count=0）；T2-05 拆成 ==阈值/过阈值 边界用例；T2-04 补 fans 数值。✅ 已定稿
