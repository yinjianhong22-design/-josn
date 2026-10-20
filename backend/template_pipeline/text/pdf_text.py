# -*- coding: utf-8 -*-

# ---------------------------------------------------------------------------
# PDF 文字层提取 (免 OCR, 坐标精准)
# ---------------------------------------------------------------------------

from ..common import _import_pymupdf
from .ocr_free import _classify_line_roles


def extract_pdf_text(path, page, dpi, cells):
    """探测并读取 PDF 文字层: 电子档提取 span 级信息, 扫描件返回 None。

    每个 span 带字体/字号/颜色/加粗/基线坐标(PDF point -> 渲染像素换算,
    缩放比 = dpi/72)。以文字行中心点判定归属格子; 格内多行排序拼接。
    格外行(页眉/标题/页码等)按"字号聚类 + 坐标规则"标注语义角色后保留。
    返回 ({(row,col): 文本}, [游离文字]); 无文字层(扫描件)返回 (None, [])。
    """
    fitz = _import_pymupdf()
    doc = fitz.open(path)
    if not (0 <= page < len(doc)):
        doc.close()
        return None, []
    pg = doc[page]
    d = pg.get_text('rawdict')
    page_w = pg.rect.width * dpi / 72.0
    doc.close()

    scale = dpi / 72.0
    lines = []
    for b in d['blocks']:
        if b.get('type') != 0:
            continue
        for l in b['lines']:
            text = ''.join(ch['c'] for s in l['spans']
                           for ch in s.get('chars', [])).strip()
            if not text:
                continue
            # 逐字符定位: WPS/Excel 转出的行常用前导空格做缩进/对齐,
            # span 的 origin/bbox 把空格宽度也算进去, 直接用会让文字
            # 整体左移、宽度虚增(触发错误的逐字均摊); 改用非空格字符
            # 的实际 bbox 和首个非空格字符的基线起点
            kept = [(s, ch) for s in l['spans'] for ch in s.get('chars', [])
                    if ch['c'].strip()]
            x0 = min(ch['bbox'][0] for _, ch in kept) * scale
            y0 = min(ch['bbox'][1] for _, ch in kept) * scale
            x1 = max(ch['bbox'][2] for _, ch in kept) * scale
            y1 = max(ch['bbox'][3] for _, ch in kept) * scale
            ox, oy = kept[0][1]['origin']
            seen, spans_k = set(), []
            for s, _ in kept:
                if id(s) not in seen:
                    seen.add(id(s))
                    spans_k.append(s)
            s0 = max(spans_k, key=lambda s: s['size'])  # 主导 span
            # 分段信息: 同一行里字体/位置不同的 span 分开记录,
            # 游离文字按段独立落位(如 "监理单位:___  编号:JB12..." 一行两段)
            segs = []
            for s in spans_k:
                schars = [ch for ch in s.get('chars', []) if ch['c'].strip()]
                segs.append({
                    'text': ''.join(ch['c'] for ch in s['chars']).strip(),
                    'ox': schars[0]['origin'][0] * scale,
                    'oy': schars[0]['origin'][1] * scale,
                    'size': s['size'], 'font': s['font'],
                    'color': '#%06x' % s['color'],
                    'bold': bool(s['flags'] & 16)
                            or 'bold' in s['font'].lower(),
                })
            lines.append({
                'cx': (x0 + x1) / 2, 'cy': (y0 + y1) / 2,
                'x0': x0, 'y0': y0, 'x1': x1, 'y1': y1,
                'ox': ox * scale, 'oy': oy * scale,
                'size': s0['size'], 'font': s0['font'],
                'color': '#%06x' % s0['color'],
                'bold': bool(s0['flags'] & 16)
                        or 'bold' in s0['font'].lower(),
                'text': text, 'segs': segs,
                'vertical': abs(l['dir'][0]) < 0.5,
            })
    if not lines:
        return None, []

    _classify_line_roles(lines, page_w)

    texts = {}
    assigned = set()
    for c in cells:
        inside = []
        for k, l in enumerate(lines):
            if (c['x'] - 2 <= l['cx'] <= c['x'] + c['w'] + 2
                    and c['y'] - 2 <= l['cy'] <= c['y'] + c['h'] + 2):
                inside.append(l)
                assigned.add(k)
        if not inside:
            continue
        vertical = any(l['vertical'] for l in inside)
        # 横排按 y 再按 x 排序; 竖排按 x 再按 y 排序
        inside.sort(key=lambda l: (-l['x0'], l['y0']) if vertical
                    else (l['y0'], l['x0']))
        # 每行保留基线坐标/字号/字体/颜色/原始宽度(供还原字符间距)
        c['lines'] = [{'x': l['ox'], 'y': l['oy'], 'size': l['size'],
                       'font': l['font'], 'color': l['color'],
                       'bold': l['bold'], 'text': l['text'],
                       'w': l['x1'] - l['x0']}
                      for l in inside]
        c['font'] = max(inside, key=lambda l: l['size'])['font']  # 主导字体
        if vertical:
            texts[(c['row'], c['col'])] = '\n'.join(l['text'] for l in inside)
            continue
        # 同一视觉行(y 接近)的多段文字横向合并 (如 "年  月  日" 是 3 个 span)
        merged = []
        for l in inside:
            tol = max(6.0, l['size'] * scale * 0.5)
            if merged and abs(l['y0'] - merged[-1][0]['y0']) <= tol:
                merged[-1].append(l)
            else:
                merged.append([l])
        rows = []
        for grp in merged:
            grp.sort(key=lambda l: l['x0'])
            rows.append(''.join(l['text'] for l in grp))
        texts[(c['row'], c['col'])] = '\n'.join(rows)

    # 游离文字按 span 分段输出: 每段带自己的基线/字体/颜色,
    # 一行里左右分开的多段文字(编号/日期等)各自精确落位
    free = []
    for k, l in enumerate(lines):
        if k in assigned:
            continue
        for seg in l['segs']:
            free.append({'x': seg['ox'], 'y': seg['oy'], 'size': seg['size'],
                         'font': seg['font'], 'color': seg['color'],
                         'bold': seg['bold'], 'role': l['role'],
                         'text': seg['text']})
    free.sort(key=lambda t: (t['y'], t['x']))
    return texts, free
