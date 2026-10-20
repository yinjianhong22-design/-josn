# -*- coding: utf-8 -*-

# ---------------------------------------------------------------------------
# Excel (.xlsx, openpyxl) -> 标准 JSON (简化排版回退)
# ---------------------------------------------------------------------------

from ..common import _jsonable


def xlsx_to_data(path, dpi=96):
    """Excel 工作簿 -> 标准 JSON。

    逐 sheet 遍历: 值/公式/样式/合并区域分开记录; 多个 sheet 纵向拼接,
    之间留 40px 间距并标注 sheet 名。列宽(字符单位)和行高(pt)换算成像素。
    """
    import openpyxl
    from openpyxl.utils import get_column_letter

    wb_f = openpyxl.load_workbook(path)                  # 公式
    wb_v = openpyxl.load_workbook(path, data_only=True)  # 缓存值
    s = dpi / 72.0
    bwidth = {'hair': 0.5, 'thin': 1.0, 'medium': 2.0, 'thick': 3.0,
              'double': 3.0, 'dashed': 1.0, 'dotted': 0.5}

    cells, texts, rules = [], [], []
    by_addr = {}
    width = 0
    y_off = 0
    row_base = 0  # 多 sheet 纵向拼接时行号全局唯一化, 供角色/字段按网格邻接
    for name in wb_f.sheetnames:
        ws = wb_f[name]
        wsv = wb_v[name]
        if ws.max_row is None:
            continue
        if len(wb_f.sheetnames) > 1:
            texts.append({'x': 0, 'y': y_off + 18 * s, 'size': 14,
                          'font': None, 'color': None, 'bold': True,
                          'role': 'heading', 'text': f'[{name}]',
                          'align': None, 'w': 0})
            y_off += int(30 * s)

        col_x = [0]
        for i in range(1, ws.max_column + 1):
            cd = ws.column_dimensions.get(get_column_letter(i))
            w = cd.width if cd and cd.width else 8.43
            col_x.append(col_x[-1] + int(round(w * 7 + 5)))  # 96dpi 近似
        row_y = [0]
        for i in range(1, ws.max_row + 1):
            rd = ws.row_dimensions.get(i)
            h = rd.height if rd and rd.height else 13.2
            row_y.append(row_y[-1] + int(round(h * s)))

        merged = {}   # 被合并覆盖的位置 -> 锚点 (r, c)
        spans = {}    # 锚点 -> (rowspan, colspan)
        for rg in ws.merged_cells.ranges:
            spans[(rg.min_row, rg.min_col)] = (
                rg.max_row - rg.min_row + 1, rg.max_col - rg.min_col + 1)
            for rr in range(rg.min_row, rg.max_row + 1):
                for cc in range(rg.min_col, rg.max_col + 1):
                    if (rr, cc) != (rg.min_row, rg.min_col):
                        merged[(rr, cc)] = (rg.min_row, rg.min_col)

        seen_rules = {}

        def rule(x0, y0, x1, y1, wpx):
            key = (round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1))
            if key not in seen_rules or seen_rules[key] < wpx:
                seen_rules[key] = wpx

        for r in range(1, ws.max_row + 1):
            for c in range(1, ws.max_column + 1):
                if (r, c) in merged:
                    continue
                cell = ws.cell(row=r, column=c)
                vcell = wsv.cell(row=r, column=c)
                value = cell.value
                formula = None
                if isinstance(value, str) and value.startswith('='):
                    formula = value
                    value = vcell.value  # 显示用缓存计算值
                rowspan, colspan = spans.get((r, c), (1, 1))
                x0 = col_x[c - 1]
                y0 = row_y[r - 1] + y_off
                x1 = col_x[min(c - 1 + colspan, len(col_x) - 1)]
                y1 = row_y[min(r - 1 + rowspan, len(row_y) - 1)] + y_off
                ent = {'row': r - 1 + row_base, 'col': c - 1,
                       'rowspan': rowspan, 'colspan': colspan,
                       'x': x0, 'y': y0, 'w': x1 - x0, 'h': y1 - y0,
                       'borders': None,
                       'addr': f'{name}!{get_column_letter(c)}{r}',
                       'text': '' if value is None else str(value)}
                if formula:
                    ent['formula'] = formula
                vv = vcell.value
                if vv is not None:
                    ent['value'] = _jsonable(vv)
                nf = cell.number_format
                if nf and nf != 'General':
                    ent['number_format'] = nf
                if value is not None and str(value).strip():
                    room = sum(1 for k in range(
                        c + 1, min(c + colspan, ws.max_column) + 1)
                        if wsv.cell(row=r, column=k).value is None)
                    if room:
                        ent['value_room'] = room
                f = cell.font
                if f:
                    if f.sz:
                        ent['size'] = f.sz
                    if f.b:
                        ent['bold'] = True
                    if f.name:
                        ent['font'] = f.name
                    try:
                        if f.color and f.color.rgb \
                                and isinstance(f.color.rgb, str):
                            ent['color'] = '#' + f.color.rgb[-6:]
                    except Exception:
                        pass
                al = cell.alignment
                if al and al.horizontal in ('left', 'right', 'center'):
                    ent['align'] = al.horizontal
                cells.append(ent)
                by_addr[ent['addr']] = ent

        # 边框 -> 矢量线段: 单独遍历所有格(含被合并覆盖的格, 其边上
        # 可能定义了框线), 共享边去重取最粗; 同时记录每格四边有无,
        # 供角色标注 (表体可填判定) 使用
        cell_borders = {}
        for row in ws.iter_rows():
            for cell in row:
                bd = cell.border
                if not bd:
                    continue
                r, c = cell.row, cell.column
                x0 = col_x[c - 1]
                y0 = row_y[r - 1] + y_off
                x1 = col_x[min(c, len(col_x) - 1)]
                y1 = row_y[min(r, len(row_y) - 1)] + y_off
                sides = {}
                for side, seg in (
                        ('top', (x0, y0, x1, y0)),
                        ('bottom', (x0, y1, x1, y1)),
                        ('left', (x0, y0, x0, y1)),
                        ('right', (x1, y0, x1, y1))):
                    b = getattr(bd, side, None)
                    has = bool(b and b.style in bwidth)
                    sides[side] = has
                    if has:
                        rule(*seg, bwidth[b.style])
                cell_borders[(r, c)] = sides
        for (r, c), sides in cell_borders.items():
            ent = by_addr.get(f'{name}!{get_column_letter(c)}{r}')
            if ent is not None:
                ent['borders'] = sides

        rules.extend({'x0': k[0], 'y0': k[1], 'x1': k[2], 'y1': k[3],
                      'width': w} for k, w in seen_rules.items())
        width = max(width, col_x[-1])
        y_off = row_y[-1] + y_off + int(40 * s)
        row_base += ws.max_row

    for ent in cells:
        if ent.get('borders') is None:
            ent.pop('borders', None)
    return {'dpi': dpi, 'width': width,
            'height': y_off - int(40 * s) if y_off else 0,
            'cells': cells, 'texts': texts, 'rules': rules}
