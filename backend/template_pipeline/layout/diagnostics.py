# -*- coding: utf-8 -*-

# ---------------------------------------------------------------------------
# 可视化 + 线诊断落盘
# ---------------------------------------------------------------------------

from ..common import cv2, json, os


def draw_overlay(img, h_pos, v_pos, cells, out_path, blocks=None):
    vis = img.copy()
    for b in blocks or []:
        color = (200, 0, 200) if b['type'] == 'text' else (0, 165, 255)
        cv2.rectangle(vis, (b['x'], b['y']),
                      (b['x'] + b['w'], b['y'] + b['h']), color, 2)
    for y in h_pos:
        cv2.line(vis, (0, y), (vis.shape[1] - 1, y), (0, 255, 0), 1)
    for x in v_pos:
        cv2.line(vis, (x, 0), (x, vis.shape[0] - 1), (255, 0, 0), 1)
    for c in cells:
        cv2.rectangle(vis, (c['x'], c['y']),
                      (c['x'] + c['w'], c['y'] + c['h']), (0, 0, 255), 1)
        cv2.putText(vis, f"{c['row']},{c['col']}",
                    (c['x'] + 3, c['y'] + 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1)
    cv2.imwrite(out_path, vis)


def dump_lines_json(out_dir, result):
    """把横线/竖线/交点/格子诊断结果落盘成 lines.json (打印内容不变)。

    result 为 extract_page 组好的诊断 dict; 落盘路径固定为
    out_dir/lines.json。
    """
    json_path = os.path.join(out_dir, 'lines.json')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f'结果已写入 {json_path}')

