# 博主种草能力分析系统重构 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把小红书博主分析从「四维真实数据评分」重构为「餐饮种草能力五维评分 + 账号阶段 + 低质号闸门 + 合作建议」，同一引擎支撑单号深度诊断与批量筛选。

**Architecture:** 保留 C9 真实数据骨架（真实样本准入/粉丝分层/类型内标准化/资格闸门），在 `blogger_scoring.py` 内重构为五维（种草深度/内容垂直度/稳定产出/持续经营/增长趋势），新增 `blogger_verticality.py`（美食关键词分类）与 `blogger_comments.py`（可选评论意向分析）；`score_blogger` 输出新增 recommendation 枚举 + score_suppressed + stage + 通用置信度汇总。旧同步分析接口两阶段下线（先 410+埋点，确认零调用后删文件）。

**Tech Stack:** Python 3 / FastAPI / SQLAlchemy async / pytest / TypeScript / React + Ant Design + Recharts。

**设计规格:** `docs/superpowers/specs/2026-08-11-blogger-seeding-analysis-design.md`（v1.3）

---

## 阶段总览

- **Phase 1 后端**（Task 1–11）：配置 → 垂直度 → 种草深度 → 稳定产出 → 增长趋势 → 阶段 → 闸门 → 置信度/决策 → score_blogger 整合 → 评论增强 → 旧引擎下线。每 Task 独立可测、可提交。
- **Phase 2 前端**（Task 12–14）：api client → UserAnalysisPanel 升级 → 批量筛选视图。

> 后端 Task 依赖顺序执行；前端 Task 依赖后端 Task 9 落地的 JSON 结构。

---

## Phase 1 后端

### Task 1: 配置扩展 — blogger_scoring 段

**Files:**
- Modify: `backend/services/crawler/config.py`（DEFAULT_CONFIG 增加 `blogger_scoring` 默认段）
- Create: `backend/app/services/scoring_config.py`（读取/合并配置 + 默认值兜底）
- Test: `backend/tests/test_scoring_config.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_scoring_config.py
from app.services.scoring_config import load_scoring_config, DEFAULT_SCORING_CONFIG

def test_defaults_present():
    cfg = load_scoring_config()
    assert set(cfg["weights"]) == {
        "seeding_depth", "verticality", "stable_output", "sustained_operation", "growth_trend",
    }
    assert abs(sum(cfg["weights"].values()) - 1.0) < 1e-9
    assert "T1" in cfg["tiers"] and "T4" in cfg["tiers"]
    assert cfg["tiers"]["T1"]["growth_baseline"] > 0
    assert "探店" in cfg["verticality"]["food_keywords"]
    assert "gate" in cfg and cfg["gate"]["stale_days"] == 60


def test_json_override():
    cfg = load_scoring_config()
    # 默认兜底存在即可；覆盖逻辑由 merge 单元保证
    merged = dict(DEFAULT_SCORING_CONFIG)
    merged["weights"] = {**merged["weights"], "seeding_depth": 0.4}
    assert merged["weights"]["seeding_depth"] == 0.4
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_scoring_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.scoring_config'`

- [ ] **Step 3: 实现 scoring_config.py**

```python
# backend/app/services/scoring_config.py
"""博主种草评分配置：默认值 + crawler_config.json 的 blogger_scoring 段覆盖。"""
from __future__ import annotations

import copy

DEFAULT_SCORING_CONFIG: dict = {
    "weights": {
        "seeding_depth": 0.30,
        "verticality": 0.20,
        "stable_output": 0.20,
        "sustained_operation": 0.15,
        "growth_trend": 0.15,
    },
    "tiers": {
        "T1": {"min": 1000, "max": 10000, "min_healthy_rate": 1.0, "growth_baseline": 0.06,
               "collect_rate_points": [(0.4, 0), (0.8, 40), (1.5, 70), (3.0, 100)],
               "share_rate_points": [(0.02, 0), (0.05, 40), (0.12, 70), (0.3, 100)]},
        "T2": {"min": 10000, "max": 100000, "min_healthy_rate": 0.6, "growth_baseline": 0.09,
               "collect_rate_points": [(0.2, 0), (0.4, 40), (0.8, 70), (1.5, 100)],
               "share_rate_points": [(0.01, 0), (0.03, 40), (0.08, 70), (0.2, 100)]},
        "T3": {"min": 100000, "max": 1000000, "min_healthy_rate": 0.3, "growth_baseline": 0.08,
               "collect_rate_points": [(0.1, 0), (0.2, 40), (0.4, 70), (0.8, 100)],
               "share_rate_points": [(0.005, 0), (0.015, 40), (0.04, 70), (0.1, 100)]},
        "T4": {"min": 1000000, "max": None, "min_healthy_rate": 0.15, "growth_baseline": 0.07,
               "collect_rate_points": [(0.05, 0), (0.1, 40), (0.2, 70), (0.4, 100)],
               "share_rate_points": [(0.003, 0), (0.008, 40), (0.02, 70), (0.05, 100)]},
    },
    "verticality": {
        "food_keywords": [
            "探店", "美食", "好吃", "打卡", "菜单", "套餐", "口味", "推荐", "人气",
            "排队", "新店", "必吃", "餐厅", "小吃", "甜品", "咖啡", "奶茶", "火锅", "烧烤",
        ],
        "points": [(0.2, 10), (0.4, 40), (0.6, 70), (0.8, 100)],
    },
    "viral": {"median_multiplier": 3.0, "abs_min": 200, "points": [(0.0, 0), (0.08, 40), (0.1, 70), (0.2, 100)]},
    "stability": {"gap_days": 14, "cliff_drop": 0.5, "cliff_penalty": 25},
    "growth": {"content_weight": 0.3, "points": [(0.0, 15), (0.5, 45), (1.0, 75), (1.2, 100)]},
    "comments": {
        "intent_keywords": ["在哪", "多少钱", "好吃吗", "怎么去", "求地址", "人均", "哪里", "电话", "营业", "菜单"],
        "spam_keywords": ["太棒了", "学习了", "支持", "求链接", "已收藏", "点赞"],
        "negative_keywords": ["广告", "取关", "踩雷", "差评", "失望"],
        "note_limit": 8,
        "per_note": 50,
    },
    "gate": {
        "stale_days": 60,
        "fake_ratio": 0.20,
        "fake_extra_ratio": 0.005,
        "collect_like_ratio_floor": 0.2,
        "growth_spike": 0.20,
        "growth_interaction_drop": 0.2,
        "t1_growth_spike": 0.35,
    },
    "stage": {"cold_start_fans": 5000},
}


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_scoring_config() -> dict:
    """读取 crawler_config.json 的 blogger_scoring 段并覆盖默认值。"""
    try:
        from crawler.config import load_config

        raw = load_config().get("blogger_scoring") or {}
        return _deep_merge(DEFAULT_SCORING_CONFIG, raw)
    except Exception:
        return copy.deepcopy(DEFAULT_SCORING_CONFIG)
```

- [ ] **Step 4: 修改 config.py 默认段**

在 `backend/services/crawler/config.py` 的 `DEFAULT_CONFIG` 末尾（`"subscription_deep_sync_max_per_run": 200,` 之后）加：

```python
    "blogger_scoring": {
        "weights": {
            "seeding_depth": 0.30, "verticality": 0.20, "stable_output": 0.20,
            "sustained_operation": 0.15, "growth_trend": 0.15,
        },
        "tiers": {
            "T1": {"min": 1000, "max": 10000, "min_healthy_rate": 1.0, "growth_baseline": 0.06},
            "T2": {"min": 10000, "max": 100000, "min_healthy_rate": 0.6, "growth_baseline": 0.09},
            "T3": {"min": 100000, "max": 1000000, "min_healthy_rate": 0.3, "growth_baseline": 0.08},
            "T4": {"min": 1000000, "max": None, "min_healthy_rate": 0.15, "growth_baseline": 0.07},
        },
        "verticality": {"food_keywords": ["探店", "美食", "好吃", "打卡", "菜单", "套餐", "口味", "推荐", "人气", "排队", "新店", "必吃", "餐厅", "小吃", "甜品", "咖啡", "奶茶", "火锅", "烧烤"]},
        "viral": {"median_multiplier": 3.0, "abs_min": 200},
        "stability": {"gap_days": 14, "cliff_drop": 0.5, "cliff_penalty": 25},
        "comments": {
            "intent_keywords": ["在哪", "多少钱", "好吃吗", "怎么去", "求地址", "人均", "哪里", "电话", "营业", "菜单"],
            "spam_keywords": ["太棒了", "学习了", "支持", "求链接", "已收藏", "点赞"],
            "negative_keywords": ["广告", "取关", "踩雷", "差评", "失望"],
            "note_limit": 8,
            "per_note": 50,
        },
        "gate": {
            "stale_days": 60, "fake_ratio": 0.20, "fake_extra_ratio": 0.005,
            "collect_like_ratio_floor": 0.2, "growth_spike": 0.20,
            "growth_interaction_drop": 0.2, "t1_growth_spike": 0.35,
        },
        "stage": {"cold_start_fans": 5000},
    },
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_scoring_config.py -v`
Expected: PASS（2 passed）

- [ ] **Step 6: Commit**

```bash
git add backend/services/crawler/config.py backend/app/services/scoring_config.py backend/tests/test_scoring_config.py
git commit -m "feat: 博主种草评分配置段（权重/分层基准/关键词/闸门阈值）"
```

---

### Task 2: 内容垂直度分类器

**Files:**
- Create: `backend/app/services/blogger_verticality.py`
- Test: `backend/tests/test_blogger_verticality.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_blogger_verticality.py
from app.services.blogger_verticality import food_verticality, is_food_note


def _note(title="", desc="", tags=None):
    return {"title": title, "desc": desc, "tags": tags or []}


def test_is_food_note_by_title_desc_tags():
    assert is_food_note(_note(title="周末探店 这家火锅绝了"))
    assert is_food_note(_note(desc="美食打卡日记，人均 80"))
    assert is_food_note(_note(tags=["美食", "探店"]))
    assert not is_food_note(_note(title="OOTD 秋季穿搭分享"))
    assert not is_food_note(_note())  # 无法判定 → False（不计入分子）


def test_food_verticality_ratio_and_score():
    notes = [_note(title="探店打卡") for _ in range(10)] + [_note(title="穿搭分享") for _ in range(4)]
    res = food_verticality(notes)
    assert res["judged_notes"] == 14
    assert res["food_notes"] == 10
    assert abs(res["ratio"] - 10 / 14) < 1e-9
    # 71.4% 落在 60→70 与 80→100 之间线性插值区间
    assert 70 <= res["score"] <= 100
    assert res["confidence"] == "high"


def test_food_verticality_low_judged_notes_low_confidence():
    notes = [_note(title="探店打卡") for _ in range(6)] + [_note() for _ in range(10)]
    res = food_verticality(notes)
    assert res["judged_notes"] == 6
    assert res["confidence"] == "low"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_blogger_verticality.py -v`
