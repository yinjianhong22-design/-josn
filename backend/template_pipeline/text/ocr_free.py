# -*- coding: utf-8 -*-

# ---------------------------------------------------------------------------
# 格外文字块 OCR + 行角色标注
# ---------------------------------------------------------------------------

from importlib import import_module as _import_module

_content = _import_module('..layout.content', __package__)
split_text_lines = _content.split_text_lines


def _classify_line_roles(lines, page_w):
    """字号聚类 + 坐标规则, 给每行文字定语义角色 (title/heading/body)。

    以字号中位数为正文基准: 明显大于正文且接近页面水平居中 -> 标题;
    明显大于正文但不居中 -> 小标题; 其余为正文。
    """
    if not lines:
        return
    sizes = sorted(l['size'] for l in lines)
    body = sizes[len(sizes) // 2]
    for l in lines:
        centered = abs(l['cx'] - page_w / 2) < page_w * 0.12
        if l['size'] >= body * 1.3:
            l['role'] = 'title' if centered else 'heading'
        elif l['size'] >= body * 1.12:
            l['role'] = 'heading'
        else:
            l['role'] = 'body'


def ocr_free_blocks(img, blocks, cells, content, backend, dpi):
    """扫描件/图片路径: OCR 表格线框外的文字块, 转成游离文字列表。

    每个块按投影切行, 行高换算字号(size_pt = 行高*72/dpi*0.75),
    基线取行底上 80% 处, 产出结构与 PDF 文字层路径的游离文字一致。
    """
    pseudo = []
    for k, b in enumerate(blocks):
        if b['type'] != 'text':
            continue
        cx, cy = b['x'] + b['w'] / 2, b['y'] + b['h'] / 2
        if any(c['x'] - 2 <= cx <= c['x'] + c['w'] + 2
               and c['y'] - 2 <= cy <= c['y'] + c['h'] + 2 for c in cells):
            continue
        pseudo.append({'row': -1, 'col': k, 'x': b['x'], 'y': b['y'],
                       'w': b['w'], 'h': b['h']})
    if not pseudo:
        return []
    print(f'格外文字块 {len(pseudo)} 个, OCR 中...')
    res = backend(img, pseudo) or {}
    free = []
    for p in pseudo:
        t = res.get((p['row'], p['col']))
        if not t:
            continue
        ols = t.split('\n')
        spans = split_text_lines(content, (p['x'], p['y'], p['w'], p['h']))
        if len(spans) != len(ols):
            step = p['h'] / len(ols)  # 行数对不上: 块高均分兜底
            spans = [(p['y'] + int(i * step), p['y'] + int((i + 1) * step))
                     for i in range(len(ols))]
        for (y0, y1), txt in zip(spans, ols):
            lh = y1 - y0
            free.append({'x': p['x'], 'y': y0 + lh * 0.8,
                         'size': lh * 72 / dpi * 0.75,
                         'color': '#000000', 'bold': False, 'role': 'body',
                         'text': txt, 'cx': p['x'] + p['w'] / 2})
    free.sort(key=lambda t: (t['y'], t['x']))
    return free
