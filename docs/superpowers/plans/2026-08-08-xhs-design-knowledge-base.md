# 小红书设计知识库 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立可检索的小红书设计知识库（风格库/规则/提示词模板/品类映射），并接入装修模块全链路生成与复刻、体检建议，提升 AI 设计感。

**Architecture:** 静态 JSON 知识库 + 标签/别名归一化检索服务 `xhs_knowledge.py`；在 `profile_agent`（方案/提示词/体检）和 `doubao_vision`（复刻校准）入口注入检索上下文；预留 `xhs_knowledge_cases` 表供第二阶段案例库使用。

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy 2 / Alembic / pytest / JSON

**Spec:** `docs/superpowers/specs/2026-08-08-xhs-design-knowledge-base-design.md`

**Note:** 所有后端测试命令在 `D:\two\backend` 下执行；测试库为独立 `aistro_test`（127.0.0.1:5433，docker compose 已配置）。运行前确保 `docker compose up -d postgres redis minio`。

---

## File Structure

- Create: `backend/knowledge/xhs/styles.json` — 8 个风格条目
- Create: `backend/knowledge/xhs/rules.json` — 通用设计规则
- Create: `backend/knowledge/xhs/templates.json` — 按风格的头像/背景提示词模板
- Create: `backend/knowledge/xhs/category_map.json` — 品类→默认风格候选
- Create: `backend/app/services/xhs_knowledge.py` — 加载/检索/上下文拼接/复刻校准
- Create: `backend/app/models/xhs_knowledge_case.py` — 案例库模型
- Create: `backend/alembic/versions/e5f6a7b8c9d0_add_xhs_knowledge_cases.py` — 迁移
- Modify: `backend/app/models/__init__.py` — 注册模型
- Modify: `backend/app/ai/profile_agent.py` — 方案/提示词/体检接入
- Modify: `backend/app/ai/doubao_vision.py` — 复刻校准
- Create: `backend/tests/test_xhs_knowledge.py` — 检索与接入测试

---

### Task 1: 创建知识库静态文件

**Files:**
- Create: `backend/knowledge/xhs/styles.json`
- Create: `backend/knowledge/xhs/rules.json`
- Create: `backend/knowledge/xhs/templates.json`
- Create: `backend/knowledge/xhs/category_map.json`

- [ ] **Step 1: 创建 styles.json**

