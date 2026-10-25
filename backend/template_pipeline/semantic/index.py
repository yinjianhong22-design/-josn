# -*- coding: utf-8 -*-

# ---------------------------------------------------------------------------
# 可填充索引 index: by_label + header_fields + rows (+ cells + report)
#
# 表头行 (role=header, 含"规定值"类列名的行) 为分界线, 构建时自动识别:
#   表头行以上 -> 上下文区: label 格 -> 同排右侧值格, 进 header_fields,
#                 目录 context 纯字典查找填充 (空值格=覆盖写, 带占位文本=
#                 inline 替换), 与数据区互不干扰;
#   表头行以下 -> 数据区: 按行分组还原 "字段 -> 规定值/实测值/合格率" 结构,
#                 进 rows, 数据简表按 行标签+列名 填充;
#   全表       -> by_label: 所有带 label 的字段 (兜底和通用查找)。
# uuid 由 addr 确定性生成 (uuid5), 同表重建一致; cells 表携带每格几何/
# 占位文本/mode, 回填渲染只查 cells[uuid]。占位覆盖/无值格/缺列等边界
# 构建期全部进 report, 不等到运行期。
#
# 填充语义 (cells[uuid] 的 mode):
#   overwrite  text 为空, 直接写入 value
#   replace    整格替换 (占位文字视为示例值, 如 工程部位 的 "土方路基")
#   append     值追加在占位文本之后 (标签与值同格, 如 抽检时间)
#   inline     替换占位文本片段 (同行冒号内联, 如 编号: JB12-...)
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# 可填充索引 index: by_label + header_fields + rows (+ cells + report)
# ---------------------------------------------------------------------------

from importlib import import_module as _import_module

_xlsx_anchor = _import_module('..align.xlsx_anchor', __package__)
from .table_topology import (
    _group_free_text_lines,
    _label_col,
    _pick_header_row,
    _table_rows_set,
    discover_table,
)


_INDEX_NS = None  # uuid5 namespace, 延迟生成


