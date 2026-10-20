# -*- coding: utf-8 -*-

# ---------------------------------------------------------------------------
# 交点与格子
# ---------------------------------------------------------------------------


def compute_intersections(h_pos, v_pos, horiz, vert, win=5):
    """计算所有横竖线交点。若交点邻域内横竖两个方向都有线像素则保留。"""
    points = []
    for y in h_pos:
        for x in v_pos:
            y0, y1 = max(0, y - win), min(horiz.shape[0], y + win + 1)
            x0, x1 = max(0, x - win), min(horiz.shape[1], x + win + 1)
            if horiz[y0:y1, x0:x1].any() and vert[y0:y1, x0:x1].any():
                points.append({'x': x, 'y': y})
    return points


def _edge_present(mask, p1, p2, axis, thickness=2, density=0.4):
    """检查 p1->p2 之间是否真的有线段(采样投影密度)。"""
    if axis == 'h':
        y = (p1[1] + p2[1]) // 2
        band = mask[max(0, y - thickness):y + thickness + 1,
                    min(p1[0], p2[0]):max(p1[0], p2[0]) + 1]
    else:
        x = (p1[0] + p2[0]) // 2
        band = mask[min(p1[1], p2[1]):max(p1[1], p2[1]) + 1,
                    max(0, x - thickness):x + thickness + 1]
    if band.size == 0:
        return False
    proj = band.any(axis=0 if axis == 'h' else 1)
    return proj.mean() >= density


def find_cells(h_pos, v_pos, horiz, vert):
    """推出小格子(含合并单元格)。

    把相邻横竖线围成的原子块按"公共边是否缺线"做并查集合并:
    没有分隔线的相邻块属于同一个合并单元格。
    只保留至少含一个">=2 条边"的块的组, 表格外的开放区域因此被丢弃。
    """
    R, C = len(h_pos) - 1, len(v_pos) - 1
    if R <= 0 or C <= 0:
        return []

    def tid(i, j):
        return i * C + j

    parent = list(range(R * C))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    def edges(i, j):
        tl = (v_pos[j], h_pos[i])
        tr = (v_pos[j + 1], h_pos[i])
        bl = (v_pos[j], h_pos[i + 1])
        br = (v_pos[j + 1], h_pos[i + 1])
        return (
            _edge_present(horiz, tl, tr, 'h'),  # top
            _edge_present(horiz, bl, br, 'h'),  # bottom
            _edge_present(vert, tl, bl, 'v'),   # left
            _edge_present(vert, tr, br, 'v'),   # right
        )

    tiles = {}
    for i in range(R):
        for j in range(C):
            e = edges(i, j)
            tiles[tid(i, j)] = e
            if j + 1 < C and not e[3]:      # 右边没分隔线 -> 与右邻同属一格
                union(tid(i, j), tid(i, j + 1))
            if i + 1 < R and not e[1]:      # 下边没分隔线 -> 与下邻同属一格
                union(tid(i, j), tid(i + 1, j))

    groups = {}
    for i in range(R):
        for j in range(C):
            groups.setdefault(find(tid(i, j)), []).append((i, j))

    cells = []
    for members in groups.values():
        if max(sum(tiles[tid(i, j)]) for i, j in members) < 2:
            continue  # 表格外的开放区域
        is_ = [m[0] for m in members]
        js = [m[1] for m in members]
        i0, i1, j0, j1 = min(is_), max(is_), min(js), max(js)
        x, y = v_pos[j0], h_pos[i0]
        cells.append({
            'row': i0, 'col': j0,
            'rowspan': i1 - i0 + 1, 'colspan': j1 - j0 + 1,
            'x': x, 'y': y,
            'w': v_pos[j1 + 1] - x, 'h': h_pos[i1 + 1] - y,
        })
    cells.sort(key=lambda c: (c['row'], c['col']))
    return cells
