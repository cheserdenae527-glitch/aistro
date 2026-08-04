"""内容工坊 QA — 4-band 密度（PIL）+ 溢出/底部空白（DOM 指标）。

规则（移植 validate-social-deck 核心，SPEC-CONTENT-STUDIO 4.3）：
- 内容带覆盖 >= 75% 画布高（按行统计，行内任意内容像素即算覆盖）
- 无连续两条 justified-empty 带（连续两带占用 < 15%）
- 空带至多一条（占用 < 15% 的带数量 <= 1）
- 溢出 <= 4px
- 底部空白 <= 190px（安全区下界 + 容差）

说明：像素级字形行之间会留空隙，与 DOM line-box 统计不一致；这里对内容行做
<=30px 的间隙闭合（形态学 close），等效于把整行文本框计入覆盖，与 validate-social-deck
的 rows 位图口径一致。
"""
from __future__ import annotations

import io

from PIL import Image

_GAP_FILL_PX = 30


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _is_content(px: tuple[int, int, int], paper: tuple[int, int, int]) -> bool:
    return abs(px[0] - paper[0]) + abs(px[1] - paper[1]) + abs(px[2] - paper[2]) > 30


def analyze_density(png: bytes, paper_hex: str) -> dict:
    """按 360px 水平带统计内容像素，返回占用率与判定。"""
    img = Image.open(io.BytesIO(png)).convert("RGB")
    width, height = img.size
    paper = _hex_to_rgb(paper_hex)
    band_h = height // 4
    step = 4
    gap_limit = max(1, _GAP_FILL_PX // step)

    # 按采样行标记是否有内容像素
    row_count = (height + step - 1) // step
    filled = [False] * row_count
    for y in range(0, height, step):
        idx = y // step
        for x in range(0, width, step):
            if _is_content(img.getpixel((x, y)), paper):
                filled[idx] = True
                break

    # 间隙闭合：内容行之间的非内容行（<= gap_limit 行）视为内容，等效行框覆盖
    closed = list(filled)
    i = 0
    while i < row_count:
        if filled[i]:
            i += 1
            continue
        j = i
        while j < row_count and not filled[j]:
            j += 1
        # 若间隙两端都有内容且长度 <= gap_limit，闭合
        if i > 0 and j < row_count and (j - i) <= gap_limit:
            for k in range(i, j):
                closed[k] = True
        i = max(j, i + 1)

    # 按带统计
    occupancy: list[float] = []
    for band in range(4):
        start = band * band_h // step
        end = min((band + 1) * band_h // step, row_count)
        total = end - start
        occ = sum(1 for k in range(start, end) if closed[k]) / total if total else 0.0
        occupancy.append(occ)

    total = sum(occupancy) / 4
    issues: list[str] = []
    if total < 0.745:
        issues.append("密度不足：内容覆盖低于 75%")
    for i in range(3):
        if occupancy[i] < 0.15 and occupancy[i + 1] < 0.15:
            issues.append(f"第 {i + 1}-{i + 2} 带连续空白")
            break
    if sum(1 for o in occupancy if o < 0.15) > 1:
        issues.append("空带数量超过 1 条")

    return {
        "pass": not issues,
        "coverage": round(total * 100, 1),
        "bands": [round(o * 100, 1) for o in occupancy],
        "issues": issues,
    }


def build_qa_report(png: bytes, metrics: dict, paper_hex: str) -> dict:
    density = analyze_density(png, paper_hex)
    overflow = int(metrics.get("overflow", 0))
    bottom_gap = int(metrics.get("bottom_gap", 0))
    overflow_ok = overflow <= 4
    bottom_ok = bottom_gap <= 190

    issues: list[str] = []
    issues.extend(density["issues"])
    if not overflow_ok:
        issues.append("内容溢出画布")
    if not bottom_ok:
        issues.append("底部空白过大")

    return {
        "pass": density["pass"] and overflow_ok and bottom_ok,
        "checks": {
            "density": {
                "pass": density["pass"],
                "coverage": density["coverage"],
                "bands": density["bands"],
                "issues": density["issues"],
            },
            "overflow": {"pass": overflow_ok, "overflow_px": overflow},
            "bottom_blank": {"pass": bottom_ok, "bottom_gap_px": bottom_gap},
        },
        "issues": issues,
    }