```json
[
  {
    "id": "shi_jing", "name": "市井烟火",
    "category_tags": ["火锅", "烧烤", "川菜", "湘菜", "江湖菜"],
    "style_tags": ["烟火气", "热闹", "暖调", "接地气", "复古市井"],
    "aliases": ["温馨", "热闹", "烟火", "市井"],
    "description": "老社区街巷的烟火气，热闹亲切、接地气，适合高复购的社区餐饮。",
    "color_palettes": [
      {"primary": "#C93828", "secondary": "#FFF0EE", "accent": "#A82015", "text": "#2A0A08", "ratio": "主4辅3点2文1"},
      {"primary": "#E8793A", "secondary": "#FFF3EC", "accent": "#D4520A", "text": "#2D1A0A", "ratio": "主5辅3点1文1"}
    ],
    "avatar_rules": "主体为人/食物特写或店招，构图居中偏大，暖光，背景虚化街巷。",
    "bg_rules": "门头/餐桌/招牌，暖黄灯光，有人气但不杂乱，留白适中。",
    "avoid": "冷灰调、无人物烟火感、高饱和荧光色、过度修图。"
  },
  {
    "id": "ri_xi", "name": "日系清新",
    "category_tags": ["咖啡", "甜品", "轻食", "烘焙", "Brunch"],
    "style_tags": ["清新", "治愈", "奶油", "低饱和", "胶片"],
    "aliases": ["温馨", "治愈", "干净", "日式"],
    "description": "低饱和、奶油色、大面积留白的日系治愈感，适合咖啡甜品轻食。",
    "color_palettes": [
      {"primary": "#E8C37A", "secondary": "#FFFBF0", "accent": "#C49A3C", "text": "#4A3A1A", "ratio": "主4辅3点2文1"},
      {"primary": "#A8C8A0", "secondary": "#F5F8F2", "accent": "#6E9A6A", "text": "#2A3A28", "ratio": "主4辅3点2文1"}
    ],
    "avatar_rules": "简洁手绘或食物特写，大面积留白，低饱和，暖白底。",
    "bg_rules": "原木桌面、手写菜单、窗边自然光，留白多。",
    "avoid": "高饱和、密集信息、冷蓝灰、黑色重边框。"
  },
  {
    "id": "gao_ji", "name": "高级冷淡",
    "category_tags": ["西餐", "日料", "高端餐饮", "酒吧"],
    "style_tags": ["极简", "冷淡", "高级", "黑白灰", "留白"],
    "aliases": ["简约", "高级", "克制", "性冷淡"],
    "description": "克制的黑白灰与大量留白，低装饰、高质感，适合高端餐饮。",
    "color_palettes": [
      {"primary": "#6B6B6B", "secondary": "#F7F7F7", "accent": "#4A4A4A", "text": "#1A1A1A", "ratio": "主3辅4点2文1"},
      {"primary": "#2F3E46", "secondary": "#EDF1F2", "accent": "#1F2A30", "text": "#0E1418", "ratio": "主4辅3点2文1"}
    ],
    "avatar_rules": "单一主体居中，弱化装饰，低饱和中性色，锐利简洁。",
    "bg_rules": "纯色或大留白，细线分隔，少元素。",
    "avoid": "暖色堆叠、卡通、复杂插画、过多样式。"
  },
  {
    "id": "fu_gu", "name": "复古文艺",
    "category_tags": ["咖啡", "甜品", "书店", "文创", "川菜"],
    "style_tags": ["复古", "文艺", "胶片", "棕调", "做旧"],
    "aliases": ["怀旧", "文艺", "旧时光", "胶片"],
    "description": "胶片颗粒、暖棕色调、年代道具的复古文艺感。",
    "color_palettes": [
      {"primary": "#9B8E8A", "secondary": "#F5F2F0", "accent": "#7A6E6A", "text": "#3A3330", "ratio": "主3辅4点2文1"},
      {"primary": "#8C5A2D", "secondary": "#F7F1E8", "accent": "#5E3D1C", "text": "#2B1F1A", "ratio": "主4辅3点2文1"}
    ],
    "avatar_rules": "胶片质感、颗粒感，主体带年代道具，暖棕色调。",
    "bg_rules": "木桌、旧海报、暖台灯，层次丰富但色调统一。",
    "avoid": "现代荧光、冷蓝、亮白底、无质感。"
  },
  {
    "id": "ins_feng", "name": "ins风",
    "category_tags": ["甜品", "咖啡", "轻食", "网红店"],
    "style_tags": ["ins", "时尚", "粉彩", "清爽", "打卡"],
    "aliases": ["网红", "ins", "时尚", "粉嫩"],
    "description": "柔和粉彩、通透光感、高颜值单品的打卡友好风格。",
    "color_palettes": [
      {"primary": "#F2A9C4", "secondary": "#FFF7FA", "accent": "#D96C9E", "text": "#4A2230", "ratio": "主4辅3点2文1"},
      {"primary": "#9ED4D8", "secondary": "#F4FBFB", "accent": "#4FA3A8", "text": "#16333A", "ratio": "主4辅3点2文1"}
    ],
    "avatar_rules": "高颜值单品特写，柔和粉彩，光感通透，适当道具点缀。",
    "bg_rules": "粉彩墙面加单品，干净留白，可加品牌小字。",
    "avoid": "暗黑、高对比荧光、杂乱堆料、土味贴纸风。"
  },
  {
    "id": "guo_chao", "name": "国潮",
    "category_tags": ["川菜", "湘菜", "火锅", "新中式"],
    "style_tags": ["国潮", "新中式", "红金", "传统纹样"],
    "aliases": ["国风", "中国风", "国潮", "传统"],
    "description": "传统纹样与现代图形结合，红金为主色的新中式国潮。",
    "color_palettes": [
      {"primary": "#A82015", "secondary": "#F6E7D8", "accent": "#D9A441", "text": "#1F1410", "ratio": "主4辅3点2文1"},
      {"primary": "#1F3A5F", "secondary": "#F0EDE6", "accent": "#C9A227", "text": "#101820", "ratio": "主4辅3点2文1"}
    ],
    "avatar_rules": "传统纹样加现代图形，红金为主，印章或书法元素点缀。",
    "bg_rules": "屏风、窗棂、灯笼元素，稳重底色，留出信息区。",
    "avoid": "廉价贴纸、元素过多、饱和度失控、字体混杂。"
  },
  {
    "id": "nai_yu", "name": "奶油风",
    "category_tags": ["甜品", "烘焙", "Brunch", "轻食"],
    "style_tags": ["奶油", "温柔", "低饱和", "圆润", "舒适"],
    "aliases": ["奶油", "温柔", "软糯", "舒适"],
    "description": "奶油色块、圆润造型、柔和光影的温暖舒适风。",
    "color_palettes": [
      {"primary": "#F2E3D5", "secondary": "#FFFDF9", "accent": "#D9B896", "text": "#4A3A2E", "ratio": "主4辅3点2文1"},
      {"primary": "#EAD9C8", "secondary": "#FFFBF4", "accent": "#C7A17B", "text": "#40342A", "ratio": "主4辅3点2文1"}
    ],
    "avatar_rules": "圆润造型、奶油色底、柔和光影，可爱但不幼稚。",
    "bg_rules": "奶油色块分区、圆角卡片感、温暖灯光。",
    "avoid": "高饱和、锐利边缘、冷色、信息过密。"
  },
  {
    "id": "shen_ye", "name": "深夜酒馆",
    "category_tags": ["酒吧", "居酒屋", "烧烤", "夜宵"],
    "style_tags": ["夜", "暗调", "霓虹", "微醺", "神秘"],
    "aliases": ["深夜", "酒吧", "暗黑", "霓虹", "微醺"],
    "description": "暗底配局部霓虹光，神秘微醺的夜经济氛围。",
    "color_palettes": [
      {"primary": "#7B5EA7", "secondary": "#F5F0FA", "accent": "#5E3F89", "text": "#201838", "ratio": "主4辅3点2文1"},
      {"primary": "#1B2A4A", "secondary": "#0F1626", "accent": "#4A7BD9", "text": "#DCE6F5", "ratio": "主4辅3点2文1"}
    ],
    "avatar_rules": "暗底加霓虹光，主体剪影或酒器，神秘氛围。",
    "bg_rules": "暗色背景加局部光，吧台或酒柜元素，信息区保持可读。",
    "avoid": "高亮白底、卡通、明亮小清新、文字对比不足。"
  }
]
```

