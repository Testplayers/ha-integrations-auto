"""简单图形验证码识别：颜色聚类分割 + 模板匹配（旋转/平移鲁棒）"""
from __future__ import annotations

import io
import logging

from PIL import Image

from .const import TEMPLATES, TMPL_SIZE

_LOGGER = logging.getLogger(__name__)

INK_THRESHOLD = 225  # RGB 最小通道低于此视为笔画（可捕获浅色字符）
MIN_CLUSTER = 12     # 颜色簇最小像素数


def _cluster_chars(img: Image.Image) -> list[list[tuple[int, int]]]:
    """按颜色聚类，返回各字符的像素点集（按 x 排序）"""
    w, h = img.size
    px = img.load()
    clusters: dict[tuple[int, int, int], list[tuple[int, int]]] = {}
    for x in range(w):
        for y in range(h):
            r, g, b = px[x, y]
            if min(r, g, b) >= INK_THRESHOLD:
                continue
            key = (r // 48, g // 48, b // 48)
            clusters.setdefault(key, []).append((x, y))

    boxes = []
    for key, pts in clusters.items():
        if len(pts) < MIN_CLUSTER:
            continue
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        boxes.append([min(xs), min(ys), max(xs) + 1, max(ys) + 1, len(pts), key, pts])

    # 相近色合并（x 区间大量重叠视为同一字符）
    merged: list[list] = []
    for box in sorted(boxes, key=lambda b: -b[4]):
        x0, y0, x1, y1, n, key, pts = box
        placed = False
        for m in merged:
            ox = min(m[2], x1) - max(m[0], x0)
            if ox > 0 and ox > 0.6 * min(m[2] - m[0], x1 - x0):
                m[0] = min(m[0], x0); m[1] = min(m[1], y0)
                m[2] = max(m[2], x1); m[3] = max(m[3], y1)
                m[4] += n; m[6].extend(pts)
                placed = True
                break
        if not placed:
            merged.append(box)

    out = [m for m in merged if (m[2] - m[0]) >= 3]
    out.sort(key=lambda m: m[0])
    return [m[6] for m in out]


def _char_bits(pts: list[tuple[int, int]]) -> list[int]:
    """字符像素集 → 归一化位图"""
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    x0, x1 = min(xs), max(xs) + 1
    y0, y1 = min(ys), max(ys) + 1
    mw, mh = x1 - x0, y1 - y0
    if mw < 3 or mh < 3:
        return []
    grid = Image.new("L", (mw, mh), 255)
    gpx = grid.load()
    for x, y in pts:
        gpx[x - x0, y - y0] = 0
    grid = grid.resize(TMPL_SIZE)
    return [1 if p < 128 else 0 for p in grid.getdata()]


def solve_captcha(jpeg: bytes) -> str:
    """识别 4-6 位彩色字符验证码，失败返回空串"""
    try:
        img = Image.open(io.BytesIO(jpeg)).convert("RGB")
    except Exception:
        return ""

    char_pts = _cluster_chars(img)
    if not 4 <= len(char_pts) <= 6:
        _LOGGER.debug("颜色聚类得到 %d 个字符，放弃", len(char_pts))
        return ""

    result = []
    for pts in char_pts:
        bits = _char_bits(pts)
        if not bits:
            return ""
        best_ch, best_d = "", None
        for ch, tmpl_list in TEMPLATES.items():
            for tmpl in tmpl_list:
                d = sum(abs(u - v) for u, v in zip(bits, tmpl))
                if best_d is None or d < best_d:
                    best_ch, best_d = ch, d
        if not best_ch:
            return ""
        result.append(best_ch)

    code = "".join(result)
    _LOGGER.debug("验证码识别结果: %s (%d 字符)", code, len(char_pts))
    return code
