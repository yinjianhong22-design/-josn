# -*- coding: utf-8 -*-

# ---------------------------------------------------------------------------
# 版面分析 (文字区域 / 图片块 / 行切分)
# ---------------------------------------------------------------------------

from ..common import cv2, np


def analyze_layout(bw, horiz_c, vert_c, min_area=200):
    """OpenCV 版面分析: 页面内容边界 + 文字块/图片块外接矩形。

    从二值图中剔除表格线得到纯内容掩码; 文字经闭运算聚块后取轮廓。
    填充密度高的块判为图片块, 其余为文字块。
    返回 (纯内容掩码, 块列表, 页面内容边界)。
    """
    content = bw.copy()
    content[horiz_c > 0] = 0
    content[vert_c > 0] = 0
    h, w = content.shape
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT,
                                       (max(15, w // 80), max(8, h // 150)))
    merged = cv2.morphologyEx(content, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(merged, cv2.RETR_EXTERNAL,
                                   cv2.CHAIN_APPROX_SIMPLE)
    blocks = []
    for c in contours:
        x, y, cw, ch = cv2.boundingRect(c)
        if cw * ch < min_area:
            continue
        density = content[y:y + ch, x:x + cw].mean() / 255
        blocks.append({'x': int(x), 'y': int(y), 'w': int(cw), 'h': int(ch),
                       'type': 'image' if density > 0.5 else 'text'})
    blocks.sort(key=lambda b: (b['y'], b['x']))

    cols = np.where(content.any(axis=0))[0]
    rows = np.where(content.any(axis=1))[0]
    bounds = None
    if cols.size and rows.size:
        bounds = {'x': int(cols[0]), 'y': int(rows[0]),
                  'w': int(cols[-1] - cols[0]), 'h': int(rows[-1] - rows[0])}
    return content, blocks, bounds


def split_text_lines(content, rect, gap=2, min_h=5):
    """横向投影(波峰波谷)在矩形内切出每行文字, 返回整页坐标 [(y0, y1)]。

    行高(y1-y0)可直接用于约束还原文本的字号: size_pt ≈ 行高*72/dpi*0.75。
    """
    x, y, w, h = rect
    sub = content[y:y + h, x:x + w]
    if sub.size == 0:
        return []
    on = (sub > 0).sum(axis=1) > 0
    runs = []
    i, n = 0, len(on)
    while i < n:
        if on[i]:
            j = i
            while j + 1 < n and (on[j + 1] or
                                 (j + gap < n and on[j + 1:j + gap + 1].any())):
                j += 1
            if j - i + 1 >= min_h:
                runs.append((y + i, y + j + 1))
            i = j + 1
        else:
            i += 1
    return runs
