"""
爬虫基类。所有平台爬虫实现此接口。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class CrawlResult:
    """爬虫执行结果。"""
    def __init__(
        self,
        success: bool,
        data: list[dict[str, Any]] | None = None,
        error: str | None = None,
        stats: dict[str, Any] | None = None,
    ):
        self.success = success
        self.data = data or []
        self.error = error
        self.stats = stats or {}


class BaseCrawler(ABC):
    """爬虫抽象基类。"""

    @abstractmethod
    def search_notes(self, query: str, limit: int = 20) -> CrawlResult:
        """搜索笔记。"""
        ...

    @abstractmethod
    def get_note_detail(self, note_url: str) -> CrawlResult:
        """获取笔记详情。"""
        ...

    @abstractmethod
    def get_comments(self, note_url: str) -> CrawlResult:
        """获取笔记评论。"""
        ...

    @abstractmethod
    def get_user_notes(self, user_url: str) -> CrawlResult:
        """获取用户笔记。"""
        ...
