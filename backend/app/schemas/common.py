"""通用 Pydantic schema。"""
from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class PaginatedResponse(BaseModel):
    items: list[Any]
    total: int
    page: int
    size: int
