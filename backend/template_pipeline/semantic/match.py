# -*- coding: utf-8 -*-

# ---------------------------------------------------------------------------
# 数据简表 -> 回填值匹配
# ---------------------------------------------------------------------------


def match_data_fields(sheet, index, fuzzy_min=0.6):
    """数据简表 JSON -> {values: {fieldUuid: 值}, unmatched: [字段名, ...]}。

    上下文区字段 (施工单位等) 走 header_fields/by_label; 数据区字段按
    行标签匹配 rows, specified/measured[i]/pass_rate 分别进规定值列/
    实测值列子格第 i 个/合格率列 (模板拆格子, 数据侧只按序给值)。
    行标签先精确匹配 (归一化后相等); 剩余走相似度兜底 (difflib,
    ≥ fuzzy_min 取最高者, 一行只消费一次)——照片 OCR 对行标签的识别
    噪声 (丢符号/多点少点) 是普遍现象, 精确匹配全挂时相似键仍能对上。
    """
    import re

    def norm(s):
        s = str(s or '').translate({ord('（'): '(', ord('）'): ')'})
        return re.sub(r'[\s△▲Δ]+', '', s)

    def text(v):
        if isinstance(v, float) and v.is_integer():
            return str(int(v))
        return str(v)

    def header_cell(k):
        """header_fields 按归一化键查找 (值可能是 {cell: uuid} 或 uuid)。"""
        hf = header_fields.get(k)
        if hf is None:  # 模板侧键未归一, 扫一遍
            hf = next((v for kk, v in header_fields.items()
                       if norm(kk) == k), None)
        if hf is None:
            return None
        return hf.get('cell') if isinstance(hf, dict) else hf

    idx_cells = index.get('cells') or {}

    def already_there(u, v):
        """模板该格已有这个值 (印刷体/编号/规定值等) -> 无需映射覆盖。"""
        t = norm((idx_cells.get(u) or {}).get('text') or '')
        return bool(t) and norm(v) in t

    values = {}
    unmatched = []
    rows = index.get('rows') or []
    by_label = index.get('by_label') or {}
    header_fields = index.get('header_fields') or {}

    # 上下文区 (简表表头行以上): 走 header_fields/by_label 值格
    for ck, cv in (sheet.get('context') or {}).items():
        k = norm(ck)
        if not k or cv is None:
            continue
        u = header_cell(k) or next(
            (e.get('value') for e in by_label.get(k, []) if e.get('value')),
            None)
        if u is None:
            unmatched.append(ck)
            continue
        v = text(cv)
        if not already_there(u, v):
            values[u] = v

    for f in sheet.get('fields') or []:
        name = f.get('name') or ''
        k = norm(name)
        if not k:
            continue
        measured = f.get('measured') or []
        row = next((r for r in rows if norm(r.get('key')) == k), None)
        if row is None and fuzzy_min:
            # 相似度兜底: OCR 噪声下的通用匹配, 一行只被消费一次
            from difflib import SequenceMatcher
            best = None
            for r in rows:
                if r.get('_matched'):
                    continue
                ratio = SequenceMatcher(None, k,
                                        norm(r.get('key'))).ratio()
                if ratio >= fuzzy_min and (best is None
                                           or ratio > best[0]):
                    best = (ratio, r)
            if best:
                row = best[1]
        if row is not None:
            row['_matched'] = True
            cols = row.get('columns') or {}
            if f.get('specified') is not None:
                sv = text(f['specified'])
                for hn, col in cols.items():
                    if '规定值' in norm(hn):
                        if not already_there(col['cell'], sv):
                            values[col['cell']] = sv
                        break
            slots = []
            for hn, col in cols.items():
                if '实测' in norm(hn):
                    slots = col.get('cells') or [col['cell']]
                    break
            if len(slots) == 1 and len(measured) > 1:
                # 模板该行实测区是一整个大格 (无子格) -> 值空格拼接写入
                joined = ' '.join(text(v) for v in measured)
                if not already_there(slots[0], joined):
                    values[slots[0]] = joined
            else:
                for i, v in enumerate(measured):
                    if i < len(slots):
                        tv = text(v)
                        if not already_there(slots[i], tv):
                            values[slots[i]] = tv
                    else:
                        unmatched.append(f'{name} 第{i + 1}个值'
                                         f'(模板该行只有 {len(slots)} 个值格)')
            if f.get('pass_rate') is not None:
                pv = text(f['pass_rate'])
                for hn, col in cols.items():
                    if '合格率' in norm(hn):
                        if not already_there(col['cell'], pv):
                            values[col['cell']] = pv
                        break
            continue
        # 上下文字段/表尾字段: 值取 measured 首值, 否则 specified
        u = header_cell(k) or next(
            (e.get('value') for e in by_label.get(k, []) if e.get('value')),
            None)
        if u is None:
            unmatched.append(name)
            continue
        v = measured[0] if measured else f.get('specified')
        if v is None:
            unmatched.append(f'{name} (简表无值)')
            continue
        tv = text(v)
        if not already_there(u, tv):
            values[u] = tv
    return {'values': values, 'unmatched': unmatched}