Expected: FAIL — ModuleNotFoundError

- [ ] **Step 3: 实现 blogger_verticality.py**

```python
# backend/app/services/blogger_verticality.py
"""内容垂直度：餐饮/美食关键词分类（V1 规则版，Phase 2 可换大模型）。"""
from __future__ import annotations

from app.services.scoring_config import load_scoring_config


def _keywords() -> list[str]:
    return load_scoring_config()["verticality"]["food_keywords"]


def _note_text(note: dict) -> str:
    parts = [str(note.get("title") or ""), str(note.get("desc") or "")]
    tags = note.get("tags") or []
    parts.extend(str(t) for t in tags if isinstance(t, str))
    return " ".join(parts)


def is_food_note(note: dict) -> bool:
    """标题/正文/标签任一命中美食关键词即判定为餐饮相关；无文本则 False。"""
    text = _note_text(note).strip()
    if not text:
        return False
    return any(kw in text for kw in _keywords())


def food_verticality(notes: list[dict]) -> dict:
    """返回垂直度评分结果。复用 blogger_scoring._interpolate（升序锚点，与 C9 一致）。

    函数内 import 避免与 blogger_scoring 顶层相互导入（blogger_scoring 顶层
    会 import food_verticality，这里在调用时才取 _interpolate）。
    """
    from app.services.blogger_scoring import _interpolate

    judged = [n for n in notes if _note_text(n).strip()]
    food = sum(1 for n in judged if is_food_note(n))
    judged_count = len(judged)
    ratio = food / judged_count if judged_count else 0.0
    points = load_scoring_config()["verticality"]["points"]  # [(0.2,10),(0.4,40),(0.6,70),(0.8,100)] 升序
    score = round(_interpolate(points, ratio), 1)
    confidence = "high" if judged_count >= len(notes) * 0.8 else "low"
    return {
        "score": score,
        "confidence": confidence,
        "detail": {"food_ratio": round(ratio, 4), "food_notes": food, "judged_notes": judged_count},
    }
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_blogger_verticality.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/blogger_verticality.py backend/tests/test_blogger_verticality.py
git commit -m "feat: 美食内容垂直度分类器（关键词规则版）"
```

---

### Task 3: 种草深度评分

**Files:**
- Modify: `backend/app/services/blogger_scoring.py`
- Test: `backend/tests/test_blogger_scoring.py`（追加）

- [ ] **Step 1: 写失败测试（追加到 test_blogger_scoring.py）**

```python
def test_seeding_depth_weights_and_detail():
    from app.services.blogger_scoring import _score_seeding_depth, _tier_for

    now = datetime(2026, 8, 11, 12, 0, 0, tzinfo=CN_TZ)
    notes = [_mk(i, now - timedelta(days=i * 2), 3000, 1600, 300, 200) for i in range(30)]
    res = _score_seeding_depth(notes, fans=50000, tier=_tier_for(50000), now=now)
    assert 0 <= res["score"] <= 100
    d = res["detail"]
    assert d["collect_like_ratio"] > 0.5  # 藏/赞 > 0.5，干货结构
    assert d["comment_signal_low_conf"] is True  # 默认未开评论分析


def test_seeding_depth_comment_reweight():
    from app.services.blogger_scoring import _score_seeding_depth, _tier_for

    now = datetime(2026, 8, 11, 12, 0, 0, tzinfo=CN_TZ)
    notes = [_mk(i, now - timedelta(days=i * 2), 3000, 1600, 300, 200) for i in range(30)]
    base = _score_seeding_depth(notes, fans=50000, tier=_tier_for(50000), now=now)
    with_comments = _score_seeding_depth(
        notes, fans=50000, tier=_tier_for(50000), now=now,
        comment_analysis={"intent_ratio": 0.3, "spam_ratio": 0.05},
    )
    assert with_comments["detail"]["comment_signal_low_conf"] is False
    # 评论全权重时，高意向低水评应显著高于默认降权口径（低样本对比即可）
    assert with_comments["score"] != base["score"]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_blogger_scoring.py::test_seeding_depth_weights_and_detail -v`
Expected: FAIL — ImportError: cannot import name '_score_seeding_depth'

- [ ] **Step 3: 实现 _score_seeding_depth**

在 `backend/app/services/blogger_scoring.py` 的 `_score_sustained_operation` 之后插入：

```python
def _comment_participation(notes: list[dict]) -> float:
    """评论参与度 = 评论数 / (赞+藏+评+转) 的篇均值；互动全为 0 时取 0。"""
    ratios = []
    for n in notes:
        st = n["stats"]
        total = sum(int(st.get(k, 0) or 0) for k in ("liked", "collected", "comments", "shared"))
        if total > 0:
            ratios.append(int(st.get("comments", 0) or 0) / total)
    return statistics.fmean(ratios) if ratios else 0.0


def _map_comment_participation(ratio: float) -> float:
    """评论参与度映射（结构占位，待标定）：≥0.25→100，0.15→70，0.08→40，0→0。"""
    points = [(0.25, 100), (0.15, 70), (0.08, 40), (0.0, 0)]
    return _interpolate(points, ratio)


def _score_seeding_depth(
    notes: list[dict],
    fans: int,
    tier: dict,
    now: datetime,
    comment_analysis: dict | None = None,
) -> dict:
    """种草深度：收藏(想去)45% + 分享(安利)30% + 评论信号25%。

    收藏深度/分享扩散按粉丝分层映射；赞藏比只作展示信号与闸门红旗，不打分。
    评论分析默认关闭：评论子项用参与度近似且 confidence=low、权重 ×0.5 重归一化。
    """
    cutoff = now - timedelta(days=ANALYSIS_WINDOW_DAYS)
    recent = [n for n in notes if _parse_dt(n["published_at"]) is not None and _parse_dt(n["published_at"]) >= cutoff]
    recent = recent or notes
    if not recent or fans <= 0:
        return {"score": 0.0, "confidence": "high", "detail": {
            "collect_rate_percent": 0.0, "collect_like_ratio": 0.0, "share_rate_percent": 0.0,
            "comment_signal": 0.0, "comment_signal_low_conf": True}}

    total_collect = sum(int(n["stats"].get("collected", 0) or 0) for n in recent)
    total_share = sum(int(n["stats"].get("shared", 0) or 0) for n in recent)
    collect_like_ratios = []
    for n in recent:
        liked = int(n["stats"].get("liked", 0) or 0)
        collected = int(n["stats"].get("collected", 0) or 0)
        if liked > 0:
            collect_like_ratios.append(collected / liked)
    collect_like_ratio = statistics.median(collect_like_ratios) if collect_like_ratios else 0.0

    collect_rate_percent = (total_collect / len(recent) / fans) * 100.0
    share_rate_percent = (total_share / len(recent) / fans) * 100.0
    collect_score = _interpolate(tier["collect_rate_points"], collect_rate_percent)
    share_score = _interpolate(tier["share_rate_points"], share_rate_percent)

    comment_low_conf = comment_analysis is None
    if comment_analysis is not None:
        intent = float(comment_analysis.get("intent_ratio", 0.0))
        spam = float(comment_analysis.get("spam_ratio", 0.0))
        comment_score = max(0.0, min(100.0, intent * 100 - spam * 50))
    else:
        comment_score = _map_comment_participation(_comment_participation(recent))

    sub_weights = {"collect": 0.45, "share": 0.30, "comment": 0.25}
    if comment_low_conf:
        sub_weights["comment"] *= 0.5
    total_w = sum(sub_weights.values())
    score = (collect_score * sub_weights["collect"] + share_score * sub_weights["share"]
             + comment_score * sub_weights["comment"]) / total_w
    return {
        "score": round(score, 1),
        "confidence": "high",
        "detail": {
            "collect_rate_percent": round(collect_rate_percent, 3),
            "collect_like_ratio": round(collect_like_ratio, 3),
            "share_rate_percent": round(share_rate_percent, 3),
            "comment_signal": round(comment_score, 1),
            "comment_signal_low_conf": comment_low_conf,
        },
    }
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_blogger_scoring.py::test_seeding_depth_weights_and_detail tests/test_blogger_scoring.py::test_seeding_depth_comment_reweight -v`
Expected: PASS（2 passed）

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/blogger_scoring.py backend/tests/test_blogger_scoring.py
git commit -m "feat: 种草深度维度（收藏/分享/评论信号 + 赞藏比展示 + 评论子项降权）"
```

---

### Task 4: 稳定产出重构（中位数爆文 + 连续性/断崖）

**Files:**
- Modify: `backend/app/services/blogger_scoring.py`
- Test: `backend/tests/test_blogger_scoring.py`（追加）

- [ ] **Step 1: 写失败测试**

```python
def test_stable_output_median_viral_and_no_cv_penalty():
    from app.services.blogger_scoring import _score_stable_output

    now = datetime(2026, 8, 11, 12, 0, 0, tzinfo=CN_TZ)
    # 20 篇普通 + 6 篇爆款（互动量 >> 中位数×3），正常账号高方差但连续发布
    notes = [_mk(i, now - timedelta(days=i * 2), 800, 300, 100, 50) for i in range(20)]
    for i in range(6):
        notes[i] = _mk(i, now - timedelta(days=i * 2), 9000, 3600, 900, 600)
    res = _score_stable_output(notes, now=now)
    # 中位数×3 阈值下 6/26 ≈ 23% 命中爆文 → 高分；连续发布无空白期 → 无稳健性扣分
    assert res["score"] >= 70
    assert res["detail"]["cliff_detected"] is False
    assert res["detail"]["gap_days"] == 0


