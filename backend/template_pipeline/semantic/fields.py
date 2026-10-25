# -*- coding: utf-8 -*-

# ---------------------------------------------------------------------------
# 字段配对 (fields: 标签->值/内联; table_fields: 表体行)
# ---------------------------------------------------------------------------

from importlib import import_module as _import_module

from ..common import _NO_LABEL_PREFIX

_xlsx_anchor = _import_module('..align.xlsx_anchor', __package__)
from .table_topology import (
    _group_free_text_lines,
    _label_col,
    _norm_text,
    _pick_header_row,
    _table_rows_set,
    discover_table,
)


# 值格占位文本: 年月日样式 (允许数字/点/横线), 如 "年  月  日"
_PLACEHOLDER_RE = None  # 延迟编译, 见 _is_placeholder


def _is_placeholder(text):
    """text 是否是年月日类占位文本 (视为可覆盖写的空值格)。"""
    import re
    global _PLACEHOLDER_RE
    if _PLACEHOLDER_RE is None:
        _PLACEHOLDER_RE = re.compile(r'^(?=.*[年月日])[\s0-9年月日./-]{2,15}$')
    return bool(_PLACEHOLDER_RE.match((text or '').strip()))


_COLON_RE = None  # 延迟编译, 见 extract_fields


def extract_fields(data):
    """从角色标注中产出可回填字段: fields (标签->值/内联) + table_fields。

    - 格内联冒号: 整格文本形如 "编 号：xxx" -> inline 字段, prefix 为冒号前;
    - 标签->值对: label 角色格优先配右邻 (下划线占位格也算), 下邻次之;
    - 游离文字行: 按基线聚行后同样匹配冒号模式, 用原生 addr 或几何 #T
      伪地址寻址, value_seg 为值起始的下标位置;
    - 表体行: 表头行之下, 行标签列 = 非空格最多的列; 每个行标签下,
      只收集"标签行该列为空"的表头列, 优先取下一行 (专用填写行) 的地址。
    """
    import re
    global _COLON_RE
    if _COLON_RE is None:
        _COLON_RE = re.compile(r'^(.*?[:：])(.*)$', re.S)

    cells = data['cells']
    by_grid = {(c['row'], c['col']): c for c in cells}

    def text_of(c):
        return (c.get('text') or '').replace('\n', '').strip()

    fields, table_fields = [], []

    # 1) 格内联冒号
    for c in cells:
        t = (c.get('text') or '').strip()
        m = _COLON_RE.match(t)
        if m and len(t) <= 20 and c.get('addr'):
            name = re.sub(r'\s+', '', re.sub(r'\s*[:：]\s*$', '',
                                             m.group(1)))
            if name:
                fields.append({'name': name, 'label': c['addr'],
                               'inline': True, 'prefix': m.group(1)})

    # 2) 标签->值对
    for c in cells:
        if c.get('role') != 'label' or not c.get('addr'):
            continue
        name = re.sub(r'\s+', '', re.sub(r'\s*[:：]\s*$', '', text_of(c)))
        if not name:
            continue
        target = by_grid.get((c['row'], c['col'] + c['colspan']))
        replace = False
        if target is not None and text_of(target) \
                and '___' not in (target.get('text') or ''):
            if _is_placeholder(target.get('text')):
                replace = True  # "年 月 日" 占位 -> 覆盖写
            else:
                # 行尾合并值格自带短样例文本 (如 工程部位="土方路基") ->
                # 按覆盖写配对; 右侧还有格子的短文本更像下一个标签
                nxt = by_grid.get((target['row'],
                                   target['col'] + target['colspan']))
                if nxt is None and len(text_of(target)) <= 15:
                    replace = True
                else:
                    target = None
        if target is None:
            below = by_grid.get((c['row'] + c['rowspan'], c['col']))
            if below is not None and not text_of(below):
                target = below
        if target is None or not target.get('addr'):
            continue
        target['fillable'] = True
        target.setdefault('role', 'value')
        entry = {'name': name, 'label': c['addr'], 'value': target['addr']}
        if replace:
            entry['replace'] = True  # 回填时整格覆盖占位文本
        if '___' in (target.get('text') or ''):
            entry['underscore'] = True  # 回填时把下划线段替换为值
        fields.append(entry)

    # 2.5) 格内右侧留白型: 标签与值探测成同一格, 但原生 colspan 内锚点
    #      右侧还有空格 (value_room, 对齐阶段记录) -> 值追加写在同一格
    #      标签之后 (如 "抽检时间" 后的大片空格)
    topology = discover_table(cells)
    table_rows = topology['table_rows']
    claimed = {a for f in fields for a in (f.get('label'), f.get('value'))}
    for c in cells:
        if c.get('role') in ('header', 'title', 'value') \
                or c['row'] in table_rows \
                or not c.get('addr') or c['addr'] in claimed:
            continue
        t = text_of(c)
        if not t or len(t) > 15 or t[0] in _NO_LABEL_PREFIX:
            continue
        # value_room 缺省时, 行尾合并格 (右侧无格) 同样视为值格
        row_end = by_grid.get((c['row'], c['col'] + c['colspan'])) is None
        if not c.get('value_room') and not row_end:
            continue
        c['fillable'] = True
        # 左邻是标签样文本 -> 本格是它的值格, 已有文字视为占位, 整格替换
        # (占位文字要求短, 避免把 "基本要求" 配到后面的长 checklist 格)
        left = by_grid.get((c['row'], c['col'] - 1))
        lt = text_of(left) if left is not None else ''
        if lt and len(t) <= 15 and len(lt) <= 12 \
                and lt[0] not in _NO_LABEL_PREFIX \
                and left.get('role') in (None, 'data') \
                and left.get('addr') and left['addr'] not in claimed:
            fields.append({'name': re.sub(r'\s+', '', lt),
                           'label': left['addr'], 'value': c['addr'],
                           'replace': True})
            claimed.add(left['addr'])
            continue
        fields.append({'name': re.sub(r'\s+', '', t),
                       'label': c['addr'], 'value': c['addr'],
                       'inline': True, 'prefix': t, 'append': True})

    # 3) 游离文字行: 一行可含多个"标签：值"字段 (按冒号扫描, 如
    #    "监理单位：    编  号：JB12-4.2.2-")
    texts = data.get('texts') or []
    label_chars = re.compile(r'([\w\u4e00-\u9fff（）()·、\s]{1,14}?)\s*[:：]')
    for ln in _group_free_text_lines(texts):
        items = ln['items']
        joined = ''.join(it['text'] for it in items)
        if len(_norm_text(joined)) > 40:  # 长段落不是字段行
            continue
        matches = list(label_chars.finditer(joined))
        if not matches:
            continue

        def seg_at(pos):
            acc = 0
            for k, it in enumerate(items):
                acc += len(it['text'])
                if pos < acc:
                    return k
            return len(items) - 1

        for k, m in enumerate(matches):
            name = re.sub(r'\s+', '', m.group(1))
            if not name or len(name) > 12 or name[0] in _NO_LABEL_PREFIX \
                    or '□' in name:
                continue
            value_start = m.end()
            value_end = (matches[k + 1].start() if k + 1 < len(matches)
                         else len(joined))
            ls = seg_at(m.start())
            entry = {'name': name,
                     'label': texts[items[ls]['idx']].get('addr')
                              or f"#T{items[ls]['idx']}",
                     'inline': True, 'prefix': m.group(0)}
            value_text = joined[value_start:value_end].strip()
            if value_text:
                vs = seg_at(value_start)
                entry['value'] = (texts[items[vs]['idx']].get('addr')
                                  or f"#T{items[vs]['idx']}")
                entry['value_seg'] = vs
            fields.append(entry)

    # 4) 表体行字段 (拓扑和值格候选与 build_index 共用同一次发现)
    for row in topology['rows']:
        c = row['key_cell']
        entry = {'row_label': row['key'], 'cells': {}}
        if c.get('addr'):
            entry['row'] = c['addr']
        for hname, target in row['columns'].items():
            if target is None or text_of(target):
                continue  # 已有内容 (如规定值) 不是 table_fields 的填写列
            entry['cells'][hname] = target['addr']
        if entry['cells']:
            table_fields.append(entry)

    data['fields'] = fields
    data['table_fields'] = table_fields
    print(f'字段配对: fields {len(fields)} 个, '
          f'table_fields {len(table_fields)} 行')