- [ ] **Step 2: 创建 rules.json**

```json
[
  {"id": "bg_ratio", "rule": "背景图比例 1125:420，重要信息避开左右边缘。"},
  {"id": "avatar_size", "rule": "头像不小于 400x400，圆形裁切，主体居中。"},
  {"id": "nickname_bio_limit", "rule": "昵称不超过 20 字且不含 emoji；简介不超过 100 字。"},
  {"id": "palette_limit", "rule": "全页主色不超过 4 个，优先取自所选风格的配色配方。"},
  {"id": "contrast", "rule": "文字与背景对比度足够，避免浅底浅字或深底深字。"},
  {"id": "consistency", "rule": "头像与背景使用同一风格，气质统一。"},
  {"id": "whitespace", "rule": "每屏留白不少于四分之一，避免元素铺满。"},
  {"id": "avatar_zone", "rule": "背景图中头像落点区域保持简洁，避免复杂纹理干扰头像。"},
  {"id": "decoration_limit", "rule": "风格化元素（印章、霓虹、贴纸）克制使用，单页不超过 2 类。"},
  {"id": "avoid_template_feel", "rule": "避免模板感：布局可变化，但统一色系与字体气质。"}
]
```

- [ ] **Step 3: 创建 templates.json**（占位符：`{category}` `{style}` `{palette}` `{subject}`）

```json
{
  "shi_jing": {
    "avatar_template": "为{category}设计{style}风格头像：{palette}配色，{subject}主体居中偏大，暖黄灯光，背景虚化街巷，有烟火气，方形构图，无文字水印；避免冷灰调、荧光色、复杂文字。",
    "bg_template": "为{category}设计{style}风格背景图：{palette}配色，门头、餐桌或招牌氛围，暖黄灯光，人气热闹但不杂乱，宽幅构图，头像区域保持简洁。"
  },
  "ri_xi": {
    "avatar_template": "为{category}设计{style}风格头像：{palette}配色，{subject}简洁主体居中，大面积留白，低饱和，暖白底，胶片感；避免高饱和、密集元素、冷蓝灰。",
    "bg_template": "为{category}设计{style}风格背景图：{palette}配色，原木桌面、手写菜单或窗边自然光，留白多，宽幅构图，头像区域简洁。"
  },
  "gao_ji": {
    "avatar_template": "为{category}设计{style}风格头像：{palette}配色，单一{subject}主体居中，弱化装饰，低饱和中性色，锐利简洁；避免暖色堆叠、卡通、复杂插画。",
    "bg_template": "为{category}设计{style}风格背景图：{palette}配色，纯色或大留白，细线分隔，少元素，宽幅构图，头像区域简洁。"
  },
  "fu_gu": {
    "avatar_template": "为{category}设计{style}风格头像：{palette}配色，{subject}主体带年代道具，胶片颗粒质感，暖棕色调，居中构图；避免现代荧光、冷蓝、亮白底。",
    "bg_template": "为{category}设计{style}风格背景图：{palette}配色，木桌、旧海报、暖台灯元素，层次丰富但色调统一，宽幅构图，头像区域简洁。"
  },
  "ins_feng": {
    "avatar_template": "为{category}设计{style}风格头像：{palette}配色，高颜值{subject}特写，柔和粉彩，光感通透，适当道具点缀；避免暗黑、荧光、杂乱堆料。",
    "bg_template": "为{category}设计{style}风格背景图：{palette}配色，粉彩墙面加单品，干净留白，可加品牌小字，宽幅构图，头像区域简洁。"
  },
  "guo_chao": {
    "avatar_template": "为{category}设计{style}风格头像：{palette}配色，{subject}主体结合传统纹样与现代图形，红金为主，印章或书法点缀；避免廉价贴纸、元素过多、字体混杂。",
    "bg_template": "为{category}设计{style}风格背景图：{palette}配色，屏风、窗棂或灯笼元素，稳重底色，留出信息区，宽幅构图，头像区域简洁。"
  },
  "nai_yu": {
    "avatar_template": "为{category}设计{style}风格头像：{palette}配色，圆润{subject}主体，奶油色底，柔和光影，可爱但不幼稚；避免高饱和、锐利边缘、冷色。",
    "bg_template": "为{category}设计{style}风格背景图：{palette}配色，奶油色块分区、圆角卡片感、温暖灯光，宽幅构图，头像区域简洁。"
  },
  "shen_ye": {
    "avatar_template": "为{category}设计{style}风格头像：{palette}配色，{subject}剪影或酒器，暗底加霓虹光，神秘氛围，居中构图；避免高亮白底、卡通、文字对比不足。",
    "bg_template": "为{category}设计{style}风格背景图：{palette}配色，暗色背景加局部光，吧台或酒柜元素，宽幅构图，头像区域保持可读。"
  }
}
```

