# -*- coding: utf-8 -*-

# ---------------------------------------------------------------------------
# 通用表格拓扑: 表头、表体、行标签列和可填值格只发现一次
# ---------------------------------------------------------------------------

from ..common import _NO_LABEL_PREFIX


def _norm_text(s):
    """去掉所有空白后的文本, 用于跨源匹配 (PDF 文字层 vs openpyxl 值)。"""
    return ''.join(str(s).split())


def _group_free_text_lines(texts):
    """把游离文字按基线 y 聚成视觉行。

    返回 [{'y', 'items': [{'idx', 'x', 'y', 'text'}]}], items 按 x 升序,
    idx 为在 texts 列表中的下标 (供稳定几何伪地址寻址)。
    """
    items = sorted(({'idx': i, 'x': t['x'], 'y': t['y'], 'text': t['text']}
                    for i, t in enumerate(texts)),
                   key=lambda it: (it['y'], it['x']))
    lines = []
    for it in items:
        if lines and abs(it['y'] - lines[-1]['y']) <= 6:
            lines[-1]['items'].append(it)
        else:
            lines.append({'y': it['y'], 'items': [it]})
    return lines


def _pick_header_row(cells, header_rows):
    """表头行候选中选定真表头: 取"下一行格子数最多"的候选。

    真表头直接压在最宽的表体行之上; 已填表照片里 抽检人/抽检时间 等
    信息行也可能满足短文本表头规则, 用下一行宽度把它们区分开 (并列取
    最上者)。"""
    if not header_rows:
        return None
    by_row = {}
    for c in cells:
        by_row.setdefault(c['row'], []).append(c)
    return max(sorted(header_rows),
               key=lambda r: len(by_row.get(r + 1, [])))


def _label_col(counts):
    """行标签列: 非空格计数最高者, 但照片/跨行合并场景下值列计数常会
    反超 (10 个实测子格跨两行), 取"计数 >= 60% 最大值"的最左列——
    行标签几乎总在表体最左列。"""
    if not counts:
        return None
    top = max(counts.values())
    for col in sorted(counts):
        if counts[col] >= top * 0.6:
            return col
    return min(counts)


def _table_rows_set(cells, header_row):
    """表体区行集合: 表头行之下、行标签列 (非空格最多的列) 之左无文本的连续行。

    表体区之后的行 (检查结论/审核人等表单尾区) 返回时不包含,
    供角色/字段区分"表格"与"表单尾部"。
    """
    by_row = {}
    for c in cells:
        by_row.setdefault(c['row'], []).append(c)
    counts = {}
    for c in cells:
        if c['row'] > header_row and (c.get('text') or '').strip():
            counts[c['col']] = counts.get(c['col'], 0) + 1
    table_rows = set()
    if counts:
        label_col = _label_col(counts)
        r = header_row + 1
        while r in by_row:
            row_cells = by_row[r]
            if any((c.get('text') or '').strip()
                   for c in row_cells if c['col'] < label_col):
                break
            # 表单尾区标签行 (检查结论/审核人): 行首短文本无符号前缀,
            # 右侧整行无内容, 且右侧只有 1 个格 (尾区是整段合并格;
            # 数据行规定值/实测值/合格率是多个空格, 不得误判) -> 表体到此
            def _tail_label(c):
                t = (c.get('text') or '').replace('\n', '').strip()
                if not (t and len(t) <= 12
                        and t[0] not in _NO_LABEL_PREFIX):
                    return False
                if any((x.get('text') or '').strip()
                       for x in row_cells if x['col'] > c['col']):
                    return False
                right_cells = sum(1 for x in row_cells if x['col'] > c['col'])
                return right_cells < 2
            if any(_tail_label(c) for c in row_cells
                   if c['col'] < max(label_col, 1)):
                break
            table_rows.add(r)
            r += 1
    return table_rows


def discover_table(cells, header_rows=None):
    """统一发现表格拓扑及每行的候选值格。

    返回字典含 header_row/headers/table_rows/label_col/by_grid/rows。
    rows[].columns 保留所有表头列 (target 可能为 None); 已有内容的同行格
    也可作为规定值等列的目标, fields 只挑其中的空格, index 则登记全部。
    """
    if header_rows is None:
        header_rows = {c['row'] for c in cells if c.get('role') == 'header'}
    header_row = _pick_header_row(cells, header_rows)
    result = {'header_row': header_row, 'headers': {}, 'table_rows': set(),
              'label_col': None, 'by_grid': {}, 'rows': []}
    if header_row is None:
        return result

    by_grid = {(c['row'], c['col']): c for c in cells}
    headers = {}
    for c in cells:
        if c['row'] == header_row and (c.get('text') or '').strip():
            headers.setdefault(c['col'],
                               (c.get('text') or '').replace('\n', '').strip())
    table_rows = _table_rows_set(cells, header_row)
    counts = {}
    for c in cells:
        if c['row'] in table_rows and (c.get('text') or '').strip():
            counts[c['col']] = counts.get(c['col'], 0) + 1
    label_col = _label_col(counts) if counts and headers else None
    result.update(headers=headers, table_rows=table_rows,
                  label_col=label_col, by_grid=by_grid)
    if label_col is None:
        return result

    rows = []
    for r in sorted(table_rows):
        key_cell = by_grid.get((r, label_col))
        key = (key_cell.get('text') or '').replace('\n', '').strip() \
            if key_cell else ''
        if not key:
            continue
        columns = {}
        for hc, hname in headers.items():
            if hc == label_col:
                continue
            target = by_grid.get((r, hc))
            if target is None or not (target.get('text') or '').strip():
                target = None
                # 本行空格优先; 下一行仅在同行没有地址时回退, 避免错位到
                # 备用空行或下一已有条目。
                for rr in (r, r + 1):
                    tc = by_grid.get((rr, hc))
                    if tc is None or (tc.get('text') or '').strip() \
                            or not tc.get('addr'):
                        continue
                    if rr == r + 1:
                        lbl = by_grid.get((rr, label_col))
                        if lbl is not None \
                                and (lbl.get('text') or '').strip():
                            continue
                    target = tc
                    break
            columns[hname] = target
        rows.append({'key': key, 'key_cell': key_cell, 'columns': columns})
    result['rows'] = rows
    return result