def test_stable_output_gap_and_cliff_penalize():
    from app.services.blogger_scoring import _score_stable_output

    now = datetime(2026, 8, 11, 12, 0, 0, tzinfo=CN_TZ)
    # 近 30 天只有 1 篇（前 60 天密集），且前段互动高、后段骤降
    old = [_mk(i, now - timedelta(days=70 - i * 2), 5000, 1800, 500, 300) for i in range(15)]
    new = [_mk(99, now - timedelta(days=20), 300, 100, 30, 10)]
    res = _score_stable_output(old + new, now=now)
    assert res["detail"]["gap_days"] >= 14
    assert res["score"] < 60
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_blogger_scoring.py::test_stable_output_median_viral_and_no_cv_penalty -v`
Expected: FAIL — ImportError: cannot import name '_score_stable_output'

- [ ] **Step 3: 实现 _score_stable_output**

在 `blogger_scoring.py` 中将 `_score_content_stability` 替换为：

```python
def _score_stable_output(notes: list[dict], now: datetime | None = None) -> dict:
    """稳定产出：爆文率（中位数×3，抗刷量拉高均值）×0.7 + 稳健性（连续性/断崖）×0.3。

    弃用 CV：爆款账号方差天然大，CV 会反向惩罚有爆款的账号；改为只罚中断与暴跌。
    """
    cfg = load_scoring_config()
    now = now or datetime.now(CN_TZ)
    if not notes:
        return {"score": 0.0, "confidence": "high", "detail": {"viral_ratio": 0.0, "gap_days": 0, "cliff_detected": False}}

    weighted = [_weighted(n["stats"]) for n in notes]
    median = statistics.median(weighted)
    mean = statistics.fmean(weighted)
    mult = float(cfg["viral"]["median_multiplier"])
    abs_min = int(cfg["viral"]["abs_min"])
    threshold = median * mult if median > 0 else max(mean * mult, abs_min)
    viral_count = sum(1 for w in weighted if w >= threshold)
    viral_ratio = viral_count / len(notes)
    points = cfg["viral"]["points"]  # [(0.0,0),(0.08,40),(0.1,70),(0.2,100)] 升序
    viral_score = _interpolate(points, viral_ratio)

    # 稳健性：近 30 天最长空白期 ≥ gap_days → 扣分；最新30天 vs 前60天 中位数互动跌 >50% → 扣分
    gap_days = _max_recent_gap_days(notes, now)
    cliff_detected = _interaction_cliff(notes, now, drop=float(cfg["stability"]["cliff_drop"]))
    penalty = float(cfg["stability"]["cliff_penalty"])
    robustness = 100.0 - (penalty if gap_days >= int(cfg["stability"]["gap_days"]) else 0.0) - (penalty if cliff_detected else 0.0)

    score = viral_score * 0.7 + max(0.0, robustness) * 0.3
    return {
        "score": round(score, 1),
        "confidence": "high",
        "detail": {"viral_ratio": round(viral_ratio, 4), "gap_days": gap_days, "cliff_detected": cliff_detected},
    }


def _max_recent_gap_days(notes: list[dict], now: datetime) -> int:
    """近 30 天窗口内连续无发布的最大天数；窗口内无笔记按 30 天计。"""
    cutoff = now - timedelta(days=30)
    in_window = [
        _parse_dt(n["published_at"]) for n in notes
        if _parse_dt(n["published_at"]) is not None and _parse_dt(n["published_at"]) >= cutoff
    ]
    if not in_window:
        return 30
    in_window.sort()
    max_gap = 0
    prev = cutoff
    for dt in in_window:
        gap = (dt - prev).days
        if gap > max_gap:
            max_gap = gap
        prev = dt
    tail = (now - prev).days
    return max(max_gap, tail)


def _interaction_cliff(notes: list[dict], now: datetime, drop: float = 0.5) -> bool:
    """最新30天 vs 前60天 的标准化互动中位数下降超过 drop 比例则判定断崖。"""
    std = _type_standardized(notes)
    recent, older = [], []
    for n, s in zip(notes, std):
        dt = _parse_dt(n["published_at"])
        if dt is None:
            continue
        if dt >= now - timedelta(days=30):
            recent.append(s)
        elif dt >= now - timedelta(days=90):
            older.append(s)
    if not recent or not older:
        return False
    m_recent = statistics.median(recent)
    m_older = statistics.median(older)
    return m_older > 0 and m_recent < m_older * (1 - drop)
```

在文件顶部补导入与配置引用：

```python
from app.services.scoring_config import load_scoring_config
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_blogger_scoring.py::test_stable_output_median_viral_and_no_cv_penalty tests/test_blogger_scoring.py::test_stable_output_gap_and_cliff_penalize -v`
Expected: PASS（2 passed）

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/blogger_scoring.py backend/tests/test_blogger_scoring.py
git commit -m "feat: 稳定产出重构（中位数爆文 + 连续性/断崖替代 CV）"
```

---

### Task 5: 增长趋势 + 涨粉率

**Files:**
- Modify: `backend/app/services/blogger_scoring.py`
- Test: `backend/tests/test_blogger_scoring.py`（追加）

- [ ] **Step 1: 写失败测试**

```python
def test_growth_trend_with_snapshot():
    from app.services.blogger_scoring import _score_growth_trend, _tier_for

    now = datetime(2026, 8, 11, 12, 0, 0, tzinfo=CN_TZ)
    notes = [_mk(i, now - timedelta(days=i * 2), 3000, 1200, 300, 200) for i in range(30)]
    history = [
        {"snapshot_at": (now - timedelta(days=35)).isoformat(), "fans": 45000},
        {"snapshot_at": (now - timedelta(days=5)).isoformat(), "fans": 50000},
    ]
    res = _score_growth_trend(notes, fans=50000, now=now, follower_history=history, tier=_tier_for(50000))
    # 35 天涨 11% → 月化约 9.4%，接近 T2 基准 9% → 中高分
    assert res["detail"]["has_snapshot"] is True
    assert res["detail"]["growth_rate"] > 0.05
    assert res["confidence"] in ("high", "medium")


def test_growth_trend_no_snapshot_low_conf():
    from app.services.blogger_scoring import _score_growth_trend, _tier_for

    now = datetime(2026, 8, 11, 12, 0, 0, tzinfo=CN_TZ)
    notes = [_mk(i, now - timedelta(days=i * 2), 3000, 1200, 300, 200) for i in range(30)]
    res = _score_growth_trend(notes, fans=50000, now=now, follower_history=None, tier=_tier_for(50000))
    assert res["detail"]["has_snapshot"] is False
    assert res["confidence"] == "low"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_blogger_scoring.py::test_growth_trend_with_snapshot -v`
Expected: FAIL — ImportError: cannot import name '_score_growth_trend'

- [ ] **Step 3: 实现 _score_growth_trend**

在 `blogger_scoring.py` 中新增（放在 `_score_follower_growth` 之后）：

```python
def _latest_growth_rate(history: list[dict] | None) -> float | None:
    """取最近两次快照的粉丝增长率（30 天内）；不足两次或间隔 >60 天返回 None。"""
    if not history or len(history) < 2:
        return None
    items = []
    for h in history:
        dt = _parse_dt(h.get("snapshot_at") or h.get("date") or h.get("created_at"))
        fans = int(h.get("fans", 0) or 0)
        if dt and fans > 0:
            items.append((dt, fans))
    items.sort()
    if len(items) < 2:
        return None
    (dt_prev, fans_prev), (dt_last, fans_last) = items[-2], items[-1]
    days = (dt_last - dt_prev).days
    if days <= 0 or days > 60:
        return None
    if fans_prev <= 0:
        return None
    rate = (fans_last - fans_prev) / fans_prev
    return rate * 30.0 / days  # 月化


def _score_growth_trend(
    notes: list[dict],
    fans: int,
    now: datetime,
    follower_history: list[dict] | None,
    tier: dict,
) -> dict:
    """增长趋势：有快照 → 涨粉分×0.7 + 内容趋势×0.3；无快照 → 仅内容趋势，confidence=low。

    无快照时不引入阶段分，避免与阶段判定的同源互动趋势信号重复计算（见设计 §4.5）。
    """
    std_values = _type_standardized(notes)
    trend = _score_trend(std_values, notes)
    content_score = None if trend["skipped"] else trend["score"]
    content_reason = None if not trend["skipped"] else trend["reason"]

    growth_rate = _latest_growth_rate(follower_history)
    if growth_rate is None:
        if content_score is None:
            return {"score": None, "confidence": "low", "detail": {
                "growth_rate": None, "has_snapshot": False, "trend_ratio": None,
                "reason": content_reason or "样本不足以计算内容趋势", "weight_halved": True}}
        return {"score": content_score, "confidence": "low", "detail": {
            "growth_rate": None, "has_snapshot": False, "trend_ratio": trend["ratio"],
            "reason": "无涨粉快照，仅按内容趋势计分", "weight_halved": True}}

    baseline = float(tier.get("growth_baseline", 0.08))
    points = load_scoring_config()["growth"]["points"]  # [(1.2,100),(1.0,75),(0.5,45),(0,15)]
    growth_score = _interpolate(points, growth_rate / baseline if baseline else 0.0)
    if content_score is None:
        score = growth_score
        conf = "high"
        detail = {"growth_rate": round(growth_rate, 4), "has_snapshot": True, "trend_ratio": None,
                  "reason": "内容趋势样本不足，仅按涨粉计分"}
    else:
        score = growth_score * 0.7 + content_score * 0.3
        conf = "high"
        detail = {"growth_rate": round(growth_rate, 4), "has_snapshot": True,
                  "trend_ratio": trend["ratio"], "reason": None}
    return {"score": round(score, 1), "confidence": conf, "detail": detail}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_blogger_scoring.py::test_growth_trend_with_snapshot tests/test_blogger_scoring.py::test_growth_trend_no_snapshot_low_conf -v`
Expected: PASS（2 passed）

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/blogger_scoring.py backend/tests/test_blogger_scoring.py
git commit -m "feat: 增长趋势维度（涨粉率分层基准 + 内容趋势；无快照降权标低置信）"
```
---

### Task 6: 账号阶段判定

**Files:**
- Modify: `backend/app/services/blogger_scoring.py`
- Test: `backend/tests/test_blogger_scoring.py`（追加）

- [ ] **Step 1: 写失败测试**

```python
def test_classify_stage_with_snapshot_growth():
    from app.services.blogger_scoring import _classify_stage

    now = datetime(2026, 8, 11, 12, 0, 0, tzinfo=CN_TZ)
    notes = [_mk(i, now - timedelta(days=i * 2), 3000, 1200, 300, 200) for i in range(30)]
    history = [
        {"snapshot_at": (now - timedelta(days=35)).isoformat(), "fans": 45000},
        {"snapshot_at": (now - timedelta(days=5)).isoformat(), "fans": 50000},
    ]
    res = _classify_stage(fans=50000, notes=notes, now=now, follower_history=history)
    assert res["label"] in ("成长", "成熟")
    assert res["confidence"] in ("high", "medium")


def test_classify_stage_no_snapshot_low_conf():
    from app.services.blogger_scoring import _classify_stage

    now = datetime(2026, 8, 11, 12, 0, 0, tzinfo=CN_TZ)
    notes = [_mk(i, now - timedelta(days=i * 2), 3000, 1200, 300, 200) for i in range(30)]
    res = _classify_stage(fans=2000, notes=notes, now=now, follower_history=None)
    assert res["confidence"] == "low"
    assert res["label"] == "冷启动"  # 粉丝 < 5000