- [ ] **Step 4: 创建 category_map.json**

```json
{
  "火锅": ["shi_jing", "guo_chao", "fu_gu"],
  "烧烤": ["shi_jing", "shen_ye", "guo_chao"],
  "川菜": ["shi_jing", "guo_chao", "fu_gu"],
  "湘菜": ["shi_jing", "guo_chao"],
  "咖啡": ["ri_xi", "gao_ji", "fu_gu"],
  "甜品": ["nai_yu", "ri_xi", "ins_feng"],
  "烘焙": ["nai_yu", "ri_xi", "ins_feng"],
  "Brunch": ["ri_xi", "nai_yu", "ins_feng"],
  "轻食": ["ri_xi", "ins_feng", "nai_yu"],
  "日料": ["gao_ji", "ri_xi", "shen_ye"],
  "西餐": ["gao_ji", "fu_gu"],
  "高端餐饮": ["gao_ji", "fu_gu"],
  "酒吧": ["shen_ye", "gao_ji"],
  "居酒屋": ["shen_ye", "ri_xi"],
  "夜宵": ["shen_ye", "shi_jing"],
  "书店": ["fu_gu", "ri_xi"],
  "文创": ["fu_gu", "guo_chao"],
  "新中式": ["guo_chao", "fu_gu"],
  "网红店": ["ins_feng", "nai_yu", "ri_xi"],
  "默认": ["gao_ji"]
}
```

- [ ] **Step 5: 校验 JSON 可解析并提交**

```powershell
cd D:\two\backend
python -c "import json,glob;[json.load(open(p,encoding='utf-8')) for p in glob.glob(r'knowledge\xhs\*.json')];print('json ok')"
```

Expected: `json ok`

```bash
git add backend/knowledge/xhs
git commit -m "feat: 小红书设计知识库静态内容"
```

---

### Task 2: 案例库数据模型与迁移（第二阶段预留）

**Files:**
- Create: `backend/app/models/xhs_knowledge_case.py`
- Create: `backend/alembic/versions/e5f6a7b8c9d0_add_xhs_knowledge_cases.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: 创建模型**

```python
"""小红书设计知识库案例模型（第二阶段案例库预留）。"""
from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import DateTime, Enum, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class XhsKnowledgeCase(Base):
    __tablename__ = "xhs_knowledge_cases"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    style_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    category_tags: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tags: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str | None] = mapped_column(String(200), nullable=True)
    authorization_status: Mapped[str] = mapped_column(
        Enum(
            "unauthorized",
            "authorized",
            "internal_only",
            name="xhs_knowledge_auth_status",
        ),
        nullable=False,
        server_default="internal_only",
    )
    embedding: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.func.now()
    )
```

- [ ] **Step 2: 创建迁移**

```python
"""add_xhs_knowledge_cases

Revision ID: e5f6a7b8c9d0
Revises: f9e8d7c6b5a4
Create Date: 2026-08-08 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, Sequence[str], None] = "f9e8d7c6b5a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add XHS knowledge base cases table."""
    op.create_table(
        "xhs_knowledge_cases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("style_id", sa.String(length=50), nullable=False),
        sa.Column("category_tags", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column("title", sa.String(length=100), nullable=True),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=200), nullable=True),
        sa.Column(
            "authorization_status",
            sa.Enum(
                "unauthorized",
                "authorized",
                "internal_only",
                name="xhs_knowledge_auth_status",
            ),
            nullable=False,
            server_default="internal_only",
        ),
        sa.Column("embedding", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_xhs_knowledge_cases_style_id", "xhs_knowledge_cases", ["style_id"]
    )


