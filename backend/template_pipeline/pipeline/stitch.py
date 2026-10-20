# -*- coding: utf-8 -*-

# ---------------------------------------------------------------------------
# 多页拼接与等比缩放
# ---------------------------------------------------------------------------


def stitch_page_data(pages):
    """宽表被分页时, 把后续页横向拼接到第一页右边。

    横向延续的判定: 该页格子的 y 行位与第一页表格行位高度重合
    (同一批行被切到右边); 对不上说明是纵向分页(长表), 不拼。
    """
    base = pages[0]
    if len(pages) == 1 or not base['cells']:
        return base
    ys0 = sorted({c['y'] for c in base['cells']})
    margin = min([c['x'] for c in base['cells']]
                 + [r['x0'] for r in base['rules']])
    out = dict(base)
    out['cells'] = list(base['cells'])
    out['texts'] = list(base['texts'])
    out['rules'] = list(base['rules'])
    right = max([c['x'] + c['w'] for c in base['cells']]
                + [r['x1'] for r in base['rules']])
    stitched = 0
    row_off = (max(c['row'] for c in base['cells']) + 1
               if base['cells'] else 0)  # 行号全局唯一化, 供网格邻接判定
    for pg in pages[1:]:
        if not pg['cells']:
            break
        # 延续页自带大标题 -> 是另一张表 (多工作簿/多表单), 不是宽表续页
        if any(t.get('role') == 'title' for t in pg.get('texts') or []):
            print('分页含独立表名, 视为另一张表, 不横向拼接')
            break
        ys = [c['y'] for c in pg['cells']]
        hit = sum(1 for y in ys if any(abs(y - y0) <= 6 for y0 in ys0))
        if hit < len(ys) * 0.7:
            break  # 行位对不上 -> 纵向分页, 不拼
        # 分页按列边界切: 接缝 = 已拼内容的最右缘, 该页内容左 margin 对齐过来
        left = min([c['x'] for c in pg['cells']]
                   + [r['x0'] for r in pg['rules']])
        dx = right - left
        for c in pg['cells']:
            c = dict(c)
            c['x'] += dx
            c['row'] += row_off
            if 'lines' in c:
                c['lines'] = [dict(l, x=l['x'] + dx) if 'x' in l else l
                              for l in c['lines']]
            out['cells'].append(c)
        for t in pg['texts']:
            out['texts'].append(dict(t, x=t['x'] + dx))
        for r in pg['rules']:
            out['rules'].append({**r, 'x0': r['x0'] + dx,
                                 'x1': r['x1'] + dx})
        right = max(right, max([c['x'] + c['w'] for c in out['cells']
                                if c['x'] >= dx]
                               or [right]))
        row_off += max(c['row'] for c in pg['cells']) + 1
        stitched += 1
    if stitched:
        out['width'] = right + margin  # 右侧补一个对称 margin
        out['height'] = max(p['height'] for p in pages[:stitched + 1])
        print(f'宽表分页拼接: {stitched + 1} 页横向合并')
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
