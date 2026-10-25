# -*- coding: utf-8 -*-

"""纯坐标/字号规则的文字行角色分类，不依赖 OCR。"""


def _classify_line_roles(lines, page_w):
    """字号聚类 + 坐标规则, 给每行文字定语义角色 (title/heading/body)。

    以字号中位数为正文基准: 明显大于正文且接近页面水平居中 -> 标题;
    明显大于正文但不居中 -> 小标题; 其余为正文。
    """
    if not lines:
        return
    sizes = sorted(l['size'] for l in lines)
    body = sizes[len(sizes) // 2]
    for l in lines:
        centered = abs(l['cx'] - page_w / 2) < page_w * 0.12
        if l['size'] >= body * 1.3:
            l['role'] = 'title' if centered else 'heading'
        elif l['size'] >= body * 1.12:
            l['role'] = 'heading'
        else:
            l['role'] = 'body'
