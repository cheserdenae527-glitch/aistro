# 小红书设计知识库 — 设计文档

> 日期：2026-08-08
> 状态：待评审
> 关联模块：平台账号装修（Profile）、内容工坊（后续复用）

## 1. 背景与目标

AI 生成的装修方案、提示词、复刻方案存在“设计感不足”的问题：风格趋同、配色生硬、头像与背景气质不统一。为弥补这一短板，建立一份可维护、可检索的“小红书设计知识库”，把优秀设计经验固化为结构化知识，供 AI 在生成、复刻、体检等环节按需引用。

## 2. 范围

### 第一阶段（本次实现）
- 静态知识库文件：风格库、通用设计规则、提示词模板、品类映射。
- 标签检索服务：按品类、风格关键词、视觉识别结果挑选相关知识并注入提示词。
- 全链路接入：生成装修方案、一键生成提示词、一键复刻、生图、主页体检建议。
- 数据库预留：新增 `xhs_knowledge_cases` 表与模型，API 暂不开放。

### 第二阶段（预留，不在本次实现）
- 真实案例库上传/管理 API 与后台页面。
- 向量检索升级（接口签名已预留，调用方无需改动）。

### 非目标
- 不做生成后自动“设计感打分/自评”：不产生量化分数，不因分数自动重试或改稿。
- 主页体检只把风格规则作为建议文案的参考维度，不做规则判定打分；与“非目标”不冲突。
- 不做知识库后台管理界面。
- 不做抖音/美团平台知识库。

## 3. 知识库内容结构

目录：`backend/knowledge/xhs/`

### 3.1 styles.json — 风格库
首批 8-12 个核心风格，例如：市井烟火、日系清新、高级冷淡、复古文艺、ins 风、国潮、奶油风、深夜酒馆。

每条风格字段：

| 字段 | 说明 |
|---|---|
| id | 风格唯一标识 |
| name | 风格名称 |
| category_tags | 适用品类标签（火锅/烧烤/咖啡/甜品/日料/酒吧/轻食等） |
| style_tags | 风格关键词（烟火气、暖调、复古、极简等） |
| description | 一句话风格定义 |
| color_palettes | 2-3 组配色配方，每组含 primary/secondary/accent/text 与使用比例 |
| avatar_rules | 头像设计要点（主体、构图、质感、背景处理） |
| bg_rules | 背景设计要点 |
| avoid | 该风格下的避坑提示 |
| aliases | 风格同义词（如“温馨”“治愈”归入暖调），检索时归一化匹配 |

> 标签词表采用受控词表：`style_tags`/`category_tags` 由知识库统一定义，避免同义重复；新增词需先补入对应风格的 aliases。

### 3.2 rules.json — 通用设计规则
约 10 条，覆盖：
- 平台规格：背景比例 1125:420、头像不小于 400x400、昵称 ≤20 字且无 emoji、简介 ≤100 字。
- 视觉原则：主色不超过 3-4 个、文字与背景对比度、留白、风格统一性、头像与背景气质一致、避免模板感。

### 3.3 templates.json — 提示词模板库
按风格提供：
- `avatar_template`：头像生图提示词模板，含主体、风格词、配色、构图、光影、质感、负面词。
- `bg_template`：背景生图提示词模板，同上。
- 使用 `{品类}`、`{风格}`、`{配色}` 占位符，生成时自动填充。

### 3.4 category_map.json — 品类映射
- 品类 → 默认风格候选（按优先级排列）。
- 品类 → 匹配标签，用于检索。

## 4. 检索机制

新增 `backend/app/services/xhs_knowledge.py`：

- 模块加载时读取并缓存 4 个静态文件。
- 提供 `retrieve(category, style_keywords, palette_hint=None)`：
  1. 输入归一化：去除空白、统一大小写；风格关键词先做受控词表/aliases 归一化（“温馨”→“暖调”）。
  2. 按评分规则排序，返回 2-3 个最相关风格条目、对应提示词模板、通用规则摘要。
  3. 回退优先级：精确/别名命中 → 品类默认风格（category_map） → 全局默认风格「高级冷淡」。
