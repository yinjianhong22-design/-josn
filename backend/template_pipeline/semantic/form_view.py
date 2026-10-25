# -*- coding: utf-8 -*-

# ---------------------------------------------------------------------------
# form 可索引视图 (扁平字段文档)
# ---------------------------------------------------------------------------

from ..common import _NO_LABEL_PREFIX


def build_form_view(data):
    """把 fields/table_fields 整理成可索引的 form 视图, 嵌入 data['form']。

    为后续建立索引设计, 不是简单组合:
    - 每个字段是一条扁平文档: name/mode/addr/几何坐标全在同一层,
      索引导入时无需展开嵌套对象;
    - 每条有全局唯一 id (F01..), 重名字段 (如两个"年月日") 按 id 区分,
      name 只做匹配键;
    - 同名/易混字段带 context: 同行最近左侧标签 (如 年月日@抽检时间),
      供检索时消歧;
    - 值格几何 (x/y/w/h, 像素, 基于 data['dpi']) 平铺在字段上,
      索引命中即可直接渲染, 不必回 cells 查表。
    mode 语义:
      cell    值写入空格 (改 value_addr 对应格 text)
      append  值追加在同行标签之后 (label/value 同格)
      replace 整格替换 (占位文字视为示例值)
      inline  同行冒号内联, 替换 prefix 之后的文本
    游离文字的值宽按字号估算 (estimated=true)。渲染层 cells/texts/rules
    保持不变, index.html / 前端复现层照常消费。
    """
    by_addr = {}
    cells = data['cells']
    for c in cells:
        if c.get('addr'):
            by_addr[c['addr']] = c
    for i, t in enumerate(data.get('texts') or []):
        by_addr[t['addr'] if t.get('addr') else f'#T{i}'] = t
    by_grid = {(c['row'], c['col']): c for c in cells}

    def _flat(addr):
        """addr -> 扁平几何/文本属性 (px); 游离文字宽度按字号估算。"""
        ent = by_addr.get(addr)
        if ent is None:
            return {'addr': addr}
        d = {'addr': addr,
             'x': round(ent['x'], 1), 'y': round(ent['y'], 1),
             'w': round(ent.get('w') or 0, 1),
             'h': round(ent.get('h') or 0, 1)}
        if ent.get('text'):
            d['text'] = ent['text']
        if ent.get('size'):
            d['size'] = round(ent['size'], 2)
        if ent.get('fillable'):
            d['fillable'] = True
        if 'w' not in ent and ent.get('size'):   # 游离文字: 无实体宽
            n = len(''.join(str(ent.get('text') or '').split()))
            d['w'] = round(n * ent['size'] * data.get('dpi', 96) / 72.0, 1)
            d['estimated'] = True
        return d

    def _context(ent):
        """值格同行最近左侧的标签样文本 (同名字段消歧用)。"""
        if ent is None or (ent.get('row') is None):
            return None, None
        best = None
        for c in cells:
            if c['row'] != ent.get('row') or c['col'] >= ent.get('col', 0):
                continue
            t = (c.get('text') or '').replace('\n', '').strip()
            if t and len(t) <= 12 and t[0] not in _NO_LABEL_PREFIX:
                if best is None or c['col'] > best['col']:
                    best = c
        if best is None:
            return None, None
        return (best.get('text') or '').replace('\n', '').strip(), \
            best.get('addr')

    form_fields = []
    for i, f in enumerate(data.get('fields') or []):
        mode = ('inline' if f.get('inline') else
                'replace' if f.get('replace') else
                'append' if f.get('append') else 'cell')
        doc = {'id': f'F{i + 1:02d}', 'name': f['name'], 'mode': mode}
        label_ent = by_addr.get(f.get('label') or '')
        value_ent = by_addr.get(f.get('value') or '')
        if label_ent is not None:
            doc['label_addr'] = f['label']
            if label_ent.get('text'):
                doc['label_text'] = label_ent['text']
        if value_ent is not None and f.get('value'):
            v = _flat(f['value'])
            doc['value_addr'] = v.pop('addr')
            doc.update(v)
        for k in ('prefix', 'underscore', 'value_seg'):
            if k in f:
                doc[k] = f[k]
        ctx_text, ctx_addr = _context(value_ent or label_ent)
        if ctx_text and ctx_text != f['name']:
            doc['context'] = ctx_text
            if ctx_addr:
                doc['context_addr'] = ctx_addr
        form_fields.append(doc)

    form = {'meta': {'dpi': data.get('dpi'), 'width': data.get('width'),
                     'height': data.get('height')},
            'fields': form_fields}
    titles = [t for t in data.get('texts') or [] if t.get('role') == 'title']
    if titles:
        form['meta']['title'] = max(titles, key=lambda t: t.get('size', 0)) \
            ['text'].strip()

    rows = data.get('table_fields') or []
    if rows:
        headers = []
        for r in rows:
            for h in r['cells']:
                if h not in headers:
                    headers.append(h)
        table_rows = []
        for i, r in enumerate(rows):
            row_doc = {'id': f'R{i + 1:02d}', 'label': r['row_label']}
            if r.get('row'):
                row_doc['label_addr'] = r['row']
            row_doc['cells'] = {h: _flat(a) for h, a in r['cells'].items()}
            table_rows.append(row_doc)
        form['table'] = {'headers': headers, 'rows': table_rows}
    data['form'] = form
    print(f'form 视图: 字段 {len(form_fields)} 个'
          + (f', 表体 {len(rows)} 行' if rows else ''))