def test_classify_stage_decline():
    from app.services.blogger_scoring import _classify_stage

    now = datetime(2026, 8, 11, 12, 0, 0, tzinfo=CN_TZ)
    # 最新笔记 80 天前 → 停更倾向
    notes = [_mk(i, now - timedelta(days=80 + i * 2), 3000, 1200, 300, 200) for i in range(10)]
    history = [
        {"snapshot_at": (now - timedelta(days=40)).isoformat(), "fans": 52000},
        {"snapshot_at": (now - timedelta(days=5)).isoformat(), "fans": 50000},
    ]
    res = _classify_stage(fans=50000, notes=notes, now=now, follower_history=history)
    assert res["label"] == "衰退"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_blogger_scoring.py::test_classify_stage_with_snapshot_growth -v`
Expected: FAIL — ImportError: cannot import name '_classify_stage'

- [ ] **Step 3: 实现 _classify_stage**

在 `blogger_scoring.py` 中新增（放在 `_score_growth_trend` 之后）：

```python
def _weekly_notes(notes: list[dict], now: datetime) -> float:
    cutoff = now - timedelta(days=90)
    recent = [n for n in notes if _parse_dt(n["published_at"]) is not None and _parse_dt(n["published_at"]) >= cutoff]
    return round(len(recent) / 13.0, 2)  # 90 天 ≈ 13 周


def _classify_stage(fans: int, notes: list[dict], now: datetime, follower_history: list[dict] | None) -> dict:
    """账号阶段：冷启动 / 成长 / 成熟 / 衰退。独立输出标签，不参与加权。

    有 ≥2 次快照 → 涨粉率 vs 分层基准 + 更新频率，置信 high/medium；
    无快照 → 粉丝量级 + 更新频率 + 互动趋势推断，置信度恒为 low。
    """
    cfg = load_scoring_config()
    tier = _tier_for(fans)
    baseline = float(tier.get("growth_baseline", 0.08))
    weekly = _weekly_notes(notes, now)
    growth_rate = _latest_growth_rate(follower_history)
    latest_dt = None
    for n in notes:
        dt = _parse_dt(n["published_at"])
        if dt and (latest_dt is None or dt > latest_dt):
            latest_dt = dt
    stale = latest_dt is not None and (now - latest_dt).days > int(cfg["gate"]["stale_days"])

    if growth_rate is not None:
        if growth_rate <= 0 or (growth_rate < baseline * 0.3 and weekly < 1.0):
            label, conf = "衰退", "medium"
        elif growth_rate >= baseline:
            label, conf = "成长", "high"
        elif fans >= 10000 and weekly >= 1.0:
            label, conf = "成熟", "medium"
        else:
            label, conf = "冷启动", "medium"
        if stale and label in ("成长", "成熟"):
            label, conf = "衰退", "medium"
        evidence = [f"近30天涨粉 {growth_rate * 100:.1f}%", f"周均发布 {weekly}"]
    else:
        # 无快照：仅推断，恒 low
        if stale:
            label = "衰退"
        elif fans < int(cfg["stage"]["cold_start_fans"]):
            label = "冷启动"
        elif weekly >= 1.0 and fans >= 100000:
            label = "成熟"
        else:
            label = "成长" if weekly >= 1.0 else "冷启动"
        conf = "low"
        evidence = [f"粉丝 {fans}", f"周均发布 {weekly}", "无涨粉快照，阶段为推断"]
    return {"label": label, "confidence": conf, "evidence": evidence}
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_blogger_scoring.py::test_classify_stage_with_snapshot_growth tests/test_blogger_scoring.py::test_classify_stage_no_snapshot_low_conf tests/test_blogger_scoring.py::test_classify_stage_decline -v`
Expected: PASS（3 passed）

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/blogger_scoring.py backend/tests/test_blogger_scoring.py
git commit -m "feat: 账号阶段判定（冷启动/成长/成熟/衰退；无快照恒 low 置信）"
```

---

### Task 7: 闸门升级（赞藏比 / 且关系 / 叠加惩罚说明）

**Files:**
- Modify: `backend/app/services/blogger_scoring.py`
- Test: `backend/tests/test_blogger_scoring.py`（追加）

- [ ] **Step 1: 写失败测试**

```python
def test_gate_collect_like_inversion_blocks():
    now = datetime(2026, 8, 11, 12, 0, 0, tzinfo=CN_TZ)
    # 高赞低藏：赞藏比中位数 < 0.2，且篇均收藏/粉丝极低 → 刷量嫌疑闸门
    notes = [_mk(i, now - timedelta(days=i * 2), 5000, 50, 10, 2) for i in range(40)]
    res = score_blogger(notes, follower_count=50000, total_notes=40, now=now)
    assert res["overall"] is None
    assert res["overall_score_suppressed"] is True
    assert res["decision"]["recommendation"] == "not_recommended"
    assert any(a["type"] == "fake_engagement" and a["level"] == "block" for a in res["anomalies"])


def test_gate5_growth_spike_requires_interaction_drop():
    from app.services.blogger_scoring import _growth_anomaly

    now = datetime(2026, 8, 11, 12, 0, 0, tzinfo=CN_TZ)
    # 纯涨粉 25% 但互动率未下降 → 不触发红旗
    assert _growth_anomaly(growth_rate=0.25, interaction_drop=0.05, fans=5000) is None
    # 涨粉 25% 且互动率下降 30% → 触发
    flag = _growth_anomaly(growth_rate=0.25, interaction_drop=0.30, fans=5000)
    assert flag is not None and flag["type"] == "growth_anomaly"
    # T1 小账号放大阈值：涨粉 25% 但 < 35% 不触发
    assert _growth_anomaly(growth_rate=0.25, interaction_drop=0.30, fans=2000) is None
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_blogger_scoring.py::test_gate_collect_like_inversion_blocks -v`
Expected: FAIL — KeyError: 'overall_score_suppressed'（score_blogger 尚无该字段）

- [ ] **Step 3: 实现闸门升级**

在 `blogger_scoring.py` 中新增 `_growth_anomaly` 与 `_collect_like_inversion_hit`：

```python
def _growth_anomaly(growth_rate: float, interaction_drop: float, fans: int) -> dict | None:
    """闸门 5：涨粉异常 = 增幅超阈值 且 同期互动率下降（「且」关系）。

    T1（<1w 粉）阈值放宽到 t1_growth_spike，避免小爆款有机增长误报。
    """
    cfg = load_scoring_config()["gate"]
    spike = float(cfg["t1_growth_spike"]) if fans < 10000 else float(cfg["growth_spike"])
    if growth_rate > spike and interaction_drop >= float(cfg["growth_interaction_drop"]):
        return {"type": "growth_anomaly", "level": "warn",
                "detail": f"粉丝增幅 {growth_rate * 100:.0f}% 且互动率下降，疑似注水"}
    return None


def _collect_like_inversion_hit(notes: list[dict], fans: int, tier: dict) -> bool:
    """刷量辅助信号：赞藏比中位数 <0.2 且 篇均收藏/粉丝 低于该层最低健康线。"""
    cfg = load_scoring_config()["gate"]
    ratios = []
    for n in notes:
        liked = int(n["stats"].get("liked", 0) or 0)
        collected = int(n["stats"].get("collected", 0) or 0)
        if liked > 0:
            ratios.append(collected / liked)
    if not ratios:
        return False
    median_ratio = statistics.median(ratios)
    if median_ratio >= float(cfg["collect_like_ratio_floor"]):
        return False
    collect_rate_percent = sum(int(n["stats"].get("collected", 0) or 0) for n in notes) / len(notes) / fans * 100.0
    return collect_rate_percent < float(tier.get("min_healthy_rate", 1.0))
```

> **闸门 4（发布停滞）为有意叠加惩罚**：`>60 天` 已在持续经营维度让新鲜度分归零，等级再降一档；实现时不要因感觉重复扣分而去掉等级降档。

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_blogger_scoring.py::test_gate_collect_like_inversion_blocks tests/test_blogger_scoring.py::test_gate5_growth_spike_requires_interaction_drop -v`
Expected: FAIL 依旧（score_blogger 尚未接入，Task 9 整合后转 PASS）——若本任务需要全绿，则先只跑 `test_gate5_growth_spike_requires_interaction_drop`

说明：`test_gate_collect_like_inversion_blocks` 依赖 Task 9 的 `score_blogger` 整合（`overall_score_suppressed` 字段与闸门 2 接入 `_collect_like_inversion_hit`），在本任务可先跑 `test_gate5_growth_spike_requires_interaction_drop` 验证 `_growth_anomaly`；集成测试在 Task 9 全绿。

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/blogger_scoring.py backend/tests/test_blogger_scoring.py
git commit -m "feat: 闸门升级（赞藏比倒挂辅助判定、涨粉异常改且关系、T1 阈值放宽）"
```

---

### Task 8: 置信度汇总 + 决策输出（recommendation 枚举 / score_suppressed）

**Files:**
- Modify: `backend/app/services/blogger_scoring.py`
- Test: `backend/tests/test_blogger_scoring.py`（追加）

- [ ] **Step 1: 写失败测试**

```python
def test_overall_confidence_single_noncore_low():
    from app.services.blogger_scoring import _overall_confidence

    dims = {
        "seeding_depth": {"confidence": "high"},
        "verticality": {"confidence": "high"},
        "stable_output": {"confidence": "high"},
        "sustained_operation": {"confidence": "high"},
        "growth_trend": {"confidence": "low"},  # 单个非核心维度 low
    }
    assert _overall_confidence(dims, coverage_conf="high") == "medium"


def test_overall_confidence_seeding_low():
    from app.services.blogger_scoring import _overall_confidence

    dims = {"seeding_depth": {"confidence": "low"}, "verticality": {"confidence": "high"},
            "stable_output": {"confidence": "high"}, "sustained_operation": {"confidence": "high"},
            "growth_trend": {"confidence": "high"}}
    assert _overall_confidence(dims, coverage_conf="high") == "low"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_blogger_scoring.py::test_overall_confidence_single_noncore_low -v`
Expected: FAIL — ImportError: cannot import name '_overall_confidence'

- [ ] **Step 3: 实现 _overall_confidence**

在 `blogger_scoring.py` 中新增：

