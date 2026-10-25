# -*- coding: utf-8 -*-

# ---------------------------------------------------------------------------
# 数据简表 -> 回填值匹配
# ---------------------------------------------------------------------------

from .column_roles import normalize_column_role


def match_data_fields(sheet, index, fuzzy_min=0.6):
    """数据简表 JSON -> {values: {fieldUuid: 完整格文本}, unmatched}。

    上下文区字段走 header_fields/by_label; 数据区按行标签和统一列角色路由。
    values 不再是待拼接的原始值: inline/append 会结合 index.cells 的占位
    信息物化成完整文本, 同一格多个字段的操作合并后再返回。
    """
    import re

    def norm(s):
        s = str('' if s is None else s).translate(
            {ord('（'): '(', ord('）'): ')'})
        return re.sub(r'[\s△▲Δ]+', '', s)

    def text(v):
        if isinstance(v, float) and v.is_integer():
            return str(int(v))
        return str(v)

    idx_cells = index.get('cells') or {}
    rows = index.get('rows') or []
    by_label = index.get('by_label') or {}
    header_fields = index.get('header_fields') or {}

    def header_cell(k):
        """header_fields 按归一化键查找 (值可能是 {cell: uuid} 或 uuid)。"""
        hf = header_fields.get(k)
        if hf is None:
            hf = next((v for kk, v in header_fields.items()
                       if norm(kk) == k), None)
        if hf is None:
            return None
        return hf.get('cell') if isinstance(hf, dict) else hf

    def binding_for(u, field_name):
        cell = idx_cells.get(u) or {}
        binding = next((b for b in cell.get('bindings') or []
                        if norm(b.get('name')) == norm(field_name)), None)
        if binding is not None:
            return {**cell, **binding}
        return cell

    def segment_end(current, start, cell, binding):
        """当前字段值段的结束位置: 优先原占位, 否则到下一字段前缀。"""
        placeholder = binding.get('placeholder')
        if binding.get('mode') == 'inline' and placeholder:
            pos = current.find(placeholder, start)
            if pos >= start:
                return pos + len(placeholder)
        ends = []
        for other in cell.get('bindings') or []:
            prefix = other.get('prefix')
            if not prefix or prefix == binding.get('prefix'):
                continue
            pos = current.find(prefix, start)
            if pos >= start:
                ends.append(pos)
        return min(ends) if ends else len(current)

    def current_value(u, field_name):
        """按 mode 取当前完整值或当前字段的内联/追加值段。"""
        cell = idx_cells.get(u) or {}
        binding = binding_for(u, field_name)
        current = cell.get('text') or ''
        mode = binding.get('mode') or 'overwrite'
        if mode in ('overwrite', 'replace'):
            return current
        prefix = binding.get('prefix')
        if prefix and prefix in current:
            start = current.index(prefix) + len(prefix)
            end = segment_end(current, start, cell, binding)
            return current[start:end].strip()
        placeholder = binding.get('placeholder')
        if mode == 'inline' and placeholder:
            return placeholder
        return current.strip()

    def already_there(u, v, field_name):
        # 精确比较, 不再用子串: 原值 100 不应吞掉新值 10。
        old = norm(current_value(u, field_name))
        return bool(old) and old == norm(v)

    pending = {}
    unmatched = []
    ambiguous = []

    def queue(u, value, field_name):
        value = text(value)
        if already_there(u, value, field_name):
            return
        pending.setdefault(u, []).append(
            {'value': value, 'binding': binding_for(u, field_name)})

    def apply_operation(current, operation, cell):
        binding = operation['binding']
        value = operation['value']
        mode = binding.get('mode') or 'overwrite'
        if mode in ('overwrite', 'replace'):
            return value
        prefix = binding.get('prefix')
        if not prefix or prefix not in current:
            placeholder = binding.get('placeholder')
            if mode == 'inline' and placeholder and placeholder in current:
                return current.replace(placeholder, value, 1)
            if mode == 'append':
                return current + value
            return value
        start = current.index(prefix) + len(prefix)
        if mode == 'append':
            # 追加在自身标签后, 共享格后续字段原样保留。
            return current[:start] + value + current[start:]
        end = segment_end(current, start, cell, binding)
        segment = current[start:end]
        leading = segment[:len(segment) - len(segment.lstrip())]
        trailing = segment[len(segment.rstrip()):]
        return current[:start] + leading + value + trailing + current[end:]

    # 上下文区 (简表表头行以上): 走 header_fields/by_label 值格。
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
        queue(u, cv, ck)

    # _matched 是单次调用的消费状态, 不能泄漏到下一次回填请求。
    for r in rows:
        r.pop('_matched', None)

    def column_of(cols, role):
        return next((col for hn, col in cols.items()
                     if normalize_column_role(hn) == role), None)

    for f in sheet.get('fields') or []:
        name = f.get('name') or ''
        k = norm(name)
        if not k:
            continue
        measured = f.get('measured') or []
        row = next((r for r in rows
                    if not r.get('_matched') and norm(r.get('key')) == k),
                   None)
        if row is None and fuzzy_min:
            from difflib import SequenceMatcher
            candidates = []
            for r in rows:
                if r.get('_matched'):
                    continue
                rk = norm(r.get('key'))
                ratio = SequenceMatcher(None, k, rk).ratio()
                # 短标签一点点差异就会得到虚高相似度, 提高准入阈值。
                threshold = max(fuzzy_min, 0.85) \
                    if min(len(k), len(rk)) <= 4 else fuzzy_min
                if ratio >= threshold:
                    candidates.append((ratio, r))
            candidates.sort(key=lambda item: item[0], reverse=True)
            if len(candidates) > 1 \
                    and candidates[0][0] - candidates[1][0] <= 0.05:
                ambiguous.append(name)
                unmatched.append(name)
                continue
            if candidates:
                row = candidates[0][1]
        if row is not None:
            row['_matched'] = True
            cols = row.get('columns') or {}
            if f.get('specified') is not None:
                col = column_of(cols, 'specified')
                if col is None:
                    unmatched.append(f'{name} 规定值(模板无对应列)')
                else:
                    queue(col['cell'], f['specified'], name)
            if measured:
                col = column_of(cols, 'measured')
                if col is None:
                    unmatched.append(f'{name} 实测值(模板无对应列)')
                else:
                    slots = col.get('cells') or [col['cell']]
                    if len(slots) == 1 and len(measured) > 1:
                        # 一个实测大格 -> 多值空格拼接。
                        queue(slots[0], ' '.join(text(v) for v in measured),
                              name)
                    else:
                        for i, v in enumerate(measured):
                            if i < len(slots):
                                queue(slots[i], v, name)
                            else:
                                unmatched.append(
                                    f'{name} 第{i + 1}个值(模板该行只有 '
                                    f'{len(slots)} 个值格)')
            if f.get('pass_rate') is not None:
                col = column_of(cols, 'pass_rate')
                if col is None:
                    unmatched.append(f'{name} 合格率(模板无对应列)')
                else:
                    queue(col['cell'], f['pass_rate'], name)
            continue

        # 上下文字段/表尾字段: 值取 measured 首值, 否则 specified。
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
        queue(u, v, name)

    values = {}
    for u, operations in pending.items():
        cell = idx_cells.get(u) or {}
        original = cell.get('text') or ''
        result = original
        for operation in operations:
            result = apply_operation(result, operation, cell)
        if result != original:
            values[u] = result
    return {'values': values, 'unmatched': unmatched, 'ambiguous': ambiguous}
