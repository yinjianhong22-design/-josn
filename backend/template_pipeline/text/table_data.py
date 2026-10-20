# -*- coding: utf-8 -*-

# ---------------------------------------------------------------------------
# 标准 JSON (data.json) —— 表格还原的唯一数据源
# ---------------------------------------------------------------------------

from importlib import import_module as _import_module

_cells = _import_module('..layout.cells', __package__)
_edge_present = _cells._edge_present


def build_table_data(cells, texts, horiz_c, vert_c, dpi, img_size,
                     free_texts=None, rules=None):
    """把识别结果组织成一份"可还原整页 PDF"的标准 JSON 数据结构。

    坐标为整页渲染图像素坐标(含页边距), dpi 字段记录了像素->PDF point
    的换算依据 (point = px * 72 / dpi)。包含:
      cells  每个格子的几何、rowspan/colspan、四周边框有无、文字
      texts  表格线框外的游离文字(页眉/标题/页码等), 带基线坐标和字号(pt)
      rules  电子档 PDF 的原始矢量线段(精确坐标+线宽); 有 rules 时渲染层
             直接画 rules, 不再按格子边逐边描绘(避免重复/偏移)
    0 个格子(拍照件/无线表格)也返回合法结构: 只有游离文字,
    下游照常出背景/模板, 不再返回 None 让调用方 500。
    """
    def edges(c):
        tl = (c['x'], c['y'])
        tr = (c['x'] + c['w'], c['y'])
        bl = (c['x'], c['y'] + c['h'])
        br = (c['x'] + c['w'], c['y'] + c['h'])
        return {
            'top': bool(_edge_present(horiz_c, tl, tr, 'h')),
            'bottom': bool(_edge_present(horiz_c, bl, br, 'h')),
            'left': bool(_edge_present(vert_c, tl, bl, 'v')),
            'right': bool(_edge_present(vert_c, tr, br, 'v')),
        }

    w_img, h_img = img_size
    cell_list = []
    for c in cells:
        d = {
            'row': c['row'], 'col': c['col'],
            'rowspan': c['rowspan'], 'colspan': c['colspan'],
            'x': c['x'], 'y': c['y'],
            'w': c['w'], 'h': c['h'],
            'borders': edges(c),
            'text': texts.get((c['row'], c['col']), ''),
        }
        if c.get('lines'):
            # 行级信息: PDF 文字层为 基线+字号+字体+颜色, OCR 为 行高+文本
            d['lines'] = c['lines']
        if c.get('font'):
            d['font'] = c['font']  # 主导字体名, 供还原时映射本机字体
        cell_list.append(d)

    return {
        'dpi': dpi,
        'width': w_img,
        'height': h_img,
        'cells': cell_list,
        'texts': free_texts or [],
        'rules': rules or [],
    }