```python
_CONF_RANK = {"high": 0, "medium": 1, "low": 2}
_NONCORE = {"verticality", "stable_output", "sustained_operation", "growth_trend"}


def _overall_confidence(dimensions: dict, coverage_conf: str) -> str:
    """通用置信度汇总：min(覆盖率可信度, min(五维置信度))。

    特例：low 仅来自单个非核心维度，且种草深度非 low 时，整体取 medium
    （避免单一弱信号过度拉低）。覆盖率 low 已在闸门 1 拦截，此处只会是 high/medium。
    """
    if coverage_conf == "low":
        return "low"
    dim_confs = [d.get("confidence", "high") for d in dimensions.values() if d.get("score") is not None]
    if not dim_confs:
        return "low"
    min_dim = min(dim_confs, key=lambda c: _CONF_RANK[c])
    low_dims = [k for k, d in dimensions.items() if d.get("confidence") == "low"]
    if min_dim == "low" and len(low_dims) == 1 and low_dims[0] in _NONCORE and dimensions["seeding_depth"].get("confidence") != "low":
        return "medium"
    return min([coverage_conf, min_dim], key=lambda c: _CONF_RANK[c])
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_blogger_scoring.py::test_overall_confidence_single_noncore_low tests/test_blogger_scoring.py::test_overall_confidence_seeding_low -v`
Expected: PASS（2 passed）

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/blogger_scoring.py backend/tests/test_blogger_scoring.py
git commit -m "feat: 通用置信度汇总规则（min + 单非核心 low 特例）"
```

---

### Task 9: score_blogger 整合（五维输出 + recommendation + score_suppressed + 兼容字段）

**Files:**
- Modify: `backend/app/services/blogger_scoring.py`（重写 `score_blogger`）
- Modify: `backend/tests/test_blogger_scoring.py`（更新既有断言适配新结构）
- Test: `backend/tests/test_blogger_scoring.py`（全量）

- [ ] **Step 1: 更新既有测试断言（新结构字段）**

`test_fake_engagement_blocks` 中 `res["overall"] is None` 保留；新增断言：

```python
    assert res["overall_score_suppressed"] is True
    assert res["decision"]["recommendation"] == "not_recommended"
    assert res["decision"]["low_quality"] is True
```

`test_high_quality_account` 中 `res["overall"]["score"] >= 70` 保留；追加：

```python
    assert res["stage"]["label"] in ("成长", "成熟")
    assert res["decision"]["recommendation"] in ("priority", "ok", "caution")
    assert set(res["dimensions"].keys()) == {
        "seeding_depth", "verticality", "stable_output", "sustained_operation", "growth_trend",
    }
```

`test_low_coverage_no_score` 中 `res["overall"] is None` 保留；追加：

```python
    assert res["decision"]["recommendation"] == "insufficient_data"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_blogger_scoring.py -v`
Expected: FAIL（新字段缺失 / dimensions 键名不匹配）

- [ ] **Step 3: 改造 _tier_for 以合并新配置字段**

将 `_tier_for` 替换为（保留旧 `points`/`min_healthy` 供 `_score_interaction_quality` 使用，同时暴露新字段）：

```python
def _tier_for(fans: int) -> dict:
    """粉丝分层：从 scoring_config 读取，并合并旧 TIERS 的 points/min_healthy。"""
    tiers = load_scoring_config()["tiers"]
    for key, t in tiers.items():
        if fans >= int(t["min"]) and (t.get("max") is None or fans < int(t["max"])):
            merged = dict(t)
            legacy = TIERS.get(key, {})
            merged.setdefault("points", legacy.get("points", []))
            merged.setdefault("min_healthy", legacy.get("min_healthy", t.get("min_healthy_rate", 0.0)))
            return merged
    merged = dict(tiers["T1"])
    merged.setdefault("points", TIERS["T1"].get("points", []))
    merged.setdefault("min_healthy", TIERS["T1"].get("min_healthy", tiers["T1"].get("min_healthy_rate", 0.0)))
    return merged
```

- [ ] **Step 4: 重写 score_blogger**

将 `score_blogger` 整体替换为：

```python
def score_blogger(
    notes: list[dict],
    follower_count: int = 0,
    total_notes: int = 0,
    now: datetime | None = None,
    sampled: bool = False,
    coverage_denominator: int | None = None,
    follower_history: list[dict] | None = None,
    comment_analysis: dict | None = None,
) -> dict:
    """运行种草能力五维评分，返回可直接落库/展示的结果结构。"""
    now = now or datetime.now(CN_TZ)
    if now.tzinfo is None:
        now = now.replace(tzinfo=CN_TZ)

    real = _real_notes(notes)
    fetched = len(real)
    sample_size = coverage_denominator if coverage_denominator is not None else total_notes
    coverage_rate = fetched / sample_size if sample_size else 0.0
    if coverage_rate >= 0.8 and fetched >= 30:
        coverage_conf = "high"
    elif coverage_rate >= 0.5 and fetched >= 15:
        coverage_conf = "medium"
    else:
        coverage_conf = "low"

    base = {
        "note_count": len(notes),
        "real_note_count": fetched,
        "sampled": bool(sampled),
        "coverage": {
            "total_notes": total_notes,
            "sample_size": sample_size,
            "fetched_notes": fetched,
            "coverage_rate": round(coverage_rate, 4),
        },
        "confidence": coverage_conf,
        "dimensions": {},
        "overall": None,
        "overall_score_suppressed": False,
        "grass_planting": None,
        "growth_potential": None,
        "decision": None,
        "stage": None,
        "follower_history": _summarize_follower_history(follower_history),
        "anomalies": [],
        "insights": [],
        "timeline": _build_timeline(real),
        "notes": sorted(real, key=lambda n: n.get("published_at") or "", reverse=True),
    }

    if sampled and sample_size:
        base["insights"].append(f"抽样分析：共 {total_notes} 篇，均匀抽取 {sample_size} 篇真实详情")

    # 闸门 1：覆盖率不达标 → insufficient_data（不评分、不判定低质）
    if coverage_conf == "low":
        base["insights"].append("数据不足，暂不评分")
        base["decision"] = {
            "recommendation": "insufficient_data", "summary": "真实样本覆盖率不足，暂不评分",
            "reasons": [f"已验证样本 {fetched}/{sample_size or 0}，覆盖率 {coverage_rate:.0%}"],
            "red_flags": [], "low_quality": False,
        }
        return base

    tier = _tier_for(follower_count)
    gate_cfg = load_scoring_config()["gate"]
    # 兼容字段（前端过渡期保留；新前端切走后移除）
    grass = _score_grass_planting(real, follower_count, tier)
    growth = _score_growth_potential(real, follower_count, now, follower_history)
    base["grass_planting"] = grass
    base["growth_potential"] = growth

    # 五维评分
    seeding = _score_seeding_depth(real, follower_count, tier, now, comment_analysis=comment_analysis)
    vert = food_verticality(real)
    stable = _score_stable_output(real, now)
    sustained = _score_sustained_operation(real, now)
    growth_trend = _score_growth_trend(real, follower_count, now, follower_history, tier)

    dimensions = {
        "seeding_depth": {"score": seeding["score"], "confidence": seeding["confidence"], "detail": seeding["detail"]},
        "verticality": {"score": vert["score"], "confidence": vert["confidence"], "detail": vert["detail"]},
        "stable_output": {"score": stable["score"], "confidence": stable["confidence"], "detail": stable["detail"]},
        "sustained_operation": {"score": sustained["score"], "confidence": "high", "detail": {"weekly_notes": sustained["weekly_notes"], "freshness_days": sustained["freshness_days"]}},
        "growth_trend": {"score": growth_trend["score"], "confidence": growth_trend["confidence"], "detail": growth_trend["detail"]},
    }
    base["dimensions"] = dimensions

    # 权重归一化：被跳过/降权的维度处理
    weights = dict(load_scoring_config()["weights"])
    if growth_trend["score"] is None:
        del weights["growth_trend"]
        base["insights"].append(growth_trend["detail"].get("reason") or "增长趋势样本不足，跳过")
    elif growth_trend["confidence"] == "low":
        weights["growth_trend"] *= 0.5  # 无快照降权
    total_weight = sum(weights.values())
    overall = sum(dimensions[k]["score"] * weights[k] for k in weights if dimensions[k].get("score") is not None) / total_weight
    overall = round(overall, 1)
    level, desc = _level_for(overall)

    # 闸门 2：刷量嫌疑（含赞藏比倒挂辅助）
    likes = [int(n["stats"].get("liked", 0) or 0) for n in real]
    median_likes = statistics.median(likes) if likes else 0.0
    fake_hits = 0
    if median_likes > 0:
        for n in real:
            st = n["stats"]
            liked = int(st.get("liked", 0) or 0)
            extra = int(st.get("collected", 0) or 0) + int(st.get("comments", 0) or 0) + int(st.get("shared", 0) or 0)
            if liked >= median_likes * 3 and (extra / liked if liked else 0) < float(gate_cfg["fake_extra_ratio"]):
                fake_hits += 1
    fake_ratio = fake_hits / len(real) if real else 0.0
    collect_inversion = _collect_like_inversion_hit(real, follower_count, tier)
    if fake_ratio > float(gate_cfg["fake_ratio"]) or collect_inversion:
        base["anomalies"].append({"type": "fake_engagement", "level": "block", "detail": "疑似刷量（赞藏倒挂或互动结构异常）"})
        base["overall"] = None
        base["overall_score_suppressed"] = True
        base["grass_planting"] = None
        base["growth_potential"] = None
        base["decision"] = {
            "recommendation": "not_recommended", "summary": "疑似刷量，不建议合作",
            "reasons": ["互动结构异常（高赞低藏或赞藏比倒挂）"], "red_flags": [
                {"type": "fake_engagement", "level": "block", "detail": "疑似刷量"}],
            "low_quality": True,
        }
        base["insights"].append("疑似刷量，不建议合作")
        return base

    # 阶段判定（独立标签）
    stage = _classify_stage(follower_count, real, now, follower_history)
    base["stage"] = stage

    # 闸门 3：粉丝互动倒挂
    iq_rate = _score_interaction_quality(real, follower_count, tier, now)["rate"]
    if iq_rate < float(tier.get("min_healthy", tier.get("min_healthy_rate", 0.0))):
        base["anomalies"].append({"type": "interaction_inversion", "level": "cap", "detail": "粉丝互动倒挂"})
        level = "待观察"
        desc = "粉丝互动倒挂，等级封顶待观察"

    # 闸门 4：发布停滞（有意叠加：维度已在新鲜度吃亏，等级再降一档）
    if sustained["freshness_days"] is not None and sustained["freshness_days"] > int(gate_cfg["stale_days"]):
        base["anomalies"].append({"type": "stale", "level": "downgrade", "detail": "最新笔记发布时间超过60天"})
        level = _downgrade_level(level)
        base["insights"].append("账号可能已停更")

    # 闸门 5：涨粉异常（且关系，T1 放宽）
    if growth_rate := _latest_growth_rate(follower_history):
        std_now = _type_standardized(real)
        recent_std = [s for n, s in zip(real, std_now) if _parse_dt(n["published_at"]) is not None and _parse_dt(n["published_at"]) >= now - timedelta(days=30)]
        older_std = [s for n, s in zip(real, std_now) if _parse_dt(n["published_at"]) is not None and now - timedelta(days=90) <= _parse_dt(n["published_at"]) < now - timedelta(days=30)]
        m_recent = statistics.median(recent_std) if recent_std else 0.0
        m_older = statistics.median(older_std) if older_std else 0.0
        interaction_drop = max(0.0, 1.0 - (m_recent / m_older if m_older > 0 else 0.0))
        flag = _growth_anomaly(growth_rate, interaction_drop, follower_count)
        if flag:
            base["anomalies"].append(flag)
            base["insights"].append(flag["detail"])

    # 合作建议（严格互斥顺序判定）
    recommendation, rec_summary = _recommendation(overall, level, stage, base["anomalies"])
    base["overall"] = {"score": overall, "level": level, "description": desc, "score_suppressed": False}
    base["confidence"] = _overall_confidence(dimensions, coverage_conf)
    base["decision"] = {
        "recommendation": recommendation,
        "summary": rec_summary,
        "reasons": _build_reasons(dimensions, stage),
        "red_flags": [{"type": a["type"], "level": a["level"], "detail": a["detail"]} for a in base["anomalies"]],
        "low_quality": False,
    }
    base["insights"].append(f"综合评分 {overall}，等级：{level}；阶段：{stage['label']}")
    return base
