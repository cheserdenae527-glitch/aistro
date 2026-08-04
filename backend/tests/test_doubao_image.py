"""豆包生图服务单元测试 — 不依赖网络。"""
from __future__ import annotations

import asyncio
import io

import pytest
from PIL import Image

from app.ai.doubao_image import (
    ImageGenError,
    _generate_image,
    _map_http_error,
    _normalize_ref_image,
    _parse_sse_urls,
)


def _make_png_bytes(size: tuple[int, int] = (64, 64)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color=(230, 60, 40)).save(buf, format="PNG")
    return buf.getvalue()


def test_normalize_ref_image_converts_to_png():
    data, mime = _normalize_ref_image(_make_png_bytes(), "image/webp")
    assert mime == "image/png"
    img = Image.open(io.BytesIO(data))
    assert img.format == "PNG"


def test_normalize_ref_image_rejects_invalid_bytes():
    with pytest.raises(ImageGenError) as exc:
        _normalize_ref_image(b"not an image")
    assert exc.value.status_code == 400


def test_normalize_ref_image_rejects_oversize():
    with pytest.raises(ImageGenError) as exc:
        _normalize_ref_image(b"x" * (10 * 1024 * 1024 + 1))
    assert exc.value.status_code == 400


def test_parse_sse_urls_returns_ordered_urls():
    lines = [
        'data: {"type":"image_generation.partial_succeeded","image_index":2,"url":"u2"}',
        'data: {"type":"image_generation.partial_succeeded","image_index":0,"url":"u0"}',
        'data: {"type":"image_generation.partial_succeeded","image_index":3,"url":"u3"}',
        'data: {"type":"image_generation.partial_succeeded","image_index":1,"url":"u1"}',
        'data: {"type":"image_generation.completed","usage":{"generated_images":4}}',
        "data: [DONE]",
    ]
    assert _parse_sse_urls(lines) == ["u0", "u1", "u2", "u3"]


def test_parse_sse_urls_rejects_error_event():
    lines = [
        'data: {"type":"image_generation.failed","message":"bad prompt"}',
    ]
    with pytest.raises(ImageGenError) as exc:
        _parse_sse_urls(lines)
    assert exc.value.status_code == 502
    assert exc.value.detail == "bad prompt"


def test_parse_sse_urls_rejects_empty_stream():
    with pytest.raises(ImageGenError) as exc:
        _parse_sse_urls(["data: [DONE]"])
    assert exc.value.status_code == 502


def test_map_http_error_400():
    err = _map_http_error(400, b'{"error":{"message":"size invalid"}}')
    assert err.status_code == 400
    assert err.detail == "size invalid"


def test_generate_image_requests_four_and_downloads(monkeypatch):
    png_bytes = _make_png_bytes()
    captured: dict = {}

    async def fake_stream(prompt, size, ref_data_url, on_progress=None):
        captured["prompt"] = prompt
        captured["size"] = size
        captured["ref_data_url"] = ref_data_url
        return [f"http://img/{i}" for i in range(4)]

    async def fake_download(url):
        return png_bytes, "image/png"

    monkeypatch.setattr("app.ai.doubao_image._stream_image_urls", fake_stream)
    monkeypatch.setattr("app.ai.doubao_image._download_image", fake_download)

    results = asyncio.run(_generate_image("a round logo", "2048x2048"))

    assert captured["size"] == "2048x2048"
    assert captured["ref_data_url"] is None
    assert "请生成4张风格统一" in captured["prompt"]
    assert len(results) == 4


def test_generate_image_with_ref_uses_png_data_url(monkeypatch):
    png_bytes = _make_png_bytes()
    captured: dict = {}

    async def fake_stream(prompt, size, ref_data_url, on_progress=None):
        captured["ref_data_url"] = ref_data_url
        captured["prompt"] = prompt
        return [f"http://img/{i}" for i in range(4)]

    async def fake_download(url):
        return png_bytes, "image/png"

    monkeypatch.setattr("app.ai.doubao_image._stream_image_urls", fake_stream)
    monkeypatch.setattr("app.ai.doubao_image._download_image", fake_download)

    results = asyncio.run(
        _generate_image(
            "same style logo",
            "2048x2048",
            ref_data=_make_png_bytes(),
            ref_mime="image/webp",
        )
    )

    assert captured["ref_data_url"].startswith("data:image/png;base64,")
    assert "必须保留锚点图中的核心主体" in captured["prompt"]
    assert len(results) == 4
def test_stream_image_urls_reports_progress(monkeypatch):
    """流式 partial_succeeded 逐张到达时 on_progress 递增上报。"""
    from app.ai.doubao_image import _stream_image_urls

    lines = [
        'data: {"type":"image_generation.partial_succeeded","image_index":0,"url":"u0"}',
        'data: {"type":"image_generation.partial_succeeded","image_index":1,"url":"u1"}',
        'data: {"type":"image_generation.completed","usage":{"generated_images":2}}',
        "data: [DONE]",
    ]

    class _FakeStream:
        status_code = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def aread(self):
            return b""

        async def aiter_lines(self):
            for line in lines:
                yield line

    class _FakeClient:
        def __init__(self, timeout=None):
            pass

        def stream(self, *a, **k):
            return _FakeStream()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr("app.ai.doubao_image.httpx.AsyncClient", _FakeClient)

    calls: list[tuple[int, int]] = []

    async def on_progress(done, total):
        calls.append((done, total))

    urls = asyncio.run(
        _stream_image_urls("p", "2K", None, on_progress=on_progress)
    )
    assert urls == ["u0", "u1"]
    assert calls == [(1, 4), (2, 4)]
