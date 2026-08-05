"""直播工坊模块 Pydantic Schema。"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.sensitive_filter import contains_blocked

Platform = Literal["douyin", "xiaohongshu", "wechat"]
ProjectStatus = Literal["draft", "active", "archived"]
AvatarType = Literal["image", "video"]
AvatarStatus = Literal["draft", "ready", "disabled"]
ScriptSegmentType = Literal["opening", "product", "promo", "interaction", "qa", "closing"]
ScriptStatus = Literal["draft", "edited", "confirmed"]
ReplyMode = Literal["auto", "manual"]
SessionStatus = Literal["planned", "live", "ended", "cancelled"]
MetricsSource = Literal["manual", "import"]


def _check_no_blocked(v: str | None) -> str | None:
    if v is not None and contains_blocked(v):
        raise ValueError("文本包含敏感词")
    return v


def _check_text_tree(value: Any, field: str = "内容") -> Any:
    """递归校验 dict/list/str 中的文本不含敏感词。"""
    if isinstance(value, str):
        if contains_blocked(value):
            raise ValueError(f"{field}包含敏感词")
    elif isinstance(value, list):
        for item in value:
            _check_text_tree(item, field)
    elif isinstance(value, dict):
        for k, v in value.items():
            _check_text_tree(k, field)
            _check_text_tree(v, field)
    return value


# ============================================================
# 项目
# ============================================================


class LiveProjectCreate(BaseModel):
    shop_id: uuid.UUID
    title: str = Field(..., min_length=1, max_length=100)
    platform: Platform = "douyin"
    goal: str | None = Field(None, max_length=2000)
    promo_items: list[dict] | None = None
    ai_label_text: str | None = Field(None, max_length=200)
    engine_config: dict | None = None

    @field_validator("title", "goal", "ai_label_text")
    @classmethod
    def text_blocked(cls, v: str | None) -> str | None:
        return _check_no_blocked(v)

    @field_validator("promo_items")
    @classmethod
    def promo_blocked(cls, v: list[dict] | None) -> list[dict] | None:
        if v is not None:
            _check_text_tree(v, "优惠商品")
        return v

    @field_validator("engine_config")
    @classmethod
    def engine_blocked(cls, v: dict | None) -> dict | None:
        if v is not None:
            _check_text_tree(v, "引擎配置")
        return v


class LiveProjectUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=100)
    platform: Platform | None = None
    goal: str | None = Field(None, max_length=2000)
    promo_items: list[dict] | None = None
    ai_label_text: str | None = Field(None, max_length=200)
    engine_config: dict | None = None
    status: ProjectStatus | None = None

    @field_validator("title", "goal", "ai_label_text")
    @classmethod
    def text_blocked(cls, v: str | None) -> str | None:
        return _check_no_blocked(v)

    @field_validator("promo_items")
    @classmethod
    def promo_blocked(cls, v: list[dict] | None) -> list[dict] | None:
        if v is not None:
            _check_text_tree(v, "优惠商品")
        return v

    @field_validator("engine_config")
    @classmethod
    def engine_blocked(cls, v: dict | None) -> dict | None:
        if v is not None:
            _check_text_tree(v, "引擎配置")
        return v


class LiveProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    shop_id: uuid.UUID
    title: str
    platform: str
    goal: str | None = None
    promo_items: list | None = None
    ai_label_text: str | None = None
    engine_config: dict | None = None
    status: str
    created_at: datetime
    updated_at: datetime


class LiveProjectListResponse(BaseModel):
    items: list[LiveProjectOut]
    total: int
    page: int
    size: int


# ============================================================
# 数字人形象（org 维度）
# ============================================================


class LiveAvatarCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    avatar_type: AvatarType = "image"
    image_url: str | None = Field(None, max_length=2000)
    video_url: str | None = Field(None, max_length=2000)
    engine_base_url: str | None = Field(None, max_length=2000)
    voice_config: dict | None = None
    persona: dict | None = None
    status: AvatarStatus = "draft"

    @field_validator("name", "image_url", "video_url", "engine_base_url")
    @classmethod
    def text_blocked(cls, v: str | None) -> str | None:
        return _check_no_blocked(v)

    @field_validator("voice_config", "persona")
    @classmethod
    def json_blocked(cls, v: dict | None) -> dict | None:
        if v is not None:
            _check_text_tree(v, "形象配置")
        return v


class LiveAvatarUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    avatar_type: AvatarType | None = None
    image_url: str | None = Field(None, max_length=2000)
    video_url: str | None = Field(None, max_length=2000)
    engine_base_url: str | None = Field(None, max_length=2000)
    voice_config: dict | None = None
    persona: dict | None = None
    status: AvatarStatus | None = None

    @field_validator("name", "image_url", "video_url", "engine_base_url")
    @classmethod
    def text_blocked(cls, v: str | None) -> str | None:
        return _check_no_blocked(v)

    @field_validator("voice_config", "persona")
    @classmethod
    def json_blocked(cls, v: dict | None) -> dict | None:
        if v is not None:
            _check_text_tree(v, "形象配置")
        return v


class LiveAvatarOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    org_id: uuid.UUID
    name: str
    avatar_type: str
    image_url: str | None = None
    video_url: str | None = None
    engine_base_url: str | None = None
    engine_avatar_id: str | None = None
    engine_task_id: str | None = None
    voice_config: dict | None = None
    persona: dict | None = None
    status: str
    created_at: datetime
    updated_at: datetime


class LiveAvatarListResponse(BaseModel):
    items: list[LiveAvatarOut]
    total: int
    page: int
    size: int


# ============================================================
# 脚本
# ============================================================


class ScriptSegment(BaseModel):
    type: ScriptSegmentType
    title: str = Field(..., max_length=200)
    text: str = Field(..., max_length=10000)
    duration_sec: int = Field(..., ge=1, le=3600)
    cue: str | None = Field(None, max_length=500)

    @field_validator("title", "text", "cue")
    @classmethod
    def text_blocked(cls, v: str | None) -> str | None:
        return _check_no_blocked(v)


class ScriptGenerateRequest(BaseModel):
    tone: str | None = Field(None, max_length=50)
    duration_min: int | None = Field(None, ge=1, le=480)
    avatar_id: uuid.UUID | None = None

    @field_validator("tone")
    @classmethod
    def tone_blocked(cls, v: str | None) -> str | None:
        return _check_no_blocked(v)


class ScriptUpdateRequest(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=200)
    tone: str | None = Field(None, max_length=50)
    content: list[ScriptSegment] | None = None
    total_duration_sec: int | None = Field(None, ge=1)

    @field_validator("title", "tone")
    @classmethod
    def text_blocked(cls, v: str | None) -> str | None:
        return _check_no_blocked(v)


class ComplianceItem(BaseModel):
    key: str
    ok: bool
    detail: str


class ComplianceResult(BaseModel):
    pass_: bool = Field(alias="pass")
    items: list[ComplianceItem]

    model_config = ConfigDict(populate_by_name=True)


class LiveScriptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    avatar_id: uuid.UUID | None = None
    persona_snapshot: dict | None = None
    generation_batch: int
    title: str
    tone: str | None = None
    content: list | None = None
    total_duration_sec: int | None = None
    status: str
    is_archived: bool
    compliance: dict | None = None
    created_at: datetime
    updated_at: datetime


# ============================================================
# 弹幕互动配置
# ============================================================


class ReplyRule(BaseModel):
    trigger: str = Field(..., min_length=1, max_length=200)
    reply: str = Field(..., min_length=1, max_length=2000)
    mode: ReplyMode = "manual"

    @field_validator("trigger", "reply")
    @classmethod
    def text_blocked(cls, v: str) -> str:
        if contains_blocked(v):
            raise ValueError("文本包含敏感词")
        return v


class DanmakuConfigUpdate(BaseModel):
    persona: dict | None = None
    reply_rules: list[ReplyRule] | None = None
    sensitive_words: list[str] | None = None
    escalate_topics: list[str] | None = None

    @field_validator("persona")
    @classmethod
    def persona_blocked(cls, v: dict | None) -> dict | None:
        if v is not None:
            _check_text_tree(v, "人设")
        return v

    @field_validator("sensitive_words", "escalate_topics")
    @classmethod
    def words_blocked(cls, v: list[str] | None) -> list[str] | None:
        if v is not None:
            for w in v:
                if contains_blocked(w):
                    raise ValueError("文本包含敏感词")
        return v


class LiveDanmakuConfigOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    source_script_id: uuid.UUID | None = None
    persona: dict | None = None
    reply_rules: list | None = None
    sensitive_words: list | None = None
    escalate_topics: list | None = None
    created_at: datetime
    updated_at: datetime


# ============================================================
# 场次与复盘
# ============================================================


class LiveSessionCreate(BaseModel):
    script_id: uuid.UUID | None = None
    avatar_id: uuid.UUID | None = None
    scheduled_at: datetime
    duration_min: int | None = Field(None, ge=1, le=1440)
    operator_id: uuid.UUID | None = None
    notes: str | None = Field(None, max_length=2000)

    @field_validator("notes")
    @classmethod
    def notes_blocked(cls, v: str | None) -> str | None:
        return _check_no_blocked(v)


class LiveSessionUpdate(BaseModel):
    script_id: uuid.UUID | None = None
    avatar_id: uuid.UUID | None = None
    scheduled_at: datetime | None = None
    duration_min: int | None = Field(None, ge=1, le=1440)
    operator_id: uuid.UUID | None = None
    notes: str | None = Field(None, max_length=2000)
    duty_confirmed: bool | None = None
    ai_label_confirmed: bool | None = None
    status: SessionStatus | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None

    @field_validator("notes")
    @classmethod
    def notes_blocked(cls, v: str | None) -> str | None:
        return _check_no_blocked(v)


class LiveSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    script_id: uuid.UUID | None = None
    avatar_id: uuid.UUID | None = None
    scheduled_at: datetime
    duration_min: int | None = None
    status: str
    operator_id: uuid.UUID | None = None
    duty_confirmed: bool
    ai_label_confirmed: bool
    is_backfilled: bool
    notes: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class LiveSessionListResponse(BaseModel):
    items: list[LiveSessionOut]
    total: int
    page: int
    size: int


class MetricsCreate(BaseModel):
    metrics: dict
    source: MetricsSource = "manual"

    @field_validator("metrics")
    @classmethod
    def metrics_blocked(cls, v: dict) -> dict:
        _check_text_tree(v, "复盘数据")
        return v


class LiveSessionMetricOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    metrics: dict | None = None
    source: str
    ai_review: str | None = None
    created_at: datetime
    updated_at: datetime


class ReviewResponse(BaseModel):
    ai_review: str


# ============================================================
# 开播包
# ============================================================


class LiveExportBundle(BaseModel):
    script_markdown: str
    persona_json: dict
    wordlist: list[str]
    reply_rules: list[dict]
    compliance: dict
    engine_guide: str


class ComplianceCheckRequest(BaseModel):
    script_id: uuid.UUID | None = None


class AiGenerateImageRequest(BaseModel):
    """AI 生成数字人形象图请求：用户自定义形象描述。"""

    prompt: str = Field(..., min_length=2, max_length=500)

    @field_validator("prompt")
    @classmethod
    def text_blocked(cls, v: str) -> str:
        return _check_no_blocked(v)


class EngineAvatarCreateRequest(BaseModel):
    """形象 → 引擎 Avatar 生成：可覆盖引擎地址（不传则用形象已存 engine_base_url）。"""

    engine_base_url: str | None = Field(None, max_length=2000)

    @field_validator("engine_base_url")
    @classmethod
    def text_blocked(cls, v: str | None) -> str | None:
        return _check_no_blocked(v)


class EngineTestRequest(BaseModel):
    """本地引擎「连接测试」请求：健康检查 + 可选配置推送。

    base_url 可覆盖项目已存配置（前端测试未保存的表单地址）；不传则用项目
    engine_config.base_url。persona_json / wordlist 不传时自动按开播包导出同款
    优先级解析（persona：弹幕配置 → 当前活跃定稿脚本快照 → 默认占位；
    wordlist：弹幕配置 → 内置词库）。
    """

    base_url: str | None = None
    push_persona: bool = True
    push_wordlist: bool = True
    persona_json: dict | None = None
    wordlist: list[str] | None = None

    @field_validator("persona_json", "wordlist")
    @classmethod
    def engine_test_text_blocked(cls, v):
        if v is not None:
            _check_text_tree(v, "引擎测试内容")
        return v


class EngineTestResult(BaseModel):
    ok: bool
    base_url: str
    health: dict | None = None
    persona_push: dict | None = None
    wordlist_push: dict | None = None
    last_health_check: datetime | None = None
    error: str | None = None

