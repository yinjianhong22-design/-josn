# -*- coding: utf-8 -*-

# ---------------------------------------------------------------------------
# Word (.docx, python-docx) -> 标准 JSON (简化排版回退)
# ---------------------------------------------------------------------------


def _docx_effective_style(run, para):
    """样式继承链: run 直接格式 -> 段落样式(含 base_style 链) -> 文档默认。

    返回 (字号pt, 加粗, 颜色#rrggbb 或 None, 字体名)。
    """
    def walk(getter):
        v = getter(run.font) if run is not None else None
        if v is not None:
            return v
        st = para.style
        while st is not None:
            v = getter(st.font)
            if v is not None:
                return v
            st = st.base_style
        return None

    size = walk(lambda f: f.size)
    bold = walk(lambda f: f.bold)
    name = walk(lambda f: f.name)
    try:
        color = walk(lambda f: f.color.rgb if f.color and f.color.rgb
                     else None)
    except Exception:
        color = None
    return (size.pt if size is not None else 10.5, bool(bold),
            f'#{color}' if color else None, name)


def _docx_para_role(para):
    """标题层级: 样式名/大纲级别直接判定 (标题1/Heading 1 -> title 等)。"""
    name = (para.style.name or '') if para.style else ''
    low = name.lower()
    if low in ('title', '标题'):
        return 'title'
    for lv, role in ((1, 'title'), (2, 'heading'), (3, 'heading')):
        if f'heading {lv}' in low or f'标题 {lv}' in name \
                or f'标题{lv}' in name:
            return role
    return 'body'


