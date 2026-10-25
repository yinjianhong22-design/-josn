# -*- coding: utf-8 -*-

# ---------------------------------------------------------------------------
# 单页处理主流程: 线检测 -> 格子 -> 文字 -> 标准 JSON data
# ---------------------------------------------------------------------------

from importlib import import_module as _import_module

from ..common import cv2, os

_loader = _import_module('..input.loader', __package__)
load_image = _loader.load_image
_dispatch = _import_module('..input.dispatch', __package__)
detect_input_type = _dispatch.detect_input_type
_lines_pixel = _import_module('..layout.lines_pixel', __package__)
binarize = _lines_pixel.binarize
extract_line_masks = _lines_pixel.extract_line_masks
close_gaps = _lines_pixel.close_gaps
find_line_positions = _lines_pixel.find_line_positions
filter_dangling_lines = _lines_pixel.filter_dangling_lines
_lines_merge = _import_module('..layout.lines_merge', __package__)
merge_line_sources = _lines_merge.merge_line_sources
_cells = _import_module('..layout.cells', __package__)
compute_intersections = _cells.compute_intersections
find_cells = _cells.find_cells
_content = _import_module('..layout.content', __package__)
analyze_layout = _content.analyze_layout
split_text_lines = _content.split_text_lines
_diagnostics = _import_module('..layout.diagnostics', __package__)
draw_overlay = _diagnostics.draw_overlay
dump_lines_json = _diagnostics.dump_lines_json
_lines_vector = _import_module('..layout.lines_vector', __package__)
extract_pdf_rules = _lines_vector.extract_pdf_rules
_pdf_text = _import_module('..text.pdf_text', __package__)
extract_pdf_text = _pdf_text.extract_pdf_text
_ocr_cells = _import_module('..text.ocr_cells', __package__)
_pick_ocr_backend = _ocr_cells._pick_ocr_backend
_attach_line_pos = _ocr_cells._attach_line_pos
_ocr_free = _import_module('..text.ocr_free', __package__)
ocr_free_blocks = _ocr_free.ocr_free_blocks
_classify_line_roles = _ocr_free._classify_line_roles
_table_data = _import_module('..text.table_data', __package__)
build_table_data = _table_data.build_table_data