def downgrade() -> None:
    """Drop XHS knowledge base cases table."""
    op.drop_table("xhs_knowledge_cases")
```

- [ ] **Step 3: 注册模型**

在 `backend/app/models/__init__.py` 末尾追加：

```python
from app.models.xhs_knowledge_case import XhsKnowledgeCase
```

并在 `__all__` 列表追加：

```python
    "XhsKnowledgeCase",
```

- [ ] **Step 4: 应用迁移并提交**

```powershell
cd D:\two\backend
python -m alembic upgrade head
```

Expected: `Running upgrade f9e8d7c6b5a4 -> e5f6a7b8c9d0, add_xhs_knowledge_cases`

```bash
git add backend/app/models/xhs_knowledge_case.py backend/alembic/versions/e5f6a7b8c9d0_add_xhs_knowledge_cases.py backend/app/models/__init__.py
git commit -m "feat: 预留小红书设计案例库数据表"
```

---

### Task 3: 检索服务（TDD）

**Files:**
- Create: `backend/tests/test_xhs_knowledge.py`
- Create: `backend/app/services/xhs_knowledge.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_xhs_knowledge.py`：

```python
"""小红书设计知识库检索与接入测试。"""
from __future__ import annotations

import pytest

from app.services.xhs_knowledge import (
    build_knowledge_context,
    enrich_clone_schemes,
    reset_cache,
    retrieve,
)


@pytest.fixture(autouse=True)
def _fresh_cache():
    reset_cache()
    yield
    reset_cache()


def test_static_files_load_and_schema_valid():
    payload = retrieve()
    assert payload["styles"]
    assert payload["rules"]
    assert payload["styles"][0]["color_palettes"][0]["primary"].startswith("#")


def test_retrieve_by_category_returns_default_style():
    payload = retrieve(category="火锅", limit=1)
    assert payload["styles"][0]["id"] == "shi_jing"


def test_retrieve_by_style_alias():
    payload = retrieve(style_keywords=["温馨"], limit=3)
    ids = [s["id"] for s in payload["styles"]]
    assert "shi_jing" in ids


def test_retrieve_scoring_combines_category_and_keywords():
    payload = retrieve(category="火锅", style_keywords=["市井烟火"], limit=1)
    assert payload["styles"][0]["id"] == "shi_jing"


def test_retrieve_fallback_to_default_style():
    payload = retrieve(category="不存在品类", style_keywords=[], limit=1)
    assert payload["styles"][0]["id"] == "gao_ji"


def test_retrieve_palette_hint_boosts_style():
    payload = retrieve(category="咖啡", palette_hint="#E8C37A", limit=1)
    assert payload["styles"][0]["id"] == "ri_xi"


def test_build_context_contains_style_and_rules():
    ctx = build_knowledge_context(category="火锅", style_keywords=["市井烟火"])
    assert "市井烟火" in ctx
    assert "通用设计规则" in ctx
    assert "背景比例 1125:420" in ctx


def test_enrich_clone_schemes_fills_missing_prompts():
    result = {
        "style_keywords": ["烟火气"],
        "schemes": [
            {
                "id": "A",
                "name": "暖辣市井方案",
                "color_scheme": {
                    "primary": "#C93828",
                    "secondary": "#FFF0EE",
                    "accent": "#A82015",
                    "text": "#2A0A08",
                },
                "avatar_prompt": "",
                "bg_prompt": "",
            }
        ],
    }
    out = enrich_clone_schemes(result)
    assert out["schemes"][0]["avatar_prompt"]
    assert out["schemes"][0]["bg_prompt"]
    assert out["knowledge_styles"]
```

- [ ] **Step 2: 运行确认失败**

```powershell
cd D:\two\backend
python -m pytest tests/test_xhs_knowledge.py -q
```

Expected: `ERROR ... cannot import name 'retrieve' from 'app.services.xhs_knowledge'`

- [ ] **Step 3: 实现检索服务**

创建 `backend/app/services/xhs_knowledge.py`：

```python
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
    return sum(1 for kw in keywords if _norm(kw) in tags or _norm(kw) in aliases)