def build_index(data):
    """按上述契约生成 data['index']。依赖 extract_fields/assign_roles
    的配对结果 (fields) 与网格几何, 在 build_form_view 之后调用。"""
    import re
    import uuid
    global _INDEX_NS
    if _INDEX_NS is None:
        _INDEX_NS = uuid.UUID('7d4f2a90-3b1c-5e6a-9f08-2d5b8c4a7e91')

    def norm(s):
        return re.sub(r'\s+', '', str(s or ''))

    cells = data['cells']
    topology = discover_table(cells)
    by_grid = topology['by_grid']
    header_row = topology['header_row']

    # 同 addr 的游离文字按视觉行拼接 (一个原生格常被拆成多个 seg,
    # 如 A3 = "监理单位：..." + "JB12-4.2.2-"), 拼接后占位提取才完整
    merged_text = {}
    for grp in _group_free_text_lines(data.get('texts') or []):
        by_a = {}
        for it in grp['items']:
            t = data['texts'][it['idx']]
            if t.get('addr'):
                by_a.setdefault(t['addr'], []).append(it)
        for a, items in by_a.items():
            merged_text[a] = ''.join(
                data['texts'][it['idx']]['text']
                for it in sorted(items, key=lambda i: i['x']))

    idx_cells, report = {}, []
    _noaddr = {}  # id(cell) -> uuid (无 addr 的格, 每次运行不同)

    def ref(c):
        """cell -> uuid, 并登记进 cells 表 (几何/文本/占位)。"""
        a = c.get('addr')
        if a:
            u = str(uuid.uuid5(_INDEX_NS, a))
        else:
            u = _noaddr.setdefault(id(c), str(uuid.uuid4()))
        if u not in idx_cells:
            e = {'addr': a, 'x': round(c['x'], 1), 'y': round(c['y'], 1),
                 'w': round(c.get('w') or 0, 1),
                 'h': round(c.get('h') or 0, 1)}
            t = merged_text.get(a, (c.get('text') or '').strip())
            if t:
                e['text'] = t
            # 字号/字体/颜色: PDF 文字层 (lines, 实际打印样式) > 顶层原生
            # 属性 (docx/xlsx 简化排版通路) > openpyxl 原生字体 (空值格
            # 唯一来源) > 无; 对齐只有原生侧可得。
            # 渲染层按此复原字体 (build_template -> style.fontFamily 等)
            ln0 = (c.get('lines') or [{}])[0] or {}
            size = c.get('size') or ln0.get('size') or c.get('font_size')
            bold = (c.get('bold') or ln0.get('bold')
                    or c.get('font_bold'))
            family = (c.get('font') or ln0.get('font')
                      or c.get('font_name'))
            color = (c.get('color') or ln0.get('color')
                     or c.get('font_color'))
            align = c.get('align') or c.get('font_align')
            if size:
                e['size'] = round(float(size), 2)
            if bold:
                e['bold'] = True
            if family:
                e['font'] = str(family)
            if color:
                e['color'] = str(color)
            if align:
                e['align'] = align
            idx_cells[u] = e
        return u

    def mode_of(u, f):
        """登记字段填充方式; 共享格逐字段保留 prefix/placeholder。"""
        if f.get('inline'):
            mode = 'inline'
        elif f.get('replace'):
            mode = 'replace'
        elif f.get('append'):
            mode = 'append'
        else:
            mode = 'overwrite'
        cell = idx_cells[u]
        text = cell.get('text') or ''
        prefix = f.get('prefix')
        if mode == 'append' and prefix:
            placeholder = prefix
        elif mode == 'inline' and text:
            placeholder = None
            if prefix and prefix in text:
                start = text.index(prefix) + len(prefix)
                ends = []
                # 同一原生格可含多个字段, 当前字段的值段到下一字段前缀止。
                for other in data.get('fields') or []:
                    op = other.get('prefix')
                    other_addr = other.get('value') or other.get('label')
                    if other is f or not op or op == prefix \
                            or other_addr != cell.get('addr'):
                        continue
                    pos = text.find(op, start)
                    if pos >= 0:
                        ends.append(pos)
                end = min(ends) if ends else len(text)
                placeholder = text[start:end].strip() or None
            if placeholder is None and not prefix:
                placeholder = re.split(r'[:：]', text)[-1].strip() or text
        elif text:
            placeholder = text
        else:
            placeholder = None

        # 顶层字段保持旧索引结构; bindings 让共享格的每个字段仍使用自己的
        # 填充语义, 不会被最后登记的字段覆盖。
        cell['mode'] = mode
        if prefix:
            cell['prefix'] = prefix
        else:
            cell.pop('prefix', None)
        if placeholder:
            cell['placeholder'] = placeholder
        else:
            cell.pop('placeholder', None)
        binding = {'name': f['name'], 'mode': mode}
        if prefix:
            binding['prefix'] = prefix
        if placeholder:
            binding['placeholder'] = placeholder
        cell.setdefault('bindings', []).append(binding)
        if placeholder:
            report.append({
                'level': 'info', 'type': 'placeholder_fill',
                'field': f['name'], 'cell': u, 'addr': cell['addr'],
                'placeholder': placeholder, 'mode': mode,
                'message': f'"{f["name"]}" 值格含占位文本 '
                           f'"{placeholder}", 按 {mode} 填充'})
        return mode

    header_fields, by_label, rows = {}, {}, []

    def add_label(c, value_u):
        t = norm((c.get('text') or '').replace('\n', ''))
        if not t:
            return
        ent = by_label.setdefault(t, [])
        u = ref(c)
        if any(e['cell'] == u for e in ent):
            return
        e = {'cell': u}
        if value_u:
            e['value'] = value_u
        ent.append(e)

    if header_row is None:
        report.append({'level': 'warn', 'type': 'no_header',
                       'message': '未识别到表头行, header_fields/rows 为空, '
                                  '仅 by_label 可用'})
    # label 可能是格子也可能是游离文字 (监理单位/编号), 游离文字无
    # 行号, 上下文区用 y 坐标与表头行比较定区
    all_ents = list(cells) + list(data.get('texts') or [])

    def find_ent(addr):
        return next((c for c in all_ents if c.get('addr') == addr), None)

    if header_row is not None:
        hdr_y = min(c['y'] for c in cells if c['row'] == header_row)
        # ---- 上下文区: 表头行以上的 fields (label -> 同排右侧值格) ----
        for f in data.get('fields') or []:
            label_ent = find_ent(f.get('label'))
            if label_ent is None or label_ent.get('y', 0) >= hdr_y:
                continue  # 表尾/表内字段 (检查结论/审核日期等) 不进 header_fields
            if not f.get('value') and not (f.get('inline')
                                           and f.get('prefix')):
                report.append({'level': 'warn', 'type': 'no_value_cell',
                               'field': f['name'], 'addr': f.get('label'),
                               'message': f'"{f["name"]}" 未配到值格, '
                                          f'仅进 by_label'})
                add_label(label_ent, None)
                continue
            value_ent = find_ent(f.get('value'))
            if value_ent is None:
                value_ent = label_ent   # 标签与值同格 (内联前缀型), 追加填充
                f = {**f, 'inline': False, 'append': True}
            u = ref(value_ent)
            key = norm(f['name'])

            def _reg_label():
                # 以字段名登记 by_label (label 全文可能含多字段, 如 A3 行)
                ent = by_label.setdefault(key, [])
                if not any(x['cell'] == ref(label_ent) for x in ent):
                    x = {'cell': ref(label_ent)}
                    if u != ref(label_ent):
                        x['value'] = u
                    ent.append(x)

            if key in header_fields:
                report.append({'level': 'warn', 'type': 'dup_field',
                               'field': key,
                               'message': f'上下文区重名字段 "{key}", 后者 '
                                          f'仅进 by_label'})
                _reg_label()
                continue
            header_fields[key] = {'cell': u}
            header_fields[key]['mode'] = mode_of(u, f)
            _reg_label()

        # ---- 数据区: 表体行 -> 字段 -> 各列 (规定值/实测值/合格率) ----
        headers = topology['headers']
        header_cols = {hname: hc for hc, hname in headers.items()}
        for table_row in topology['rows']:
            kc = table_row['key_cell']
            kt = table_row['key']
            row_doc = {'key': kt, 'key_cell': ref(kc)}
            add_label(kc, None)
            for hname, target in table_row['columns'].items():
                if target is None or not target.get('addr'):
                    report.append({'level': 'warn',
                                   'type': 'missing_col',
                                   'row': kt, 'col': hname,
                                   'message': f'行 "{kt}" 缺列 '
                                              f'"{hname}" 的值格'})
                    continue
                col = {'cell': ref(target)}
                if (target.get('text') or '').strip():
                    col['text'] = target['text']
                if '实测' in norm(hname):
                    # 实测值类列: 登记列区内全部子格 (按 行,x 序),
                    # 数据简表 measured 列表按序拆格填入 (模板拆格子)
                    hc = header_cols[hname]
                    hcell = by_grid.get((header_row, hc))
                    r = kc['row']
                    rs = kc.get('rowspan', 1)
                    if hcell is not None and rs:
                        hx0 = hcell['x']
                        hx1 = hcell['x'] + hcell['w']
                        subs = [c for c in cells
                                if c is not kc and c.get('addr')
                                and hx0 - 1 <= c['x'] + c['w'] / 2
                                < hx1 + 1
                                and r <= c['row'] < r + rs]
                        subs.sort(key=lambda c: (c['row'], c['x']))
                        col['cells'] = [ref(c) for c in subs]
                        report.append({
                            'level': 'info', 'type': 'value_cells',
                            'row': kt, 'col': hname,
                            'count': len(col['cells']),
                            'message': f'行 "{kt}" 列 "{hname}" 有 '
                                       f'{len(col["cells"])} 个值格, '
                                       f'measured 按序拆格填入'})
                row_doc.setdefault('columns', {})[hname] = col
            if row_doc.get('columns'):
                rows.append(row_doc)
            else:
                report.append({'level': 'info',
                               'type': 'no_fillable_col',
                               'row': kt,
                               'message': f'行 "{kt}" 没有可填列 '
                                          f'(如检查要求说明行), 不进 rows'})

    # ---- by_label 兜底: 表尾 label 角色格 (检查结论/审核人 等) ----
    registered = {e['cell'] for lst in by_label.values() for e in lst}
    for c in cells:
        if c.get('role') != 'label' or not c.get('addr'):
            continue
        u = ref(c)
        if u in registered:
            continue
        right = by_grid.get((c['row'], c['col'] + c.get('colspan', 1)))
        value_u = None
        if right is not None and right.get('addr'):
            value_u = ref(right)
            if (right.get('text') or '').strip():
                idx_cells[value_u]['mode'] = 'replace'
                idx_cells[value_u]['placeholder'] = \
                    (right.get('text') or '').strip()
                report.append({
                    'level': 'info', 'type': 'placeholder_fill',
                    'field': norm(c.get('text')), 'cell': value_u,
                    'addr': right['addr'],
                    'placeholder': (right.get('text') or '').strip(),
                    'mode': 'replace',
                    'message': f'"{norm(c.get("text"))}" 值格含占位文本, '
                               f'按 replace 填充'})
        add_label(c, value_u)

    # fields 里尚未登记的标签 (审核日期/监理单位/编号 等非 label 角色,
    # label 可能是格子也可能是游离文字)
    for f in data.get('fields') or []:
        label_ent = find_ent(f.get('label'))
        if label_ent is None:
            continue
        u = ref(label_ent)
        if u in {e['cell'] for lst in by_label.values() for e in lst}:
            continue
        value_u = None
        value_ent = find_ent(f.get('value'))
        if value_ent is not None and f.get('value') != f.get('label'):
            value_u = ref(value_ent)
        elif value_ent is not None:
            value_u = u  # label/value 同格 (inline/append)
        # 以字段名 (而非 label 格全文) 登记, 游离文字 label 的全文
        # 可能含多个字段 (如 A3 一整行)
        key = norm(f['name'])
        ent = by_label.setdefault(key, [])
        if not any(x['cell'] == u for x in ent):
            x = {'cell': u}
            if value_u:
                x['value'] = value_u
            ent.append(x)

    # 重名数据行显式报告; 匹配阶段仍会按输入顺序逐行各消费一次。
    duplicate_rows = {}
    for i, row in enumerate(rows):
        duplicate_rows.setdefault(norm(row.get('key')), []).append(i)
    for key, positions in duplicate_rows.items():
        if key and len(positions) > 1:
            report.append({
                'level': 'warn', 'type': 'duplicate_row', 'row': key,
                'count': len(positions), 'rows': positions,
                'message': f'数据区重名行 "{key}" 共 {len(positions)} 行, '
                           f'匹配时按顺序逐行消费'})

    # xlsx 对齐失败或纯图片通路使用几何伪地址, 索引必须保留降级痕迹。
    pseudo_cells = sum(1 for c in cells
                       if str(c.get('addr') or '').startswith('#G'))
    pseudo_texts = sum(1 for t in data.get('texts') or []
                       if str(t.get('addr') or '').startswith('#T'))
    if pseudo_cells or pseudo_texts:
        report.append({
            'level': 'warn', 'type': 'alignment_degraded',
            'cells': pseudo_cells, 'texts': pseudo_texts,
            'message': f'语义对齐降级为几何伪地址: 格子 {pseudo_cells} 个, '
                       f'游离文字 {pseudo_texts} 个'})

    data['index'] = {
        'meta': {'title': (data.get('form') or {}).get('meta', {})
                 .get('title'),
                 'dpi': data.get('dpi'), 'width': data.get('width'),
                 'height': data.get('height'),
                 'header_row': header_row,
                 'norm': '去除所有空白字符'},
        'header_fields': header_fields,
        'rows': rows,
        'by_label': by_label,
        'cells': idx_cells,
        'report': report,
    }
    print(f"index: header_fields {len(header_fields)} 个, rows {len(rows)}"
          f" 行, by_label {len(by_label)} 项, 报告 {len(report)} 条")