def docx_to_data(path, dpi=96):
    """Word 文档 -> 标准 JSON。

    Word 是流式格式没有固定坐标, 这里做简化排版: 按节设置取页面/页边距,
    段落按行高顺序下排, 表格按列宽/行高换算成格子。dpi 取 96 (屏幕像素),
    JSON 坐标即像素。
    """
    from docx import Document
    from docx.oxml.ns import qn
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    doc = Document(path)
    sec = doc.sections[0]
    emu = 12700  # EMU per pt
    page_w = (sec.page_width or 7560310) / emu    # 默认 A4
    page_h = (sec.page_height or 10692000) / emu
    ml = (sec.left_margin or 914400) / emu
    mr = (sec.right_margin or 914400) / emu
    mt = (sec.top_margin or 914400) / emu
    mb = (sec.bottom_margin or 914400) / emu
    s = dpi / 72.0
    content_w = page_w - ml - mr

    texts, cells, rules = [], [], []
    y = mt

    def add_paragraph(p):
        nonlocal y
        text = p.text.strip()
        pf = p.paragraph_format
        runs = [r for r in p.runs if r.text.strip()]
        dom = max(runs, key=lambda r: len(r.text)) if runs else None
        size, bold, color, fname = _docx_effective_style(dom, p)
        spacing = pf.line_spacing
        if spacing is None:
            line_h = size * 1.35
        elif isinstance(spacing, float):
            line_h = size * spacing
        else:
            line_h = spacing / emu
        before = (pf.space_before or 0) and pf.space_before / emu
        after = (pf.space_after or 0) and pf.space_after / emu
        y += before
        if text:
            from docx.enum.text import WD_ALIGN_PARAGRAPH
            align = {WD_ALIGN_PARAGRAPH.CENTER: 'center',
                     WD_ALIGN_PARAGRAPH.RIGHT: 'right'}.get(p.alignment)
            indent = pf.left_indent / emu if pf.left_indent else 0
            texts.append({
                'x': (ml + indent) * s, 'y': (y + size * 0.85) * s,
                'size': size, 'font': fname, 'color': color,
                'bold': bold, 'role': _docx_para_role(p),
                'text': text, 'align': align, 'w': content_w * s,
            })
        y += line_h + after

    def add_table(tbl):
        nonlocal y
        # 列宽: tblGrid 的 dxa (1/20pt); 缺失则均分版心
        grid = tbl._tbl.tblGrid.findall(qn('w:gridCol'))
        widths = [(int(gc.get(qn('w:w'))) / 20 if gc.get(qn('w:w'))
                   else content_w / max(1, len(grid))) for gc in grid]
        ncol = max(1, len(widths))
        xs = [ml]
        for w in widths:
            xs.append(xs[-1] + w)

        # 行高: trHeight (dxa), 缺失按内容行数估算
        rows_y = []
        yy = y
        for row in tbl.rows:
            h = None
            trPr = row._tr.find(qn('w:trPr'))
            if trPr is not None:
                trH = trPr.find(qn('w:trHeight'))
                if trH is not None and trH.get(qn('w:val')):
                    h = int(trH.get(qn('w:val'))) / 20
            if h is None:
                n = max((c.text.count('\n') + 1 for c in row.cells),
                        default=1)
                h = max(16.0, n * 10.5 * 1.35)
            rows_y.append((yy, h))
            yy += h

        # 表格边框: tblBorders (sz 单位 1/8pt); 无定义时 Table Grid 默认全框
        borders = {}
        tblPr = tbl._tbl.tblPr
        tb = tblPr.find(qn('w:tblBorders')) if tblPr is not None else None
        if tb is not None:
            for side in ('top', 'left', 'bottom', 'right',
                         'insideH', 'insideV'):
                el = tb.find(qn(f'w:{side}'))
                if el is None or el.get(qn('w:val')) in ('none', 'nil'):
                    borders[side] = None
                else:
                    borders[side] = int(el.get(qn('w:sz'), '4')) / 8
        else:
            grid_style = tbl.style and 'grid' in (tbl.style.name or '').lower()
            borders = {k: (0.5 if grid_style else None)
                       for k in ('top', 'left', 'bottom', 'right',
                                 'insideH', 'insideV')}

        def rule(x0, y0, x1, y1, wpt):
            if wpt:
                rules.append({'x0': x0 * s, 'y0': y0 * s,
                              'x1': x1 * s, 'y1': y1 * s,
                              'width': wpt * s})

        # 逐行逐格: 直接读 tr.tc_lst (row.cells 会把 vMerge 纵向合并
        # 解析成根格内容, 掩盖延续格); gridSpan 横并, vMerge 纵并
        from docx.table import _Cell
        tbl_start = len(cells)
        vopen = {}  # col -> cells 列表里跨行来源格的索引
        for r, row in enumerate(tbl.rows):
            c = 0
            for tc in row._tr.tc_lst:
                span = tc.grid_span or 1
                vm = tc.vMerge
                if c >= ncol:
                    break
                if vm == 'continue':
                    if c in vopen:
                        cells[vopen[c]]['rowspan'] += 1
                    c += span
                    continue
                cell = _Cell(tc, tbl)
                text = cell.text.strip()
                ent = {'row': r, 'col': c, 'rowspan': 1, 'colspan': span,
                       'x': xs[c] * s, 'y': rows_y[r][0] * s,
                       'w': (xs[min(c + span, ncol)] - xs[c]) * s,
                       'h': 0,  # 行高可能因纵并后延, 最后统一算
                       '_r0': r,
                       'borders': None, 'text': text}
                para0 = next((p for p in cell.paragraphs if p.text.strip()),
                             None)
                if para0 is not None:
                    runs = [rn for rn in para0.runs if rn.text.strip()]
                    dom = (max(runs, key=lambda rn: len(rn.text))
                           if runs else None)
                    size, bold, color, fname = _docx_effective_style(
                        dom, para0)
                    ent['size'] = size
                    ent['font'] = fname
                    if bold:
                        ent['bold'] = True
                vopen.pop(c, None)
                if vm == 'restart':
                    vopen[c] = len(cells)
                cells.append(ent)
                c += span

        # 纵并结束后算每格真实高度
        for ent in cells:
            if ent.get('_r0') is not None and ent['h'] == 0:
                r0 = ent['_r0']
                ent['h'] = sum(rows_y[i][1]
                               for i in range(r0, min(r0 + ent['rowspan'],
                                                      len(rows_y)))) * s
                del ent['_r0']

        # 边框 -> 矢量线段 (合并区域内部的分隔线不画)
        tbl_cells = cells[tbl_start:]
        hskip = set()  # (行边界 r, 列 c): 纵向合并跨过
        vskip = set()  # (行 r, 列边界 c): 横向合并跨过
        for ent in tbl_cells:
            for rr in range(ent['row'] + 1, ent['row'] + ent['rowspan']):
                for cc in range(ent['col'], ent['col'] + ent['colspan']):
                    hskip.add((rr, cc))
            for rr in range(ent['row'], ent['row'] + ent['rowspan']):
                for cc in range(ent['col'] + 1, ent['col'] + ent['colspan']):
                    vskip.add((rr, cc))
        nrow = len(rows_y)
        for r in range(nrow + 1):
            yb = rows_y[r][0] if r < nrow else yy
            wpt = borders['top'] if r == 0 else (
                borders['bottom'] if r == nrow else borders['insideH'])
            if not wpt:
                continue
            c = 0
            while c < ncol:
                if (r, c) in hskip:
                    c += 1
                    continue
                c0 = c
                while c + 1 < ncol and (r, c + 1) not in hskip:
                    c += 1
                rule(xs[c0], yb, xs[c + 1], yb, wpt)
                c += 1
        for c in range(ncol + 1):
            wpt = borders['left'] if c == 0 else (
                borders['right'] if c == ncol else borders['insideV'])
            if not wpt:
                continue
            r = 0
            while r < nrow:
                if (r, c) in vskip:
                    r += 1
                    continue
                r0 = r
                while r + 1 < nrow and (r + 1, c) not in vskip:
                    r += 1
                rule(xs[c], rows_y[r0][0], xs[c],
                     rows_y[r][0] + rows_y[r][1], wpt)
                r += 1
        y = yy + 12  # 表格后留一点间距

    for child in doc.element.body.iterchildren():
        if child.tag == qn('w:p'):
            add_paragraph(Paragraph(child, doc))
        elif child.tag == qn('w:tbl'):
            add_table(Table(child, doc))

    # 清理辅助字段
    for ent in cells:
        ent.pop('_r0', None)
        if ent['borders'] is None:
            del ent['borders']

    height = max(page_h, y + mb)
    return {'dpi': dpi, 'width': int(page_w * s), 'height': int(height * s),
            'cells': cells, 'texts': texts, 'rules': rules}
