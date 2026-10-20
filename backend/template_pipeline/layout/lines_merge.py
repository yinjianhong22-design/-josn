# -*- coding: utf-8 -*-

# ---------------------------------------------------------------------------
# 像素线与矢量线合并
# ---------------------------------------------------------------------------

from ..common import cv2
from .lines_pixel import filter_dangling_lines
from .lines_vector import rules_to_masks, _merge_positions


def merge_line_sources(horiz_c, vert_c, h_pos, v_pos, rules, shape):
    """把矢量线段并入像素级线掩码与线坐标 (OpenCV 检测值与
    get_drawings 聚类值合并)——掩码按位或、线坐标合并聚类,
    再统一过悬空过滤。纯 OpenCV 在表格只占页面一角时容易丢
    外框线(邻线缺失引发连锁过滤), 矢量线段正好补上。
    返回 (horiz_c, vert_c, h_pos, v_pos)。
    """
    horiz_r, vert_r, h_r, v_r = rules_to_masks(rules, shape)
    horiz_c = cv2.bitwise_or(horiz_c, horiz_r)
    vert_c = cv2.bitwise_or(vert_c, vert_r)
    h_pos = _merge_positions(h_pos, h_r)
    v_pos = _merge_positions(v_pos, v_r)
    h_pos = filter_dangling_lines(h_pos, horiz_c, 'h', v_pos,
                                  other_mask=vert_c)
    v_pos = filter_dangling_lines(v_pos, vert_c, 'v', h_pos,
                                  other_mask=horiz_c)
    return horiz_c, vert_c, h_pos, v_pos

