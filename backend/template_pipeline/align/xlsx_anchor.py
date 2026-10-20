# -*- coding: utf-8 -*-

# ---------------------------------------------------------------------------
# 可回填表单模板: 语义对齐 (addr) + 角色标注 + 字段配对
#
# 回填契约: 按 fields/table_fields 按键名匹配找到目标 addr, 把对应 cell 的
# text 改为新值, 并删除该 cell 的 lines 字段 (lines 是 PDF 文字层的逐行缓存,
# 不删的话旧值会被渲染出来)。text 是唯一回填入口, 几何与边框不许动。
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# 可回填表单模板: 语义对齐 (addr)
# ---------------------------------------------------------------------------

from ..common import _jsonable, _NO_LABEL_PREFIX


def _norm_text(s):
    """去掉所有空白后的文本, 用于跨源匹配 (PDF 文字层 vs openpyxl 值)。"""
    return ''.join(str(s).split())


def _group_free_text_lines(texts):
    """把游离文字按基线 y 聚成视觉行。

    返回 [{'y', 'items': [{'idx', 'x', 'y', 'text'}]}], items 按 x 升序,
    idx 为在 texts 列表中的下标 (供 #T{n} 寻址)。
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


def augment_xlsx_semantics(page_data, wb_f, wb_v, max_candidates=50):
    """把一页探测结果对齐到原生 workbook, 给格子/游离文字赋稳定地址 addr。

    对齐用纯文本锚点投票: 探测格文本(去空白)在原生各 sheet 中反查,
    每个同名位置产生候选偏移 (dr,dc), 得票 Top 做全量校验取匹配最多者;
    阈值 max(3, 0.6×非空探测格), 跨 sheet 取总分最高, 不达标该页跳过
    (JSON 退回纯视觉, 不产生错误地址)。命中后逐格赋
    addr ("Sheet1!B2") 及 value/formula/number_format,
    字体样式 (font_size/font_bold/font_name/font_color/font_align),
    游离文字行能整行匹配原生格的也补 addr。
    字号字体对回填渲染是必需信息: 空值格 PDF 里没有文字层, 只能从
    原生字体取 (PDF 文字层的实际打印字号优先, 见 build_index.ref)。
    """
    from openpyxl.utils import get_column_letter

    sheets = []
    for name in wb_f.sheetnames:
        ws, wsv = wb_f[name], wb_v[name]
        disp, sem, fonts, aligns = {}, {}, {}, {}
        for row in ws.iter_rows():
            for cell in row:
                fnt = cell.font
                if fnt is not None:
                    fe = {}
                    if fnt.sz:
                        fe['size'] = float(fnt.sz)
                    if fnt.b:
                        fe['bold'] = True
                    if fnt.name:
                        fe['name'] = fnt.name
                    try:
                        if fnt.color and fnt.color.rgb \
                                and isinstance(fnt.color.rgb, str):
                            fe['color'] = '#' + fnt.color.rgb[-6:]
                    except Exception:
                        pass
                    if fe:
                        fonts[(cell.row, cell.column)] = fe
                al = cell.alignment
                if al is not None and al.horizontal in (
                        'left', 'right', 'center'):
                    aligns[(cell.row, cell.column)] = al.horizontal
                v = cell.value
                nf = cell.number_format
                if v is None and (not nf or nf == 'General'):
                    continue  # 无值无格式的真空格, 不需要语义记录
                r, c = cell.row, cell.column
                ent = {}
                if v is not None:
                    vv = wsv.cell(row=r, column=c).value
                    if vv is not None:
                        # 无缓存的公式 (如 openpyxl 直接生成未经过 Excel
                        # 重存) 不进 disp: PDF 里是计算结果, 匹配不上
                        disp[(r, c)] = _norm_text(vv)
                        ent['value'] = _jsonable(vv)
                    if isinstance(v, str) and v.startswith('='):
                        ent['formula'] = v
                if nf and nf != 'General':
                    ent['number_format'] = nf
                sem[(r, c)] = ent
        sheets.append((name, disp, sem, ws.max_row, ws.max_column, fonts,
                       aligns))

    anchors = [(_norm_text(c.get('text') or ''), c['row'], c['col'])
               for c in page_data['cells']]
    anchors = [a for a in anchors if len(a[0]) >= 2]
    if not anchors:
        return
    votes = {}
    for t, row, col in anchors:
        for name, disp, _, _, _, _, _ in sheets:
            for (r, c), dt in disp.items():
                if dt == t:
                    key = (name, r - 1 - row, c - 1 - col)
                    votes[key] = votes.get(key, 0) + 1
    if not votes:
        print('语义对齐: 无锚点命中, 该页跳过')
        return

    best = None  # (matches, total, name, dr, dc)
    for (name, dr, dc), _ in sorted(votes.items(), key=lambda kv: -kv[1]
                                    )[:max_candidates]:
        disp = next(d for n, d, _, _, _, _, _ in sheets if n == name)
        matches = total = 0
        for c in page_data['cells']:
            t = _norm_text(c.get('text') or '')
            if len(t) < 2:
                continue
            total += 1
            if disp.get((c['row'] + dr + 1, c['col'] + dc + 1)) == t:
                matches += 1
        if best is None or matches > best[0]:
            best = (matches, total, name, dr, dc)
    matches, total, name, dr, dc = best
    need = max(3, -(-total * 3 // 5))
    if matches < need:
        print(f'语义对齐: 最佳匹配 {matches}/{total} 低于阈值 {need}, 该页跳过')
        return
    print(f'语义对齐: {name} 偏移=({dr},{dc}) 匹配 {matches}/{total}')

    _, _, sem, max_row, max_col, fonts, aligns = next(
        s for s in sheets if s[0] == name)
    for c in page_data['cells']:
        r, cc = c['row'] + dr + 1, c['col'] + dc + 1
        if not (1 <= r <= max_row and 1 <= cc <= max_col):
            continue
        # 使用范围内每格都给 addr (空格是主要回填目标, 不能因为原生为空而缺地址)
        c['addr'] = f"{name}!{get_column_letter(cc)}{r}"
        c.update(sem.get((r, cc), {}))
        fnt = fonts.get((r, cc))
        if fnt:
            if fnt.get('size') is not None:
                c.setdefault('font_size', fnt['size'])
            if fnt.get('bold'):
                c.setdefault('font_bold', True)
            if fnt.get('name'):
                c.setdefault('font_name', fnt['name'])
            if fnt.get('color'):
                c.setdefault('font_color', fnt['color'])
        al = aligns.get((r, cc))
        if al:
            c.setdefault('font_align', al)
        # 格内右侧留白: colspan 范围内除锚点外还有原生空格 -> 值可追加
        if (c.get('text') or '').strip():
            room = sum(1 for k in range(cc + 1, min(cc + c.get('colspan', 1),
                                                   max_col) + 1)
                       if (r, k) not in disp)
            if room:
                c['value_room'] = room

    texts = page_data.get('texts') or []
    for ln in _group_free_text_lines(texts):
        items = ln['items']
        joined = ''.join(it['text'] for it in items)
        # 逐字符建立 (归一化位置 -> 原文位置/所属 item) 映射
        cmap, npos, nmap = [], '', []
        for k, it in enumerate(items):
            cmap.extend([k] * len(it['text']))
        for ci, ch in enumerate(joined):
            n = _norm_text(ch)
            if n:
                npos += n
                nmap.append(ci)
        if len(npos) < 2:
            continue
        # 整行优先; 整行配不上时按"最长前缀逐段消费"匹配
        # (一行跨多个原生格: "监理单位：  编 号：JB12-T-1")
        start = 0
        while start < len(npos):
            hit = None
            for (r, c), dt in disp.items():
                if dt and npos.startswith(dt, start) and \
                        (hit is None or len(dt) > len(hit[2])):
                    hit = (r, c, dt)
            if hit is None:
                break
            r, c, dt = hit
            lo, hi = nmap[start], nmap[start + len(dt) - 1]
            a = f"{name}!{get_column_letter(c)}{r}"
            for k in range(cmap[lo], cmap[hi] + 1):
                texts[items[k]['idx']]['addr'] = a
            start += len(dt)


def _ensure_pseudo_addr(data):
    """没有原生地址 (语义对齐失败/图片 OCR 通路) 时补几何伪地址。

    extract_fields/build_index 的配对链路都依赖 addr, 缺 addr 的格子会被
    整条链路丢弃 (对齐失败一页 -> 模板索引全空)。伪地址按 文档尺寸+网格
    坐标生成: 同表重转稳定 (uuid5 一致), 跨表几何不同不撞车。语义对齐
    成功给的 'Sheet!A1' 真地址不受影响。"""
    salt = f"{data.get('width', 0)}x{data.get('height', 0)}"
    for c in data.get('cells') or []:
        if not c.get('addr'):
            c['addr'] = f"#G{salt}:{c['row']},{c['col']}"
    for i, t in enumerate(data.get('texts') or []):
        if not t.get('addr'):
            t['addr'] = f"#T{salt}:{i}"