```

同时新增辅助函数（放在 `score_blogger` 之前）：

```python
def _recommendation(overall: float, level: str, stage: dict, anomalies: list[dict]) -> tuple[str, str]:
    """合作建议：priority / ok / caution 三档（insufficient/not_recommended 已提前返回）。"""
    red_flag_types = {a["type"] for a in anomalies}
    has_any_flag = bool(red_flag_types)
    stage_ok = stage["label"] in ("成长", "成熟") and stage["confidence"] != "low"
    if overall >= 70 and not has_any_flag and stage_ok:
        return "priority", "美食垂直度高、种草能力强，处于成长/成熟期，适合优先建联"
    if overall >= 55 and not has_any_flag:
        return "ok", "种草能力在线且无红旗，可以合作"
    return "caution", "存在非致命红旗或分数偏低，建议谨慎评估"


def _build_reasons(dimensions: dict, stage: dict) -> list[str]:
    reasons = []
    v = dimensions["verticality"]["detail"]
    if v.get("food_ratio", 0) >= 0.6:
        reasons.append(f"美食内容占比 {v['food_ratio'] * 100:.0f}%")
    sd = dimensions["seeding_depth"]["detail"]
    if sd.get("collect_rate_percent", 0) > 0:
        reasons.append(f"篇均收藏率 {sd['collect_rate_percent']:.2f}%")
    gt = dimensions["growth_trend"]["detail"]
    if gt.get("has_snapshot") and gt.get("growth_rate") is not None:
        reasons.append(f"近30天涨粉 {gt['growth_rate'] * 100:.1f}%")
    reasons.append(f"账号阶段：{stage['label']}")
    return reasons
```

在文件顶部补导入：

```python
from app.services.blogger_verticality import food_verticality
```

> `_score_content_stability` / `_score_trend` 中仍被 `_score_growth_trend` 使用的保留；`_score_content_stability` 不再被 `score_blogger` 调用，保留供旧测试过渡或删除（建议保留到旧引擎下线 Task 11 一起清理）。

- [ ] **Step 5: 全量跑测试并修复**

Run: `cd backend && python -m pytest tests/test_blogger_scoring.py tests/test_blogger_verticality.py tests/test_scoring_config.py -v`
Expected: 全绿（含新结构断言）。若 `test_grass_growth_scores_present` 断言旧 `decision.status == "ok"` 失败，将其更新为：

```python
    assert res["decision"]["recommendation"] in ("priority", "ok", "caution")
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/blogger_scoring.py backend/tests/test_blogger_scoring.py
git commit -m "feat: score_blogger 整合为种草五维输出（recommendation/score_suppressed/stage/置信度汇总）"
```

---

### Task 10: 评论增强（可选开关）+ 任务运行器接入

**Files:**
- Create: `backend/app/services/blogger_comments.py`
- Modify: `backend/app/services/analysis_task_runner.py`
- Modify: `backend/app/api/v1/notes.py`（`AnalysisTaskCreateRequest` 加 `with_comments`）
- Test: `backend/tests/test_blogger_comments.py`

- [ ] **Step 1: 写失败测试（纯函数 analyze_comments）**

```python
# backend/tests/test_blogger_comments.py
from app.services.blogger_comments import analyze_comments


def test_analyze_comments_intent_spam_negative():
    comments = [
        {"content": "这家店在哪呀 人均多少"},
        {"content": "好吃吗 想周末去试试"},
        {"content": "太棒了 学习了 支持"},
        {"content": "广告吧 取关了"},
        {"content": "求地址 求菜单"},
    ]
    res = analyze_comments(comments)
    assert res["intent_ratio"] >= 0.4
    assert res["spam_ratio"] >= 0.1
    assert res["negative_ratio"] >= 0.1


def test_analyze_comments_empty():
    res = analyze_comments([])
    assert res["intent_ratio"] == 0.0
    assert res["spam_ratio"] == 0.0
    assert res["negative_ratio"] == 0.0
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_blogger_comments.py -v`
Expected: FAIL — ModuleNotFoundError

- [ ] **Step 3: 实现 blogger_comments.py**

```python
# backend/app/services/blogger_comments.py
"""评论增强（可选）：意向词/水评/负面信号规则分析。"""
from __future__ import annotations

from app.services.scoring_config import load_scoring_config


def analyze_comments(comments: list[dict]) -> dict:
    """输入标准化评论列表（含 content），返回意向/水评/负面占比。"""
    cfg = load_scoring_config()["comments"]
    intent_kw = cfg["intent_keywords"]
    spam_kw = cfg["spam_keywords"]
    neg_kw = cfg["negative_keywords"]
    texts = [str(c.get("content") or "") for c in comments]
    if not texts:
        return {"intent_ratio": 0.0, "spam_ratio": 0.0, "negative_ratio": 0.0, "sample": 0}
    intent = sum(1 for t in texts if any(k in t for k in intent_kw))
    spam = sum(1 for t in texts if any(k in t for k in spam_kw))
    neg = sum(1 for t in texts if any(k in t for k in neg_kw))
    n = len(texts)
    return {
        "intent_ratio": round(intent / n, 4),
        "spam_ratio": round(spam / n, 4),
        "negative_ratio": round(neg / n, 4),
        "sample": n,
    }