def extract_page(input_path, page, args, diagnostics=True):
    """单页处理: 线检测 -> 格子 -> 文字 -> 标准 JSON data。

    diagnostics=True 时输出 overlay.png / lines.json 和统计信息。
    """
    img = load_image(input_path, page=page, dpi=args.dpi)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    bw = binarize(gray)
    horiz, vert = extract_line_masks(bw, h_ratio=args.h_ratio,
                                     v_ratio=args.v_ratio)
    # 交点判定和格子边判定用接合断口后的掩码, 避免断线处的误判
    horiz_c = close_gaps(horiz, 'h')
    vert_c = close_gaps(vert, 'v')
    h_pos = find_line_positions(horiz_c, 'h', min_span=args.h_min_span,
                                span_ratio=getattr(args, 'h_span_ratio',
                                                   0.45))
    v_pos = find_line_positions(vert_c, 'v', min_span=args.v_min_span,
                                span_ratio=getattr(args, 'v_span_ratio',
                                                   0.20))
    # 表格线的两端必然落在对向线上; 两端悬空的(页眉下划线等)滤掉
    h_pos = filter_dangling_lines(h_pos, horiz_c, 'h', v_pos,
                                  other_mask=vert_c)
    v_pos = filter_dangling_lines(v_pos, vert_c, 'v', h_pos,
                                  other_mask=horiz_c)

    # 电子档 PDF: OpenCV 检测(像素)与原始矢量线段(get_drawings)合并——
    # 掩码按位或、线坐标合并聚类, 再统一过悬空过滤。纯 OpenCV 在表格只占
    # 页面一角时容易丢外框线(邻线缺失引发连锁过滤), 矢量线段正好补上
    is_pdf = detect_input_type(input_path) == 'pdf'
    rules = []
    if is_pdf:
        rules = extract_pdf_rules(input_path, page, args.dpi)
        if rules:
            horiz_c, vert_c, h_pos, v_pos = merge_line_sources(
                horiz_c, vert_c, h_pos, v_pos, rules, gray.shape)

    intersections = compute_intersections(h_pos, v_pos, horiz_c, vert_c)
    cells = find_cells(h_pos, v_pos, horiz_c, vert_c)

    # 版面分析: 页面内容边界 + 文字块/图片块; 每格做横向投影行切分,
    # 行切分结果用于约束 OCR 文字还原时的字号和位置
    content, blocks, bounds = analyze_layout(bw, horiz_c, vert_c)
    for c in cells:
        c['text_lines'] = split_text_lines(
            content, (c['x'] + 4, c['y'] + 4, c['w'] - 8, c['h'] - 8))

    texts = {}
    free_texts = []
    if not args.no_ocr:
        need_ocr = True
        if is_pdf and not args.force_ocr:
            # 探测文字层: 有 -> 电子档, 直接提取; 无 -> 扫描件, 回退 OCR
            pdf_texts, free_texts = extract_pdf_text(input_path, page,
                                                     args.dpi, cells)
            if pdf_texts or free_texts:
                texts = pdf_texts or {}
                need_ocr = False
                if diagnostics:
                    roles = {}
                    for t in free_texts:
                        roles[t['role']] = roles.get(t['role'], 0) + 1
                    print(f'文字层探测: 电子档, 直接提取 (格内 {len(texts)}/'
                          f'{len(cells)} 格 + 格外 {len(free_texts)} 行 '
                          f'{roles} + 矢量线段 {len(rules)} 条)')
            else:
                print('文字层探测: 扫描件(无文字层), 回退到 OCR')
        if need_ocr:
            name, backend = _pick_ocr_backend(args)
            print(f'OCR 后端: {name} (逐格请求)')
            ocr_res = backend(img, cells)
            if ocr_res is None:
                print('未安装 rapidocr-onnxruntime, 跳过文字识别'
                      ' (pip install rapidocr-onnxruntime)')
            else:
                texts = ocr_res
                # 投影行切分对位: 约束每行文字还原时的字号和位置
                _attach_line_pos(cells, texts)
                # 表格线框外的文字块也 OCR, 按行高估算字号作为游离文字
                free_texts = ocr_free_blocks(img, blocks, cells, content,
                                             backend, args.dpi)
                if free_texts:
                    tmp = [{'size': t['size'], 'cx': t.pop('cx')}
                           for t in free_texts]
                    _classify_line_roles(tmp, img.shape[1])
                    for t, r in zip(free_texts, tmp):
                        t['role'] = r['role']
                    print(f'格外游离文字 {len(free_texts)} 行 (OCR)')
        if texts and diagnostics:
            print(f'文字提取完成, {len(texts)}/{len(cells)} 个格子有文字')
            for c in cells:
                t = texts.get((c['row'], c['col']))
                if t:
                    print(f'  格[{c["row"]},{c["col"]}]: {t}')

    data = build_table_data(cells, texts, horiz_c, vert_c, args.dpi,
                            (img.shape[1], img.shape[0]), free_texts, rules)
    # 背景候选必须跟随实际提取页，不能由下游默认回第 0 页。
    data['source_page'] = page

    if diagnostics:
        n_txt = sum(1 for b in blocks if b['type'] == 'text')
        print(f'版面分析: 内容边界 {bounds}, 文字块 {n_txt} 个, '
              f'图片块 {len(blocks) - n_txt} 个')
        result = {
            'image_size': {'width': img.shape[1], 'height': img.shape[0]},
            'horizontal_lines': h_pos,
            'vertical_lines': v_pos,
            'intersections': intersections,
            'cells': cells,
            'layout': {'content_bounds': bounds, 'blocks': blocks},
        }
        for c in cells:
            c['text'] = texts.get((c['row'], c['col']), '')
        if getattr(args, 'out', None):  # 服务端调用无 out, 跳过落盘
            overlay_path = os.path.join(args.out, 'overlay.png')
            draw_overlay(img, h_pos, v_pos, cells, overlay_path, blocks)
            print(f'横线 {len(h_pos)} 条, 竖线 {len(v_pos)} 条, '
                  f'交点 {len(intersections)} 个, 格子 {len(cells)} 个')
            dump_lines_json(args.out, result)
            print(f'可视化: {overlay_path}')
    return data
