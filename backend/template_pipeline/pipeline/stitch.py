# -*- coding: utf-8 -*-

# ---------------------------------------------------------------------------
# 多页拼接与等比缩放
# ---------------------------------------------------------------------------

import re


def _native_grid(page):
    """返回带原生工作表地址的 (row, col)，伪地址不参与分页判断。"""
    result = []
    for c in page.get('cells') or []:
        addr = c.get('addr') or ''
        m = re.search(r'!\$?([A-Za-z]+)\$?(\d+)$', addr)
        if not m:
            continue
        col = 0
        for ch in m.group(1).upper():
            col = col * 26 + ord(ch) - ord('A') + 1
        result.append((int(m.group(2)), col))
    return result


def _is_horizontal_continuation(base, previous, page):
    """只有存在横向表体延续证据时才拼接，无法判定时按纵向页处理。"""
    ys0 = sorted({c['y'] for c in base.get('cells') or []})
    ys = [c['y'] for c in page.get('cells') or []]
    if not ys0 or not ys:
        return False
    hit = sum(1 for y in ys if any(abs(y - y0) <= 6 for y0 in ys0))
    if hit < len(ys) * 0.7:
        return False

    # xlsx 语义对齐后的原生地址是明确证据：行集合相同且列向右增长才是
    # 横向续页；行向后增长/列仍为原区域则是纵向续页。地址歧义时不猜。
    prev_grid = _native_grid(previous)
    page_grid = _native_grid(page)
    if prev_grid and page_grid:
        prev_rows = {r for r, _ in prev_grid}
        page_rows = {r for r, _ in page_grid}
        row_overlap = len(prev_rows & page_rows) / max(1, len(page_rows))
        return (row_overlap >= 0.7 and
                min(c for _, c in page_grid) > max(c for _, c in prev_grid))

    # 无原生地址时采用保守几何证据：同一批行、前页表体贴近可打印区
    # 右缘，且没有延伸到页底。仅 y 重合不足以区分纵向续页。
    right = max([c['x'] + c['w'] for c in previous.get('cells') or []]
                + [r['x1'] for r in previous.get('rules') or []] or [0])
    bottom = max([c['y'] + c['h'] for c in previous.get('cells') or []]
                 + [r['y1'] for r in previous.get('rules') or []] or [0])
    if previous['height'] - bottom <= max(24, previous['height'] * 0.06):
        return False
    return previous['width'] - right <= max(24, previous['width'] * 0.03)


def stitch_page_data(pages):
    """把有明确横向延续证据的页拼到第一页右侧。

    横向拼接保持行号、累加列号，确保接缝两侧的 (row, col) 邻接连续。
    纵向页/独立表/空页不静默丢弃：逐页告警并记录在 _unstitched_pages；
    当前单页模板仍使用第一段，调用方可据元数据后续扩展多页输出。
    """
    base = pages[0]
    if len(pages) == 1:
        return base
    margin = min([c['x'] for c in base.get('cells') or []]
                 + [r['x0'] for r in base.get('rules') or []] or [0])
    out = dict(base)
    out['cells'] = list(base.get('cells') or [])
    out['texts'] = list(base.get('texts') or [])
    out['rules'] = list(base.get('rules') or [])
    right = max([c['x'] + c['w'] for c in out['cells']]
                + [r['x1'] for r in out['rules']] or [0])
    col_off = max([c['col'] + c.get('colspan', 1) for c in out['cells']]
                  or [0])
    stitched_pages = [base.get('source_page', 0)]
    offsets = [0.0]
    unstitched = []
    previous = base
    stopped = False
    for i, pg in enumerate(pages[1:], 1):
        page_no = pg.get('source_page', i)
        if stopped:
            unstitched.append(page_no)
            print(f'警告: 第 {page_no} 页保留为纵向分页，未并入当前单页数据')
            continue
        reason = None
        if not pg.get('cells'):
            reason = '无表格'
        elif any(t.get('role') == 'title' for t in pg.get('texts') or []):
            reason = '含独立表名'
        elif not _is_horizontal_continuation(base, previous, pg):
            reason = '无明确横向表体延续证据'
        if reason:
            print(f'警告: 第 {page_no} 页{reason}，保留为纵向分页，'
                  '未并入当前单页数据')
            unstitched.append(page_no)
            stopped = True
            continue

        # 接缝 = 已拼内容最右缘，该页内容左 margin 对齐过来。
        left = min([c['x'] for c in pg['cells']]
                   + [r['x0'] for r in pg.get('rules') or []])
        dx = right - left
        page_right = 0
        for c in pg['cells']:
            c = dict(c)
            c['x'] += dx
            c['col'] += col_off
            page_right = max(page_right, c['x'] + c['w'])
            if 'lines' in c:
                c['lines'] = [dict(l, x=l['x'] + dx) if 'x' in l else l
                              for l in c['lines']]
            out['cells'].append(c)
        for t in pg.get('texts') or []:
            out['texts'].append(dict(t, x=t['x'] + dx))
        for r in pg.get('rules') or []:
            shifted = {**r, 'x0': r['x0'] + dx, 'x1': r['x1'] + dx}
            out['rules'].append(shifted)
            page_right = max(page_right, shifted['x1'])
        right = max(right, page_right)
        col_off += max(c['col'] + c.get('colspan', 1) for c in pg['cells'])
        stitched_pages.append(page_no)
        offsets.append(dx)
        previous = pg
        print(f'宽表分页拼接: 第 {page_no} 页横向合并')

    if len(stitched_pages) > 1:
        out['width'] = right + margin  # 右侧补一个对称 margin
        out['height'] = max(p['height'] for p in pages[:len(stitched_pages)])
    out['_stitch'] = {'pages': stitched_pages, 'offsets': offsets,
                      'width': out['width'], 'height': out['height']}
    out['_unstitched_pages'] = unstitched
    return out


def scale_data(data, s):
    """对标准 JSON 做纯数学等比缩放 (坐标/字号都乘 s), 相对位置不变。"""
    if abs(s - 1.0) < 1e-6:
        return data
    out = dict(data)
    cells = []
    for c in data['cells']:
        c = dict(c)
        for k in ('x', 'y', 'w', 'h'):
            c[k] = c[k] * s
        if 'size' in c:
            c['size'] *= s
        if 'font_size' in c:
            c['font_size'] *= s
        if 'lines' in c:
            ls = []
            for l in c['lines']:
                l = dict(l)
                for k in ('x', 'y', 'w', 'h'):
                    if k in l:
                        l[k] *= s
                if 'size' in l:
                    l['size'] *= s
                ls.append(l)
            c['lines'] = ls
        cells.append(c)
    out['cells'] = cells
    out['texts'] = [dict(t, x=t['x'] * s, y=t['y'] * s, size=t['size'] * s,
                         w=t['w'] * s if t.get('w') else t.get('w'))
                    for t in data.get('texts', [])]
    out['rules'] = [dict(r, x0=r['x0'] * s, y0=r['y0'] * s,
                         x1=r['x1'] * s, y1=r['y1'] * s,
                         width=r['width'] * s)
                    for r in data.get('rules', [])]
    out['width'] = data['width'] * s
    out['height'] = data['height'] * s
    return out
