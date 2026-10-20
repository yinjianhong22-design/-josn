# -*- coding: utf-8 -*-

# ---------------------------------------------------------------------------
# PDF 矢量线段提取 (rules -> 掩码/线坐标)
# ---------------------------------------------------------------------------

from ..common import cv2, np, _import_pymupdf


def _merge_positions(a, b, tol=6):
    """合并两个线坐标列表 (OpenCV 检测值与矢量线段聚类值), 相近的取平均。"""
    vals = sorted(list(a) + list(b))
    groups = []
    for v in vals:
        if groups and v - groups[-1][-1] <= tol:
            groups[-1].append(v)
        else:
            groups.append([v])
    return [int(round(sum(g) / len(g))) for g in groups]


def rules_to_masks(rules, shape, tol=6):
    """把矢量线段渲染成横/竖线掩码, 并直接聚出线坐标。

    用于电子档 PDF 中 OpenCV 形态学检测失效的场景 (如只占页面一角的
    小表格: 核长/覆盖度按整页比例取, 会把短线整批滤掉)。
    返回 (横线掩码, 竖线掩码, 横线坐标, 竖线坐标)。
    """
    horiz = np.zeros(shape, np.uint8)
    vert = np.zeros(shape, np.uint8)
    hs, vs = [], []
    for rl in rules:
        x0, y0, x1, y1 = rl['x0'], rl['y0'], rl['x1'], rl['y1']
        th = max(1, int(round(rl.get('width', 1))))
        if abs(y1 - y0) <= 2 and abs(x1 - x0) > 3:
            y = int(round((y0 + y1) / 2))
            cv2.line(horiz, (int(min(x0, x1)), y), (int(max(x0, x1)), y),
                     255, th)
            hs.append(y)
        elif abs(x1 - x0) <= 2 and abs(y1 - y0) > 3:
            x = int(round((x0 + x1) / 2))
            cv2.line(vert, (x, int(min(y0, y1))), (x, int(max(y0, y1))),
                     255, th)
            vs.append(x)

    def cluster(vals):
        vals.sort()
        groups = []
        for v in vals:
            if groups and v - groups[-1][-1] <= tol:
                groups[-1].append(v)
            else:
                groups.append([v])
        return [int(round(sum(g) / len(g))) for g in groups]

    return horiz, vert, cluster(hs), cluster(vs)


def extract_pdf_rules(path, page, dpi):
    """提取 PDF 里的矢量线段(表格线/下划线等), 返回整页像素坐标线段列表。

    电子档的线本来就是矢量数据, 坐标和线宽都是精确值; 只保留横平竖直的
    线段和细长矩形(填充式粗线)。返回 [{'x0','y0','x1','y1','width'}],
    坐标为渲染图像素, width 同样按 dpi/72 换算成像素。
    """
    fitz = _import_pymupdf()
    doc = fitz.open(path)
    if not (0 <= page < len(doc)):
        doc.close()
        return []
    drawings = doc[page].get_drawings()
    doc.close()

    scale = dpi / 72.0
    rules = []
    for d in drawings:
        w = max(d.get('width') or 0.5, 0.1)
        for item in d['items']:
            if item[0] == 'l':              # 线段
                p1, p2 = item[1], item[2]
                x0, y0, x1, y1 = p1.x, p1.y, p2.x, p2.y
            elif item[0] == 're':           # 细长矩形 = 填充的线
                r = item[1]
                if r.height <= 3 and r.width > 5:
                    y0 = y1 = (r.y0 + r.y1) / 2
                    x0, x1 = r.x0, r.x1
                    w = max(w, r.height)
                elif r.width <= 3 and r.height > 5:
                    x0 = x1 = (r.x0 + r.x1) / 2
                    y0, y1 = r.y0, r.y1
                    w = max(w, r.width)
                else:
                    continue
            else:
                continue
            if abs(y0 - y1) <= 1 or abs(x0 - x1) <= 1:
                rules.append({'x0': x0 * scale, 'y0': y0 * scale,
                              'x1': x1 * scale, 'y1': y1 * scale,
                              'width': w * scale})
    return rules
