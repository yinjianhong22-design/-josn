# -*- coding: utf-8 -*-

# ---------------------------------------------------------------------------
# 二值化 + 横竖线提取 (像素通路)
# ---------------------------------------------------------------------------

from ..common import cv2, np


def binarize(gray):
    """自适应阈值二值化, 返回线条/文字为白色(255)的图。"""
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    bw = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 15, 10)
    return bw


def extract_line_masks(bw, h_ratio=0.1, v_ratio=0.03):
    """形态学开运算分离横线和竖线。

    核长度按图像尺寸比例取: 横线核较长(10%), 因为表格横线通常贯穿表宽;
    竖线核较短(3%), 因为表格里存在只跨一两行的短竖线(表头分栏等),
    核太长会把它们当噪声滤掉。文字、噪点、短笔画会被滤掉。
    返回 (横线图, 竖线图)。
    """
    h, w = bw.shape
    h_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT, (max(10, int(w * h_ratio)), 1))
    v_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT, (1, max(10, int(h * v_ratio))))
    horiz = cv2.morphologyEx(bw, cv2.MORPH_OPEN, h_kernel)
    vert = cv2.morphologyEx(bw, cv2.MORPH_OPEN, v_kernel)
    return horiz, vert


def close_gaps(mask, axis):
    """沿线条方向闭运算, 接合同方向的断口 (如扫描件缺墨、虚线)。"""
    h, w = mask.shape
    if axis == 'h':
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(10, w // 50), 1))
    else:
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(10, h // 50)))
    return cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)


def find_line_positions(mask, axis, min_len=20, gap=3, min_span=0.25,
                        span_ratio=None):
    """从单方向线图中找出每条线的精确坐标。

    按像素投影找条带, 条带内按投影强度加权取中心作为线的坐标。
    min_span (占整幅图比例) 过滤掉文字行这类"只覆盖一小段长度"的假线;
    投影阈值取最大值的 4%: 表里存在只跨一两行的短线(表头分栏),
    阈值按最大长度比例取太高会把它们整批滤掉; 下限 min_len 防噪点。
    span_ratio 给定时启用自适应过滤: 阈值 = min(整图比例, 最长线比例
    × span_ratio)。手机拍照件里表格常只占画面一角, 整图比例会把真线
    全灭, 而相对最长线的比例仍按表格自身尺度放行; 满页表格场景
    longest≈图长, 取 min 后等价于原整图比例, 行为不回退。
    返回升序坐标列表。
    """
    proj = mask.sum(axis=1 if axis == 'h' else 0) // 255  # 每行/列上的线像素数

    # 投影阈值取最大值的 4%
    thresh = max(min_len, proj.max() * 0.04) if proj.max() > 0 else min_len
    on = proj >= thresh
    n = mask.shape[1] if axis == 'h' else mask.shape[0]
    bands = []
    i = 0
    while i < len(on):
        if on[i]:
            j = i
            while j + 1 < len(on) and (on[j + 1] or
                                 (j + gap < len(on) and on[j + 1:j + gap + 1].any())):
                j += 1
            # 覆盖度: 条带内沿线条延伸方向有多大比例的列/行有线像素
            if axis == 'h':
                span = mask[i:j + 1, :].any(axis=0).mean()
            else:
                span = mask[:, i:j + 1].any(axis=1).mean()
            band = proj[i:j + 1].astype(np.float64)
            center = np.average(np.arange(i, j + 1), weights=band)
            bands.append((int(round(center)), span))
            i = j + 1
        else:
            i += 1
    if not bands:
        return []
    if span_ratio:
        longest = max(s for _, s in bands)
        min_span = min(min_span, longest * span_ratio)
    return [c for c, s in bands if s >= min_span]


def _line_extent(mask, p, axis, bridge=12, wobble=2):
    """单线坐标 p 上的实际像素延伸范围 [lo, hi], 取不到返回 None。

    只在 p 附近 ±wobble 的行/列内取像素, 逐列/行做"间距 ≤ bridge 的
    断口拼接"后选延伸最长的一段。比 ±2 邻域 any 更稳: 不混入相邻
    行/列的手写笔画, 线心偏 1-2px 也不会漏掉细线 (find_line_positions
    的重心会被线旁杂散墨点拉偏)。
    """
    if axis == 'h':
        strip = mask[max(0, p - wobble):p + wobble + 1, :] > 0
        segs = _merge_runs(strip.any(axis=0), bridge)
    else:
        strip = mask[:, max(0, p - wobble):p + wobble + 1] > 0
        segs = _merge_runs(strip.any(axis=1), bridge)
    if not segs:
        return None
    return max(segs, key=lambda s: s[1] - s[0])


def _merge_runs(flags, bridge):
    """把布尔序列中为真的位置按"间距 ≤ bridge 可拼接"聚成 (lo, hi) 段。"""
    idx = np.where(flags)[0]
    if idx.size == 0:
        return []
    cuts = np.where(np.diff(idx) > bridge)[0]
    starts = np.r_[0, cuts + 1]
    ends = np.r_[cuts, idx.size - 1]
    return [(int(idx[s]), int(idx[e])) for s, e in zip(starts, ends)]


def filter_dangling_lines(pos, mask, axis, other_pos, other_mask=None,
                          tol=25, run_exempt=0.5, min_cross=2):
    """滤掉两端都不"挂靠"在另一方向线上的假线(如表格外的人名下划线)。

    取该线的实际像素延伸范围, 检查起止点 tol 像素内是否有对向线。
    真正的表格线(哪怕只跨几列)两端都会落在竖线/横线上; 下划线这类
    独立线条两端悬空, 被滤掉。满足以下任一条件即保留:
    1. 长线豁免: 自身延伸 ≥ 本方向最长线的 run_exempt 倍 (基准排除
       贴整幅图边缘的伪线)。拍照件边框发淡断裂时, 长线两端够不到锚
       是掩码缺损而非假线; 横跨大半个表格的线不可能是游离下划线。
    2. 双锚定: 两端 tol 内都有对向线, 且 other_mask 给定时该对向线的
       像素延伸必须覆盖到本线坐标附近 (±tol)——手写长竖笔位置可能
       正好压线但延伸够不到交叉点, 不能当锚; None 时退化为纯位置校验。
    3. 交叉计数: 延伸范围内穿过 ≥ min_cross 条对向线且自身延伸
       ≥ 图长 15%——救回断裂成段的边框 (段短锚不住, 但穿线数装不了假)。
    """
    n = mask.shape[1] if axis == 'h' else mask.shape[0]
    own = []
    for p in pos:
        ext = _line_extent(mask, p, axis)
        if ext is not None:
            own.append((p, ext))
    # 豁免基准取"非贴边最长线": 贴图像边缘的整幅伪线 (截图黑边) 会把
    # 基准拉满导致次长线被误杀, 不参与基准计算
    longest = max((e[1] - e[0] for _, e in own if e[1] - e[0] < n * 0.97),
                  default=0)

    def end_anchored(p, end):
        for o in other_pos:
            if abs(o - end) > tol:
                continue
            if other_mask is None:
                return True
            ext = _line_extent(other_mask, o, 'v' if axis == 'h' else 'h')
            if ext is not None and ext[0] - tol <= p <= ext[1] + tol:
                return True
        return False

    kept = []
    for p, (lo, hi) in own:
        run = hi - lo
        crossings = sum(1 for o in other_pos if lo <= o <= hi)
        if (run >= longest * run_exempt or
                (end_anchored(p, lo) and end_anchored(p, hi)) or
                (crossings >= min_cross and run >= n * 0.15)):
            kept.append(p)
    dropped = len(pos) - len(kept)
    if dropped:
        print(f'滤掉 {dropped} 条两端悬空的假线')
    return kept