- 评分规则（第一阶段）：
  ```
  score = 0
  品类命中（category_map 默认风格）          +3
  styles.category_tags 命中                 +2
  风格关键词命中 style_tags 或 aliases      +2
  palette_hint 与任一 color_palettes 相同   +1
  排序：score 降序；同分按 category_map 默认顺序
  兜底：无命中 → 品类默认 → 「高级冷淡」
  ```
- 词表规范：`style_tags`/`category_tags`/aliases 全部使用受控词表，避免第二阶段升级向量检索时推倒重来。
- 返回结构：
  ```json
  {
    "styles": [...],
    "templates": [...],
    "rules": [...],
    "category": "火锅"
  }
  ```
- 接口签名预留 `palette_hint` 等参数，第二阶段可替换为向量检索，调用方不改。

## 5. 全链路接入点

| 环节 | 接入方式 |
|---|---|
| 生成装修方案 | `profile_agent.generate_variants`：检索结果附加到 system prompt |
| 一键生成提示词 | `generate_section_prompt`：按板块带入对应风格模板与规则 |
| 一键复刻 | `doubao_vision`：视觉识别主色与风格词后检索最接近风格，校准配色与提示词 |
| 生图 | 提示词来自模板，规则随之生效，不单独改动 |
| 主页体检/按建议优化 | 将风格一致性规则作为 AI 生成建议文案的参考清单，不评分、不自动改稿（边界见非目标） |

## 6. 数据预留

新增模型 `XhsKnowledgeCase`，表 `xhs_knowledge_cases`：

| 字段 | 类型 | 说明 |
|---|---|---|
| id | UUID PK | |
| style_id | varchar | 关联 styles.json 风格 |
| category_tags | jsonb | 关联品类（可横跨多个品类） |
| image_url | text | MinIO 对象路径 |
| title | varchar | 案例标题 |
| tags | jsonb | 标签 |
| description | text | 案例说明 |
| source | varchar | 案例来源（如博主主页链接/平台） |
| authorization_status | varchar | 授权状态（未授权/已授权/仅内部参考） |
| embedding | jsonb | 向量占位（第二阶段向量检索使用，先建字段避免二次迁移） |
| created_at | datetime | |

第一阶段只建表与模型，不开放 API；第二阶段实现上传/检索接口。

## 7. 文件与改动清单

- 新增：`backend/knowledge/xhs/{styles,rules,templates,category_map}.json`
- 新增：`backend/app/services/xhs_knowledge.py`
- 新增：`backend/app/models/xhs_knowledge_case.py` + Alembic 迁移
- 修改：`backend/app/ai/profile_agent.py`（方案生成、单板块提示词）
- 修改：`backend/app/ai/doubao_vision.py`（复刻校准）
- 修改：`backend/app/api/v1/profiles.py`（体检建议带入风格规则，最小改动）
- 测试：`backend/tests/` 新增检索与复刻校准单测

## 8. 测试与验收

- 单元测试：
  - 按品类/关键词命中正确风格。
  - 无匹配时回退默认风格。
  - 静态 JSON 结构校验（必需字段完整）。
  - 复刻校准：mock 视觉结果 → 检索 → 提示词拼接正确。
- 回归：现有装修模块测试保持全绿。
- 人工验收：用同一张手机截图复刻，对比接入前后方案差异，按以下可观察维度逐项核对：
  1. 配色：主色数量 ≤4，且来自所选风格的 color_palettes。
  2. 一致性：头像与背景是否属于同一风格（同一风格 id 下生成）。
  3. 规则：是否触发所选风格的 avoid 避坑项（目标为 0）。
  4. 模板：提示词填充完整，无 `{占位符}` 残留。
  5. 可读性：文字与背景对比度、留白是否合理。

## 9. 内容维护

首版内容由实现时起草，之后可不断补充：
- 新增风格条目。
- 补充真实案例截图（第二阶段入库）。
- 修正规则与模板。