async def collect_comments(crawler, notes: list[dict], note_limit: int | None = None, per_note: int | None = None) -> dict | None:
    """抓取代表性笔记（爆文 + 最新 + 随机）的评论并分析；失败降级返回 None。

    返回结构供 score_blogger 的 comment_analysis 使用：
    {"intent_ratio": float, "spam_ratio": float, "negative_ratio": float}
    """
    import asyncio
    import random

    cfg = load_scoring_config()["comments"]
    note_limit = note_limit or int(cfg["note_limit"])
    per_note = per_note or int(cfg["per_note"])
    if not notes:
        return None
    weighted = [(_weighted_for_comments(n), n) for n in notes]
    weighted.sort(key=lambda x: x[0], reverse=True)
    picked = [n for _, n in weighted[: max(3, note_limit // 2)]]
    rest = [n for _, n in weighted[max(3, note_limit // 2):]]
    if rest:
        picked.extend(random.sample(rest, min(note_limit - len(picked), len(rest))))
    all_comments: list[dict] = []
    for n in picked[:note_limit]:
        note_id = n.get("platform_note_id") or n.get("id") or ""
        token = n.get("xsec_token", "")
        if not note_id:
            continue
        url = f"https://www.xiaohongshu.com/explore/{note_id}"
        if token:
            url += f"?xsec_token={token}&xsec_source=pc_user"
        try:
            result = await asyncio.to_thread(crawler.get_comments, url)
        except Exception:
            continue
        if not result or not result.success:
            continue
        items = (result.data or []) if isinstance(result.data, list) else []
        all_comments.extend(items[:per_note])
        await asyncio.sleep(0.3)  # 风控节奏
    if not all_comments:
        return None
    return analyze_comments(all_comments)


def _weighted_for_comments(note: dict) -> int:
    st = note.get("stats") or {}
    return (int(st.get("liked", 0) or 0) + int(st.get("collected", 0) or 0) * 4
            + int(st.get("comments", 0) or 0) * 5 + int(st.get("shared", 0) or 0) * 6)
```

- [ ] **Step 4: runner 接入 with_comments**

在 `backend/app/services/analysis_task_runner.py` 的 `run_analysis_task` 中，`score_blogger(...)` 调用前插入（若任务带评论开关）：

```python
        comment_analysis = None
        if getattr(current_task, "with_comments", False) and real_notes:
            try:
                from app.services.blogger_comments import collect_comments

                comment_analysis = await collect_comments(worker, real_notes)
                if comment_analysis is None:
                    logger.warning("评论抓取失败或为空，回退到无评论信号 task=%s", task_id)
            except Exception as exc:
                logger.warning("评论分析失败，降级 task=%s: %s", task_id, exc)
                comment_analysis = None
```

并把 `score_blogger(...)` 调用追加参数 `comment_analysis=comment_analysis`。

- [ ] **Step 5: 模型/接口支持 with_comments**

`backend/app/models/analysis_task.py` 的 `BloggerAnalysisTask` 增加列：

```python
    with_comments: Mapped[bool] = mapped_column(sa.Boolean, default=False, server_default=sa.text("false"))
```

`backend/app/api/v1/notes.py` 的 `AnalysisTaskCreateRequest` 增加字段：

```python
    with_comments: bool = False
```

创建任务处透传：`BloggerAnalysisTask(..., with_comments=body.with_comments)`。

> 该列需跑一次迁移（项目用 Alembic 则新增迁移；若为 create_all 模式则重启自动建列，见 `backend/app/core/database.py`）。

- [ ] **Step 6: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_blogger_comments.py -v`
Expected: PASS（2 passed）

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/blogger_comments.py backend/app/services/analysis_task_runner.py backend/app/api/v1/notes.py backend/app/models/analysis_task.py backend/tests/test_blogger_comments.py
git commit -m "feat: 可选评论增强（意向/水评/负面信号）+ 任务运行器接入"
```

---

### Task 11: 旧引擎两阶段下线 — 阶段 1（410 + 埋点）

**Files:**
- Modify: `backend/app/api/v1/notes.py`（同步分析接口）

- [ ] **Step 1: 同步接口改为 410 + 访问埋点**

将 `analyze_user_notes` 函数体整体替换为：

```python
@router.post("/users/{user_id}/analysis")
async def analyze_user_notes_deprecated(
    user_id: str,
    body: UserAnalysisRequest | None = None,
    user: User = Depends(get_current_user),
):
    """[已下线] 同步分析接口：迁移到 POST /users/{user_id}/analysis-tasks。

    阶段 1：保留入口，记录访问日志并返回 410，观察一个发布周期确认零调用后
    阶段 2 物理删除（含 xhs_analysis.py 与 test_xhs_analysis.py）。
    """
    import logging

    logger = logging.getLogger("crawler.analysis_deprecated")
    logger.warning("deprecated sync analysis called user_id=%s nickname=%s", user_id, body.nickname if body else "")
    raise HTTPException(
        status_code=410,
        detail="该接口已下线，请改用 POST /api/v1/notes/users/{user_id}/analysis-tasks（异步任务）",
    )
```

同时删除 `_ANALYSIS_CACHE`、`_analysis_cache_get/_set`、`_ANALYSIS_CACHE_TTL`、`UserAnalysisRequest` 的使用引用（`UserAnalysisRequest` 类保留定义供 410 函数签名兼容，阶段 2 一并删除）。

- [ ] **Step 2: 确认 xhs_analysis.py 不再被引用**

Run: `cd backend && python -c "import ast, pathlib; [print(p) for p in pathlib.Path('app').rglob('*.py') for t in ast.parse(p.read_text(encoding='utf-8')).body if isinstance(t, ast.ImportFrom) and any(a.name == 'xhs_analysis' for a in t.names)]"`
Expected: 无输出（`notes.py` 已不再 import `xhs_analysis`；`tests/test_xhs_analysis.py` 仍引用属预期，阶段 2 删除）

- [ ] **Step 3: 运行后端相关测试**

Run: `cd backend && python -m pytest tests/test_blogger_scoring.py tests/test_scoring_config.py tests/test_blogger_verticality.py tests/test_blogger_comments.py -v`
Expected: 全绿

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/v1/notes.py
git commit -m "feat: 同步分析接口下线阶段1（410 + 访问埋点，观察期后删除）"
```

> **阶段 2（观察 1–2 周、确认零调用后，作为单独任务执行）**：删除 `backend/app/services/xhs_analysis.py`、`backend/tests/test_xhs_analysis.py`、`UserAnalysisRequest` 与 410 接口本体，同步更新 SPEC-CRAWLER.md §11 状态。

---


---

### Task 11b: 分析任务列表端点（批量筛选支撑）

**Files:**
- Modify: `backend/app/api/v1/notes.py`（新增只读列表端点）
- Test: `backend/tests/test_analysis_task_list.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_analysis_task_list.py
from fastapi.testclient import TestClient


def test_list_analysis_tasks_requires_auth_and_filters(client: TestClient, auth_headers: dict, db_session):
    # 该测试依赖现有 fixtures（client/auth_headers/db_session，见 tests/conftest.py）
    # 创建一条成功任务后查询列表
    from app.models.analysis_task import BloggerAnalysisTask
    from app.core.database import async_session_factory

    # 若 conftest 无现成 fixture，则按项目既有接口测试模式补；此处验证端点存在即可
    res = client.get("/api/v1/notes/analysis-tasks", headers=auth_headers)
    assert res.status_code == 200
    body = res.json()
    assert "items" in body
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_analysis_task_list.py -v`
Expected: FAIL — 404（端点不存在）

- [ ] **Step 3: 实现列表端点**

在 `notes.py` 中 `get_analysis_task` 之前新增：

```python
@router.get("/analysis-tasks")
async def list_analysis_tasks(
    status: str | None = None,
    limit: int = 100,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """只读列表：供批量筛选视图拉取成功/部分结果，按完成时间倒序。"""
    from sqlalchemy import select

    stmt = select(BloggerAnalysisTask).where(BloggerAnalysisTask.user_id == user.id)
    if status:
        stmt = stmt.where(BloggerAnalysisTask.status == status)
    stmt = stmt.order_by(BloggerAnalysisTask.finished_at.desc().nulls_last()).limit(min(max(limit, 1), 500))
    rows = (await db.execute(stmt)).scalars().all()
    return {"items": [_task_payload(t) for t in rows]}
```

> `_task_payload` 已存在于 notes.py（`get_analysis_task` 使用），返回结构含 `xhs_user_id`、`status`、`result`、`follower_count` 等；若需 `nickname` 字段，在 `_task_payload` 中补 `"nickname": task.nickname or ""`（`BloggerAnalysisTask` 无 nickname 列时改为从 result 里取，或任务创建时透传 nickname——见 Task 10 创建处）。

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_analysis_task_list.py -v`
Expected: PASS（需按 conftest 现有 fixture 补齐测试基建；若 conftest 无对应 fixture，按项目既有 `test_notes.py` 的 TestClient 模式补）

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/v1/notes.py backend/tests/test_analysis_task_list.py
git commit -m "feat: 分析任务只读列表端点（批量筛选支撑）"
```
## Phase 2 前端

> 依赖后端 Task 9 落地的 JSON 结构：`dimensions.{seeding_depth,verticality,stable_output,sustained_operation,growth_trend}`、`stage`、`decision.recommendation ∈ {priority,ok,caution,not_recommended,insufficient_data}`、`overall.score_suppressed`。

### Task 12: 分析 API 客户端（新类型）

**Files:**
- Create: `frontend/src/services/analysis.ts`

- [ ] **Step 1: 创建 analysis.ts**

```ts
// frontend/src/services/analysis.ts
import api from './api';

export type Recommendation = 'priority' | 'ok' | 'caution' | 'not_recommended' | 'insufficient_data';
export type StageLabel = '冷启动' | '成长' | '成熟' | '衰退';
export type Conf = 'high' | 'medium' | 'low';

export interface DimensionDetail {
  collect_rate_percent?: number;
  collect_like_ratio?: number;
  share_rate_percent?: number;
  comment_signal?: number;
  comment_signal_low_conf?: boolean;
  food_ratio?: number;
  food_notes?: number;
  judged_notes?: number;
  viral_ratio?: number;
  gap_days?: number;
  cliff_detected?: boolean;
  weekly_notes?: number;
  freshness_days?: number;
  growth_rate?: number | null;
  has_snapshot?: boolean;
  trend_ratio?: number | null;
  reason?: string | null;
}

export interface BloggerDimension {
  score: number | null;
  confidence: Conf;
  detail: DimensionDetail;
}

export interface BloggerAnalysisResult {
  note_count: number;
  real_note_count: number;
  coverage: { total_notes: number; fetched_notes: number; coverage_rate: number; sampled: boolean };
  confidence: Conf;
  dimensions: Record<'seeding_depth' | 'verticality' | 'stable_output' | 'sustained_operation' | 'growth_trend', BloggerDimension>;
  overall: { score: number | null; level: string; description: string; score_suppressed: boolean } | null;
  overall_score_suppressed?: boolean;
  stage: { label: StageLabel; confidence: Conf; evidence: string[] } | null;
  decision: {
    recommendation: Recommendation;
    summary: string;
    reasons: string[];
    red_flags: { type: string; level: string; detail: string }[];
    low_quality: boolean;
  } | null;
  insights: string[];
  anomalies: { type: string; level: string; detail: string }[];
  notes: any[];
  timeline: { items?: any[] };
  follower_history: any;
  grass_planting: any;
  growth_potential: any;
}

export interface ScreeningRow {
  user_id: string;
  nickname: string;
  avatar: string;
  fans: number;
  overall_score: number | null;
  score_suppressed: boolean;
  level: string;
  recommendation: Recommendation;
  stage_label: StageLabel;
  stage_confidence: Conf;
  red_flags: string[];
  collect_rate: number;
  confidence: Conf;
}

export async function fetchAnalysisTask(userId: string, taskId: string): Promise<any> {
  return (await api.get(`/notes/users/${userId}/analysis-tasks/${taskId}`)).data;
}

export async function createAnalysisTask(userId: string, payload: { nickname: string; fans: number; with_comments?: boolean }): Promise<any> {
  return (await api.post(`/notes/users/${userId}/analysis-tasks`, payload, { timeout: 60000 })).data;
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/services/analysis.ts
git commit -m "feat: 博主分析前端类型与 API 客户端"
```

---

### Task 13: UserAnalysisPanel 升级（五维 + 阶段 + 合作建议 + 评论开关）

**Files:**
- Modify: `frontend/src/components/UserAnalysisPanel.tsx`

- [ ] **Step 1: 更新维度标签与卡片**

将 `DIMENSION_LABELS` 替换为五维：

```tsx
const DIMENSION_LABELS: Record<string, string> = {
  seeding_depth: '种草深度',
  verticality: '内容垂直度',
  stable_output: '稳定产出',
  sustained_operation: '持续经营',
  growth_trend: '增长趋势',
};
```

`statCards` 数组替换为：

```tsx
const sd = (data.dimensions?.seeding_depth?.detail || {});
const v = (data.dimensions?.verticality?.detail || {});
const so = (data.dimensions?.sustained_operation?.detail || {});
const gt = (data.dimensions?.growth_trend?.detail || {});
const statCards = [
  { title: '已验证样本', value: cov.fetched_notes, suffix: `/${cov.sample_size || cov.total_notes || 0}`, color: '#1677ff' },
  { title: '覆盖率', value: cov.coverage_rate ? (cov.coverage_rate * 100).toFixed(1) : 0, suffix: '%', color: '#1677ff' },
  { title: '种草深度', value: data.dimensions?.seeding_depth?.score, suffix: '', color: '#eb2f96' },
  { title: '内容垂直度', value: data.dimensions?.verticality?.score, suffix: '', color: '#52c41a' },
  { title: '稳定产出', value: data.dimensions?.stable_output?.score, suffix: '', color: '#fa8c16' },
  { title: '持续经营', value: data.dimensions?.sustained_operation?.score, suffix: '', color: '#722ed1' },
  { title: '增长趋势', value: data.dimensions?.growth_trend?.score, suffix: '', color: '#13c2c2' },
  { title: '篇均收藏率', value: sd.collect_rate_percent, suffix: '%', color: '#f5222d' },
  { title: '美食占比', value: v.food_ratio != null ? (v.food_ratio * 100).toFixed(0) : undefined, suffix: '%', color: '#52c41a' },
  { title: '最新发布距今', value: so.freshness_days, suffix: '天', color: '#fa541c' },
];
if (gt.has_snapshot && gt.growth_rate != null) {
  statCards.push({ title: '涨粉率(月)', value: (gt.growth_rate * 100).toFixed(1), suffix: '%', color: '#13c2c2' });
}
```

- [ ] **Step 2: 合作建议卡片 + 阶段徽标**

在 `insights` Alert 之前插入建议卡片：

```tsx
{data.decision && (
  <Card size="small" style={{ marginBottom: 12, borderLeft: `4px solid ${recColor(data.decision.recommendation)}` }}>
    <Space direction="vertical" size={4} style={{ width: '100%' }}>
      <Space>
        <Text strong style={{ fontSize: 16 }}>{recLabel(data.decision.recommendation)}</Text>
        {data.stage && (
          <Tag color={stageColor(data.stage.label)}>
            {data.stage.label}
            {data.stage.confidence === 'low' ? '（推断）' : ''}
          </Tag>
        )}
        {data.overall_score_suppressed || data.overall?.score_suppressed ? <Tag color="red">已抑制评分</Tag> : null}
      </Space>
      <Text type="secondary">{data.decision.summary}</Text>
      {data.decision.reasons?.length > 0 && (
        <ul style={{ margin: 0, paddingLeft: 18 }}>
          {data.decision.reasons.map((r: string, i: number) => <li key={i}>{r}</li>)}
        </ul>
      )}
      {data.decision.red_flags?.length > 0 && (
        <Alert type="warning" showIcon message="红旗"
          description={<ul style={{ margin: 0, paddingLeft: 18 }}>{data.decision.red_flags.map((f: any, i: number) => <li key={i}>{f.detail}</li>)}</ul>} />
      )}
    </Space>
  </Card>
)}
```

文件底部补三个映射函数：

```tsx
function recLabel(r: string): string {
  return { priority: '优先合作', ok: '可合作', caution: '谨慎', not_recommended: '不合作', insufficient_data: '数据不足' }[r] || r;
}
function recColor(r: string): string {
  return { priority: '#52c41a', ok: '#1677ff', caution: '#fa8c16', not_recommended: '#f5222d', insufficient_data: '#8c8c8c' }[r] || '#1677ff';
}
function stageColor(s: string): string {
  return { 冷启动: 'blue', 成长: 'green', 成熟: 'gold', 衰退: 'red' }[s] || 'default';
}
```

- [ ] **Step 3: 评论分析开关**

在分析页头部（`analysisLoading` 分支）加入开关，发起任务时携带 `with_comments`：

```tsx
<Space style={{ marginBottom: 12 }}>
  <Switch checked={withComments} onChange={setWithComments} checkedChildren="评论分析开" unCheckedChildren="评论分析关" />
  <Text type="secondary">深度诊断可开启评论意向分析（抓取代表笔记评论，更准但更慢）</Text>
</Space>
```

`CrawlJobsPage.tsx` 中创建任务的请求体改为 `{ nickname: u.nickname, fans: u.fans, with_comments: withComments }`，并在 `setAnalysisData(t.result)` 后若 `withComments` 展示 `data.dimensions?.seeding_depth?.detail?.comment_signal_low_conf === false` 的提示「已启用评论意向分析」。

- [ ] **Step 4: 构建验证**

Run: `cd frontend && npx tsc --noEmit`
Expected: 无类型错误

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/UserAnalysisPanel.tsx frontend/src/pages/CrawlJobsPage.tsx
git commit -m "feat: UserAnalysisPanel 升级五维/阶段/合作建议/评论开关"
```

---

### Task 14: 批量筛选视图

**Files:**
- Create: `frontend/src/components/BloggerScreeningPanel.tsx`
- Modify: `frontend/src/pages/CrawlJobsPage.tsx`（新增 Tab）

- [ ] **Step 1: 创建 BloggerScreeningPanel.tsx**

```tsx
// frontend/src/components/BloggerScreeningPanel.tsx
import { useState } from 'react';
import { Button, Card, Col, InputNumber, Row, Space, Table, Tag, Typography } from 'antd';
import { ScreeningRow } from '../services/analysis';

const { Title, Text } = Typography;

const REC_TAG: Record<string, { color: string; label: string }> = {
  priority: { color: 'green', label: '优先合作' },
  ok: { color: 'blue', label: '可合作' },
  caution: { color: 'orange', label: '谨慎' },
  not_recommended: { color: 'red', label: '不合作' },
  insufficient_data: { color: 'default', label: '数据不足' },
};

export default function BloggerScreeningPanel({ rows, onRefresh }: { rows: ScreeningRow[]; onRefresh: () => void }) {
  const [minScore, setMinScore] = useState<number | null>(0);
  const [minFood, setMinFood] = useState<number | null>(0);
  const [minFans, setMinFans] = useState<number | null>(0);

  const filtered = rows.filter(r => {
    if (r.score_suppressed || r.overall_score == null) return false; // score=null 排最末，不进正常筛选
    if (minScore != null && r.overall_score < minScore) return false;
    return true;
  }).sort((a, b) => (b.overall_score ?? -1) - (a.overall_score ?? -1));

  const columns = [
    { title: '昵称', dataIndex: 'nickname', key: 'nickname', width: 180 },
    { title: '粉丝数', dataIndex: 'fans', key: 'fans', width: 100, render: (v: number) => v.toLocaleString('zh-CN') },
    { title: '总分', dataIndex: 'overall_score', key: 'overall_score', width: 80, render: (v: number | null) => v ?? '-' },
    { title: '等级', dataIndex: 'level', key: 'level', width: 80 },
    { title: '建议', dataIndex: 'recommendation', key: 'recommendation', width: 100,
      render: (v: string) => { const t = REC_TAG[v] || { color: 'default', label: v }; return <Tag color={t.color}>{t.label}</Tag>; } },
    { title: '阶段', dataIndex: 'stage_label', key: 'stage_label', width: 110,
      render: (v: string, r: ScreeningRow) => <Tag>{v}{r.stage_confidence === 'low' ? '（推断）' : ''}</Tag> },
    { title: '收藏率', dataIndex: 'collect_rate', key: 'collect_rate', width: 90, render: (v: number) => v != null ? `${v}%` : '-' },
    { title: '红旗', dataIndex: 'red_flags', key: 'red_flags', render: (v: string[]) => v?.length ? v.map((f, i) => <Tag color="red" key={i}>{f}</Tag>) : <Text type="secondary">无</Text> },
  ];

  return (
    <Card size="small" title={<Title level={5} style={{ margin: 0 }}>博主批量筛选</Title>}
      extra={<Space><InputNumber placeholder="总分≥" min={0} max={100} value={minScore} onChange={(v) => setMinScore(v ?? 0)} style={{ width: 90 }} />
        <Button type="primary" onClick={onRefresh}>刷新</Button></Space>}>
      <Table rowKey={(r) => r.user_id} columns={columns} dataSource={filtered} size="small"
        pagination={{ pageSize: 20, showTotal: (t) => `共 ${t} 个候选` }} />
      <Text type="secondary">说明：被闸门命中（score 为空）的账号已排在最末，不参与正常排序；「优先合作」需账号已有 ≥2 次涨粉快照。</Text>
    </Card>
  );
}
```

- [ ] **Step 2: CrawlJobsPage 接入新 Tab**

`CrawlJobsPage.tsx` 中 `tabs` 数组新增一项（放在「博主分析」之前）：

```tsx
{ key: 'screening', label: '批量筛选', children: (
  <BloggerScreeningPanel rows={screeningRows} onRefresh={loadScreening} />
) },
```

并补充状态与加载函数（沿用 analysis-tasks 列表接口或新建批量接口 `/notes/analysis-tasks?status=success`）：

```tsx
const [screeningRows, setScreeningRows] = useState<ScreeningRow[]>([]);

const loadScreening = async () => {
  const res = await api.get('/notes/analysis-tasks', { params: { status: 'success', limit: 200 } });
  const tasks = res.data?.items || [];
  setScreeningRows(tasks.map((t: any) => {
    const r = t.result || {};
    return {
      user_id: t.xhs_user_id,
      nickname: t.nickname || '',
      avatar: '',
      fans: t.follower_count || 0,
      overall_score: r.overall?.score ?? null,
      score_suppressed: !!(r.overall_score_suppressed || r.overall?.score_suppressed),
      level: r.overall?.level || '-',
      recommendation: r.decision?.recommendation || 'insufficient_data',
      stage_label: r.stage?.label || '-',
      stage_confidence: r.stage?.confidence || 'low',
      red_flags: (r.decision?.red_flags || []).map((f: any) => f.detail),
      collect_rate: r.dimensions?.seeding_depth?.detail?.collect_rate_percent ?? 0,
      confidence: r.confidence || 'low',
    };
  }));
};
useEffect(() => { loadScreening(); }, []);
```

> 若后端暂无 `GET /notes/analysis-tasks` 列表接口，则在 Task 14 前补一个只读列表端点（`GET /notes/analysis-tasks?status=success`，按 `finished_at desc`，返回 `items`），这是批量筛选的必要后端支撑；实现与 `get_analysis_task` 同模式（按 user_id 过滤 + status 过滤）。

- [ ] **Step 3: 构建验证**

Run: `cd frontend && npx tsc --noEmit`
Expected: 无类型错误

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/BloggerScreeningPanel.tsx frontend/src/pages/CrawlJobsPage.tsx
git commit -m "feat: 博主批量筛选视图（硬门槛 + 总分排序 + score=null 排末）"
```

---

## 计划自审记录

- **Spec 覆盖**：五维（Task 3/4/5/6 + Task 2 垂直度）、闸门（Task 7/9）、决策输出（Task 8/9）、双场景（Task 13/14）、评论增强（Task 10）、配置标定（Task 1）、旧引擎下线（Task 11）、置信度汇总（Task 8）、冷启动说明（Task 14 UI 文案 + Task 6 阶段判定）。
- **批量筛选列表端点**：`GET /notes/analysis-tasks` 已作为 Task 11b 落地，Task 14 直接消费。
- **类型一致性**：`score_blogger` 输出键（`seeding_depth/verticality/stable_output/sustained_operation/growth_trend`、`stage.label/confidence/evidence`、`decision.recommendation/summary/reasons/red_flags/low_quality`、`overall.score/score_suppressed`、`overall_score_suppressed`）与前端 `BloggerAnalysisResult` 完全对应。
- **占位扫描**：无 TBD/TODO；所有阈值以「结构占位」注明，标定方法论在 Task 1 配置与设计 §10。