def _category_default_ids(category: str | None) -> list[str]:
    if not category:
        return []
    cmap = _load()["category_map"]
    return cmap.get(_norm(category)) or cmap.get(category) or []


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
        fallback_ids = defaults or [_DEFAULT_STYLE_ID]
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
        "templates": [templates[s["id"]] for s in top if s["id"] in templates],
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
        for i, tpl in enumerate(payload["templates"]):
            lines.append(f"- {payload['styles'][i]['name']} 头像模板：{tpl.get('avatar_template', '')}")
            if section != "avatar":
                lines.append(f"- {payload['styles'][i]['name']} 背景模板：{tpl.get('bg_template', '')}")
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
    """复刻方案校准：补齐缺失提示词并附上命中的知识风格。"""
    keywords = result.get("style_keywords") or []
    for scheme in result.get("schemes") or []:
        cs = scheme.get("color_scheme") or {}
        payload = retrieve(
            category=result.get("category"),
            style_keywords=keywords,
            palette_hint=cs.get("primary"),
            limit=1,
        )
        if not payload["styles"] or not payload["templates"]:
            continue
        style = payload["styles"][0]
        tpl = payload["templates"][0]
        if not scheme.get("avatar_prompt") and tpl.get("avatar_template"):
            scheme["avatar_prompt"] = _fill_template(
                tpl["avatar_template"], result.get("category"), style["name"], cs
            )
        if not scheme.get("bg_prompt") and tpl.get("bg_template"):
            scheme["bg_prompt"] = _fill_template(
                tpl["bg_template"], result.get("category"), style["name"], cs
            )
    if keywords:
        result["knowledge_styles"] = [
            s["name"] for s in retrieve(style_keywords=keywords, limit=2)["styles"]
        ]
    return result
```


- [ ] **Step 4: 运行确认通过**

```powershell
cd D:\two\backend
python -m pytest tests/test_xhs_knowledge.py -q
```

Expected: `8 passed`

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/xhs_knowledge.py backend/tests/test_xhs_knowledge.py
git commit -m "feat: 小红书设计知识库检索服务"
```

---

### Task 4: 方案生成接入知识库

**Files:**
- Modify: `backend/app/ai/profile_agent.py`

- [ ] **Step 1: 加 import**

在 `backend/app/ai/profile_agent.py` 顶部追加：

```python
from app.services.xhs_knowledge import build_knowledge_context
```

- [ ] **Step 2: 改造 `generate_variants`**

把 `generate_variants` 中构造 system 消息的部分改为：

```python
    kb_context = build_knowledge_context(
        category=category, style_keywords=[style], limit=3
    )
    system_content = _SYSTEM_PROMPT
    if kb_context:
        system_content += "\n\n## 参考设计知识库（必须遵守）\n" + kb_context

    response = await client.chat.completions.create(
        model=settings.DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.8,
        max_tokens=3000,
    )
```

- [ ] **Step 3: 追加测试**

在 `backend/tests/test_xhs_knowledge.py` 末尾追加：

```python
def test_generate_variants_injects_knowledge(monkeypatch):
    import asyncio

    from app.ai import profile_agent

    captured = {}

    class FakeCompletions:
        async def create(self, **kwargs):
            captured["kwargs"] = kwargs
            return type(
                "R",
                (),
                {
                    "choices": [
                        type("Ch", (), {"message": type("M", (), {"content": '{"variants":[]}'})()})()
                    ]
                },
            )()

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    monkeypatch.setattr(profile_agent, "_get_client", lambda: FakeClient())
    variants, _ = asyncio.run(
        profile_agent.generate_variants("火锅", "市井烟火", "人均80")
    )
    system = captured["kwargs"]["messages"][0]["content"]
    assert "参考设计知识库" in system
    assert "市井烟火" in system
    assert len(variants) == 4
```

- [ ] **Step 4: 运行并提交**

```powershell
cd D:\two\backend
python -m pytest tests/test_xhs_knowledge.py::test_generate_variants_injects_knowledge -q
```

Expected: `1 passed`

```bash
git add backend/app/ai/profile_agent.py backend/tests/test_xhs_knowledge.py
git commit -m "feat: 装修方案生成接入设计知识库"
```

---

### Task 5: 单板块提示词接入知识库

**Files:**
- Modify: `backend/app/ai/profile_agent.py`

- [ ] **Step 1: 改造 `generate_section_prompt`**

把该函数构造 system 消息的部分改为：

```python
    kb_context = build_knowledge_context(
        category=category, style_keywords=[style], section=section, limit=3
    )
    system_content = _SECTION_PROMPT_SYSTEM
    if kb_context:
        system_content += "\n\n## 参考设计知识库（必须遵守）\n" + kb_context

    response = await _get_client().chat.completions.create(
        model=settings.DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.9,
        max_tokens=500,
    )
```

- [ ] **Step 2: 追加测试**

在 `backend/tests/test_xhs_knowledge.py` 末尾追加：

