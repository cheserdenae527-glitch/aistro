# Beav 知识库 → AiRestro 导入映射清单

> 目的：把 Beav 桌面端采集落盘的知识库文件（`<workspace>/knowledge/redbook/*/meta.json` + `content.md` + `images/`）导入 AiRestro 的 `note_details`。
> 你的实机工作区：`C:\Users\29842\.beav\knowledge\redbook\`（已存在 10 条样例）。
> 本清单为方案级（字段映射），脚本待确认后编写。

## 1. Beav 落盘结构（生产版 2.6.x，实测）

每个条目一个目录：

```
knowledge-64eb0e5b00000000100325a2/
├── meta.json        ← 元数据（标题/作者/正文/图片/统计/来源）
├── content.md       ← 正文纯文本（与 meta.json.description 一致）
├── images/image-N.webp   ← 已下载图片（本地资产）
└── video.mp4        ← 已下载视频（如有）
```

## 2. meta.json 关键字段（实测样例）

| 字段 | 示例 | 说明 |
|---|---|---|
| `id` | `knowledge-64eb0e5b...` | 目录名 |
| `externalId` / `dedupeKey` | `64eb0e5b00000000100325a2` | **笔记 noteId** |
| `type` / `captureKind` | `xhs-note` / `xhs-video` | 类型 |
| `title` | `下一站：马尔代夫七星岛…` | 标题 |
| `description` / `excerpt` | 正文文本 | 正文 |
| `author` | `宋卿禾` | 作者昵称 |
| `authorUrl` | `https://www.xiaohongshu.com/user/profile/646243fc...` | **可提取干净 userId** |
| `authorId` | `author-https-...-profile-646243fc...` | 带前缀，不宜直接用 |
| `sourceUrl` / `sourceLink` | `https://www.xiaohongshu.com/explore/64eb0e5b...?xsec_token=...` | **含 xsec_token** |
| `stats` | `{collects, likes, comments}` | 收藏/点赞/评论（comments 常为 null） |
| `tags` | `["小红书","马尔代夫[话题]"...]` | 标签 |
| `images` | `["images/image-1.webp", ...]` | 本地相对路径 |
| `cover` | `images/image-1.webp` | 封面 |
| `video` / `videoUrl` | `video.mp4` / 原始直链 | 视频 |
| `assetTransfer.items[].source` | `http://sns-webpic-qc.xhscdn.com/...` | **图片/视频原始直链** |
| `createdAt` | ISO 时间 | 采集时间（**非发布时间的可靠来源**） |
| 转录字段 | `transcriptFile` 等 | 视频转录（可选） |

**与 XHS API note_card 的差异**：meta.json 没有 `note_card` 结构、没有 `interact_info` 完整对象、没有 `published_at`（发布时间）、`comments` 常为 null。导入时需做形状变换。

## 3. 字段映射：Beav meta.json → processor.normalize_note 输出 → note_details

| normalize_note 输出字段 | 来源（Beav meta.json / 派生） |
|---|---|
| `platform_note_id` | `externalId` |
| `xsec_token` | `sourceUrl` URL 参数 `xsec_token` |
| `title` | `title` |
| `desc` | `description`（缺失时读 `content.md`） |
| `author.user_id` | `authorUrl` 正则 `/user/profile/([^/?#]+)` |
| `author.nickname` | `author` |
| `author.avatar` | `authorAvatarUrl` |
| `stats.likes` | `stats.likes` |
| `stats.collects` | `stats.collects` |
| `stats.comments` | `stats.comments`（null → 0，可选补抓） |
| `stats.shares` | 无（缺失） |
| `images` | `images`（本地绝对路径）或 `assetTransfer.items[].source`（原始直链） |
| `video_url` | `videoUrl` |
| `note_type` | `type`（xhs-note→图文 / xhs-video→视频） |
| `published_at` | **无**（需二次补抓，或用 `createdAt` 占位标注"采集时间"） |
| `raw` | 整个 `meta.json` + `content.md`（JSONB） |

## 4. 入库策略（note_details）

- 唯一约束 `(xhs_user_id, platform_note_id)`：`xhs_user_id` 用 authorUrl 里的干净 userId；`platform_note_id` 用 `externalId`。
- **幂等**：存在则更新 `detail_json` + `fetched_at`，不存在则插入。
- 导入脚本建议放 `backend/scripts/import_beav_knowledge.py`，逻辑：
  1. 扫描 `knowledge/redbook/*/meta.json`；
  2. 跳过 `captureKind` 非 xhs 的（`douyin-video`、`link-article`）；
  3. 按第 3 节映射 → `normalize_note` → upsert；
  4. 输出统计（导入数/跳过数/失败数 + 原因）。

## 5. 注意事项

- **发布时间缺失**：`published_at` 是博主分析的重要维度，Beav 文件里没有；如需，导入后对缺失项走你的 `note_detail` 补抓通道补齐（低优先级、限速）。
- **评论缺失**：当前样例无评论条目；Beav 侧边栏"采集评论"若单独保存（`captureKind=xhs-comments`），导入时同样要处理（写入 `detail_json.comments` 或独立表）。
- **图片本地化**：`images/` 已落本地，直接可用；原始直链在 `assetTransfer.items[].source` 可作备份。
- **许可证提醒**：Beav 为 MIT-NC，导入脚本读取你自己的本地文件用于内部数据整合没问题；商用集成 Beav 本体需作者许可（前面已说明）。

## 6. 下一步（待确认）

1. 是否现在写 `backend/scripts/import_beav_knowledge.py`（导入脚本）？
2. 是否要补抓缺失的 `published_at` / 评论（走你现有 note_detail 通道）？
3. 是否先把扩展 2.6.19 与桌面端 2.6.31 的版本对齐（避免握手版本提示）？

---

## 7. 互动指标补齐策略（新增，实测确认）

**问题**：Beav 的 `meta.json` 互动数据不全——
- `comments` 恒为 `null`；`share_count`（转发）字段完全缺失；
- 从信息流卡片直接保存时 `likes`/`collects` 常为 0；
- `published_at`（发布时间）缺失。

**原因**：Beav 读页面可见数据，而转发数网页不展示、评论数需单独采集动作、卡片保存时无详情统计。

**补齐方案（导入时执行）**：
1. 内容/作者/媒体：用 Beav `meta.json`（可靠）；
2. 互动指标 + 发布时间：以现有 `XhsCrawler.get_note_detail` 接口为准——导入后对 `stats` 缺失/为 0 的条目，批量回填 `interact_info`（含 `liked_count / collected_count / comment_count / share_count`）与 `note_card.time`；
3. 评论内容：按需 `get_comments`（低优先级）；
4. 全部走现有 `gate.py` 节流 + 幂等 upsert，不新增风控压力。

**交互数据最终来源优先级**：`note_detail` 接口 > Beav `stats`。
