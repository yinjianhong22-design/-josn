# -*- coding: utf-8 -*-

# ---------------------------------------------------------------------------
# 数据简表导出 (简化.json, 与 parse_data_sheet 互为逆操作)
# ---------------------------------------------------------------------------

from ..common import json, os


# 上下文字段名里的嵌套分组分隔符: "分部工程·工程名称" 折叠成
# {"分部工程": {"工程名称": ...}}, 支持多级 (a·b·c)
_CTX_GROUP_SEP = '·'


def _norm_name(s):
    """字段名归一: 全角括号转半角 + 去空白 (与 match_data_fields 的
    行标签归一保持一致, 括号/空白差异不影响匹配)。"""
    s = str(s or '').translate({ord('（'): '(', ord('）'): ')'})
    return ''.join(s.split())


def _ctx_value(name, text):
    """整行共享格 "监理单位：…  编 号：JB12-x" -> 冒号后的值段。"""
    import re
    m = re.match(r'^(.*?)[:：]\s*(\S.*)$', text or '')
    if m and _norm_name(name) in _norm_name(m.group(1)):
        return m.group(2).strip()
    return text


def collect_context(index):
    """从 index 的表头区 (header_fields + by_label) 收集上下文字段 -> dict。

    header_fields 全部视为上下文; by_label 只收 "label -> 值格" 配对条目
    (数据行标签如 △压实度(%) 没有值格, 自然排除, 不进上下文)。值取
    index.cells 里值格的当前文本, 共享格只取冒号后的值段; 值格无文本的
    字段给 None。字段名含 _CTX_GROUP_SEP 时折叠成嵌套对象
    (如 "分部工程·工程名称" -> {"分部工程": {"工程名称": ...}})。
    """
    cells = index.get('cells') or {}
    out = {}

    def cell_text(u):
        return ((cells.get(u) or {}).get('text') or '').strip()

    def put(name, value):
        parts = [p for p in str(name).split(_CTX_GROUP_SEP) if p]
        if not parts:
            return
        node = out
        for p in parts[:-1]:
            nxt = node.get(p)
            if not isinstance(nxt, dict):
                nxt = {}
                node[p] = nxt
            node = nxt
        node[parts[-1]] = value

    for name, ent in (index.get('header_fields') or {}).items():
        u = ent.get('cell') if isinstance(ent, dict) else ent
        t = cell_text(u)
        put(name, _ctx_value(name, t) if t else None)
    for name, ents in (index.get('by_label') or {}).items():
        if name in out:
            continue  # header_fields 已覆盖的键不重复收
        u = next((e.get('value') for e in ents if e.get('value')), None)
        if not u:
            continue  # 数据行标签等无值格条目不是上下文
        t = cell_text(u)
        if t:
            put(name, _ctx_value(name, t))
    return out


def fill_header_values(header, sheet):
    """把简表 context 合并进模板表头上下文, 返回新 dict。

    冲突策略: 简表已有值优先 (含嵌套对象逐键合并, 简表键覆盖模板键),
    模板表头只补缺键; 合并后仍无值的字段给 None (由 collect_context
    保证模板侧每个字段都有键)。
    """
    out = {}
    for k, v in (header or {}).items():
        out[k] = dict(v) if isinstance(v, dict) else v
    for k, v in (sheet.get('context') or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = {**out[k], **v}
        else:
            out[k] = v
    return out


def merge_sheet_fields(sheet):
    """收编 sheet['fields']: key/norm/specified/measured/pass_rate 原样保留。

    缺 key/norm 的条目用 name 推导 (norm 为 _norm_name(key) 归一匹配键);
    measured 缺省给 [], specified/pass_rate 缺省给 None, 输出结构与
    简化.json 的 fields 元素一致。
    """
    fields = []
    for f in sheet.get('fields') or []:
        key = f.get('key') if f.get('key') is not None else f.get('name')
        fields.append({
            'key': key,
            'norm': f.get('norm') if f.get('norm') is not None
                    else _norm_name(key),
            'specified': f.get('specified'),
            'measured': f.get('measured') or [],
            'pass_rate': f.get('pass_rate'),
        })
    return fields


def build_sheet_json(sheet, index):
    """{title, context, fields} 简表 + 模板 index -> 简化.json 结构 dict。

    与 parse_data_sheet 互为逆操作: parse_data_sheet 把 数据简表.xlsx
    解析成一次性 {title, context, fields} (用完即弃); build_sheet_json
    反向把简表数据与模板表头上下文 (collect_context) 合并成可存档的完整
    JSON —— 上下文字段取模板当前值、简表值优先、模板只补缺键、缺值给
    null; fields 按 merge_sheet_fields 原样收编。输出键序: 上下文字段
    在前, fields 在最后, 与 简化.json 样例一致。
    """
    out = fill_header_values(collect_context(index), sheet)
    out['fields'] = merge_sheet_fields(sheet)
    return out


def write_sheet_json(sheet, index, out_path):
    """build_sheet_json 落盘 (utf-8, indent=1, 与 简化.json 样例同格式)。"""
    data = build_sheet_json(sheet, index)
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    return out_path