```python
def test_section_prompt_injects_avatar_template(monkeypatch):
    import asyncio

    from app.ai import profile_agent

    captured = {}

    class FakeCompletions:
        async def create(self, **kwargs):
            captured["kwargs"] = kwargs
            return type(
                "R",
                (),
                {
                    "choices": [
                        type("Ch", (), {"message": type("M", (), {"content": "头像提示词"})()})()
                    ]
                },
            )()

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    monkeypatch.setattr(profile_agent, "_get_client", lambda: FakeClient())
    prompt = asyncio.run(
        profile_agent.generate_section_prompt("avatar", "火锅", "市井烟火", "人均80")
    )
    system = captured["kwargs"]["messages"][0]["content"]
    assert "参考设计知识库" in system
    assert "头像模板" in system
    assert "背景模板" not in system
    assert prompt == "头像提示词"
```

- [ ] **Step 3: 运行并提交**

```powershell
cd D:\two\backend
python -m pytest tests/test_xhs_knowledge.py::test_section_prompt_injects_avatar_template -q
```

Expected: `1 passed`

```bash
git add backend/app/ai/profile_agent.py backend/tests/test_xhs_knowledge.py
git commit -m "feat: 一键生成提示词接入设计知识库"
```

---

### Task 6: 一键复刻校准接入知识库

**Files:**
- Modify: `backend/app/ai/doubao_vision.py`
- Test: `backend/tests/test_xhs_knowledge.py`

- [ ] **Step 1: 加 import 并校准**

在 `backend/app/ai/doubao_vision.py` 顶部追加：

```python
from app.services.xhs_knowledge import enrich_clone_schemes
```

把 `analyze_clone_style_with_fallback` 改为：

```python
async def analyze_clone_style_with_fallback(
    image_data: bytes, mime: str = "image/png"
) -> dict:
    """优先豆包视觉；识别失败或没有多方案时回退旧 DeepSeek 分析。"""
    try:
        result = await analyze_image_style(image_data, mime)
        if result.get("schemes"):
            return enrich_clone_schemes(result)
    except Exception:
        pass
    return await analyze_style(image_data, mime)
```

- [ ] **Step 2: 追加测试**

在 `backend/tests/test_xhs_knowledge.py` 末尾追加：

```python
def test_clone_fallback_enriches_schemes(monkeypatch):
    import asyncio

    from app.ai import doubao_vision

    async def fake_analyze(*args, **kwargs):
        return {
            "style_keywords": ["烟火气"],
            "schemes": [
                {
                    "id": "A",
                    "name": "暖辣市井方案",
                    "color_scheme": {
                        "primary": "#C93828",
                        "secondary": "#FFF0EE",
                        "accent": "#A82015",
                        "text": "#2A0A08",
                    },
                    "avatar_prompt": "",
                    "bg_prompt": "",
                }
            ],
        }

    monkeypatch.setattr(doubao_vision, "analyze_image_style", fake_analyze)
    result = asyncio.run(
        doubao_vision.analyze_clone_style_with_fallback(b"x", "image/png")
    )
    assert result["schemes"][0]["avatar_prompt"]
    assert result["schemes"][0]["bg_prompt"]
    assert result["knowledge_styles"]
```

- [ ] **Step 3: 运行并提交**

```powershell
cd D:\two\backend
python -m pytest tests/test_xhs_knowledge.py::test_clone_fallback_enriches_schemes tests/test_xhs_knowledge.py::test_enrich_clone_schemes_fills_missing_prompts -q
```

Expected: `2 passed`

```bash
git add backend/app/ai/doubao_vision.py backend/tests/test_xhs_knowledge.py
git commit -m "feat: 一键复刻方案按设计知识库校准"
```

---

### Task 7: 体检与按建议优化接入知识库

**Files:**
- Modify: `backend/app/ai/profile_agent.py`

- [ ] **Step 1: 体检接入**

在 `run_profile_health_check` 构造 system 消息处改为：

```python
    kb_context = build_knowledge_context(limit=2)
    system_content = _HEALTH_SYSTEM_PROMPT
    if kb_context:
        system_content += "\n\n## 设计一致性参考规则（作为建议维度，不评分）\n" + kb_context

    response = await _get_client().chat.completions.create(
        model=settings.DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.5,
        max_tokens=900,
    )
```

- [ ] **Step 2: 按建议优化接入**

在 `rewrite_by_health_check` 构造 system 消息处改为：

```python
    kb_context = build_knowledge_context(
        category=category, style_keywords=[style], limit=2
    )
    system_content = _HEALTH_REWRITE_SYSTEM_PROMPT
    if kb_context:
        system_content += "\n\n## 参考设计知识库（必须遵守）\n" + kb_context

    response = await _get_client().chat.completions.create(
        model=settings.DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.6,
        max_tokens=900,
    )
```

- [ ] **Step 3: 追加测试**

在 `backend/tests/test_xhs_knowledge.py` 末尾追加：

```python
def test_health_check_injects_knowledge_rules(monkeypatch):
    import asyncio

    from app.ai import profile_agent

    captured = {}

    class FakeCompletions:
        async def create(self, **kwargs):
            captured["kwargs"] = kwargs
            content = '{"first_impression":"ok","strengths":["a"],"weaknesses":["b"],"suggestions":["c"]}'
            return type(
                "R",
                (),
                {
                    "choices": [
                        type("Ch", (), {"message": type("M", (), {"content": content})()})()
                    ]
                },
            )()

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    monkeypatch.setattr(profile_agent, "_get_client", lambda: FakeClient())
    result = asyncio.run(
        profile_agent.run_profile_health_check(
            "昵称", "简介", "头像p", "背景p", [],
            "#C93828", "#FFF0EE", "#A82015", "#2A0A08", True, True,
        )
    )
    system = captured["kwargs"]["messages"][0]["content"]
    assert "设计一致性参考规则" in system
    assert "通用设计规则" in system
    assert result["first_impression"] == "ok"


def test_rewrite_injects_knowledge_rules(monkeypatch):
    import asyncio

    from app.ai import profile_agent

    captured = {}

    class FakeCompletions:
        async def create(self, **kwargs):
            captured["kwargs"] = kwargs
            content = '{"nickname_options":["新昵称"],"bio":"新简介","pinned_notes":[]}'
            return type(
                "R",
                (),
                {
                    "choices": [
                        type("Ch", (), {"message": type("M", (), {"content": content})()})()
                    ]
                },
            )()

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    monkeypatch.setattr(profile_agent, "_get_client", lambda: FakeClient())
    result = asyncio.run(
        profile_agent.rewrite_by_health_check(
            "旧昵称", "旧简介", [], ["不足"], ["建议"], "火锅", "市井烟火", "人均80"
        )
    )
    system = captured["kwargs"]["messages"][0]["content"]
    assert "参考设计知识库" in system
    assert result["bio"] == "新简介"
```

- [ ] **Step 4: 运行并提交**

```powershell
cd D:\two\backend
python -m pytest tests/test_xhs_knowledge.py::test_health_check_injects_knowledge_rules tests/test_xhs_knowledge.py::test_rewrite_injects_knowledge_rules -q
```

Expected: `2 passed`

```bash
git add backend/app/ai/profile_agent.py backend/tests/test_xhs_knowledge.py
git commit -m "feat: 主页体检与按建议优化接入设计知识库"
```

---

### Task 8: 全量回归与收尾

**Files:** 无新增

- [ ] **Step 1: 全量装修相关测试**

```powershell
cd D:\two\backend
python -m pytest tests/test_xhs_knowledge.py tests/test_profile.py tests/test_doubao_image.py -q
```

Expected: 全部通过（原有 30 项 + 新增 13 项左右）

- [ ] **Step 2: 确认迁移已应用**

```powershell
cd D:\two\backend
python -m alembic current
```

Expected: `e5f6a7b8c9d0 (head)`

- [ ] **Step 3: 重启后端**

```powershell
$conn = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($conn) { Stop-Process -Id $conn.OwningProcess -Force; Start-Sleep -Seconds 1 }
Start-Process -FilePath "python" -ArgumentList "-m","uvicorn","app.main:app","--host","0.0.0.0","--port","8000" -WorkingDirectory "D:\two\backend" -WindowStyle Hidden
```

- [ ] **Step 4: 人工验收**

用一张手机截图走一遍“一键复刻”，确认：
1. 复刻方案配色来自知识库风格配方。
2. 头像/背景提示词属于同一风格。
3. 提示词无 `{占位符}` 残留。
4. 方案生成、一键提示词、主页体检结果正常。

- [ ] **Step 5: 提交收尾**

```bash
git add -A
git commit -m "chore: 小红书设计知识库实施收尾"
```

---

## Self-Review

- **Spec 覆盖**：
  - 风格库/规则/模板/品类映射 → Task 1。
  - 检索评分与回退 → Task 3。
  - 案例表预留 → Task 2。
  - 方案生成/提示词/复刻/体检/按建议优化全链路接入 → Task 4-7。
  - 测试与验收 → Task 3/8。
- **占位符扫描**：无 TBD/TODO；所有代码块完整。
- **类型一致性**：`retrieve`/`build_knowledge_context`/`enrich_clone_schemes` 签名在 Task 3 定义，Task 4-7 按此调用；`section` 参数只影响模板输出，不改变返回结构。
