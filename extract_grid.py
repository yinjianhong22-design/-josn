# -*- coding: utf-8 -*-
# 代码已迁至 backend/template_pipeline, 本文件仅为兼容保留。
# server.py / ocr_service.py 等旧入口通过下面的 re-export 照常工作;
# 原模块文档见 backend/template_pipeline/common.py 的 docstring。
"""extract_grid.py 兼容 shim: 显式 re-export backend/template_pipeline 的
公开函数及 server.py / ocr_service.py 依赖的私有名字, 新代码请直接 import
backend.template_pipeline 的对应叶子模块。"""
import importlib as _importlib

_common = _importlib.import_module('backend.template_pipeline.common')
_loader = _importlib.import_module('backend.template_pipeline.input.loader')
_office_convert = _importlib.import_module(
    'backend.template_pipeline.input.office_convert')
_dispatch = _importlib.import_module('backend.template_pipeline.input.dispatch')
_lines_pixel = _importlib.import_module(
    'backend.template_pipeline.layout.lines_pixel')
_lines_vector = _importlib.import_module(
    'backend.template_pipeline.layout.lines_vector')
_lines_merge = _importlib.import_module(
    'backend.template_pipeline.layout.lines_merge')
_cells = _importlib.import_module('backend.template_pipeline.layout.cells')
_content = _importlib.import_module('backend.template_pipeline.layout.content')
_diagnostics = _importlib.import_module(
    'backend.template_pipeline.layout.diagnostics')
_ocr_engine = _importlib.import_module('backend.template_pipeline.text.ocr_engine')
_ocr_cells = _importlib.import_module('backend.template_pipeline.text.ocr_cells')
_ocr_free = _importlib.import_module('backend.template_pipeline.text.ocr_free')
_pdf_text = _importlib.import_module('backend.template_pipeline.text.pdf_text')
_table_data = _importlib.import_module('backend.template_pipeline.text.table_data')
_docx_reader = _importlib.import_module(
    'backend.template_pipeline.office_fb.docx_reader')
_xlsx_reader = _importlib.import_module(
    'backend.template_pipeline.office_fb.xlsx_reader')
_xlsx_anchor = _importlib.import_module(
    'backend.template_pipeline.align.xlsx_anchor')
_roles = _importlib.import_module('backend.template_pipeline.semantic.roles')
_fields = _importlib.import_module('backend.template_pipeline.semantic.fields')
_form_view = _importlib.import_module('backend.template_pipeline.semantic.form_view')
_index = _importlib.import_module('backend.template_pipeline.semantic.index')
_sheet_input = _importlib.import_module(
    'backend.template_pipeline.semantic.sheet_input')
_match = _importlib.import_module('backend.template_pipeline.semantic.match')
_template = _importlib.import_module('backend.template_pipeline.output.template')
_sheet_json = _importlib.import_module('backend.template_pipeline.output.sheet_json')
_rebuild = _importlib.import_module('backend.template_pipeline.output.rebuild')
_frontend = _importlib.import_module('backend.template_pipeline.output.frontend')
_stitch = _importlib.import_module('backend.template_pipeline.pipeline.stitch')
_page = _importlib.import_module('backend.template_pipeline.pipeline.page')
_document = _importlib.import_module('backend.template_pipeline.pipeline.document')
_cli = _importlib.import_module('backend.template_pipeline.pipeline.cli')

# ---- 共享常量/小工具 (common) ----
_import_pymupdf = _common._import_pymupdf
_OCR_TEXT_SCORE = _common._OCR_TEXT_SCORE

# ---- 输入加载 / Office 转换 / 类型判定 ----
load_image = _loader.load_image
office_to_pdf = _office_convert.office_to_pdf
detect_input_type = _dispatch.detect_input_type

# ---- 版面: 线 / 格子 / 内容 / 诊断 ----
binarize = _lines_pixel.binarize
extract_line_masks = _lines_pixel.extract_line_masks
close_gaps = _lines_pixel.close_gaps
find_line_positions = _lines_pixel.find_line_positions
filter_dangling_lines = _lines_pixel.filter_dangling_lines
extract_pdf_rules = _lines_vector.extract_pdf_rules
rules_to_masks = _lines_vector.rules_to_masks
merge_line_sources = _lines_merge.merge_line_sources
compute_intersections = _cells.compute_intersections
find_cells = _cells.find_cells
analyze_layout = _content.analyze_layout
split_text_lines = _content.split_text_lines
draw_overlay = _diagnostics.draw_overlay
dump_lines_json = _diagnostics.dump_lines_json

# ---- 文字: OCR / PDF 文字层 / 标准 JSON ----
_make_ocr_engine = _ocr_engine._make_ocr_engine
ocr_cells = _ocr_cells.ocr_cells
_prepare_crop = _ocr_cells._prepare_crop
_tight_crop = _ocr_cells._tight_crop
_reading_order = _ocr_cells._reading_order
ocr_free_blocks = _ocr_free.ocr_free_blocks
extract_pdf_text = _pdf_text.extract_pdf_text
build_table_data = _table_data.build_table_data

# ---- Office 简化排版回退 ----
docx_to_data = _docx_reader.docx_to_data
xlsx_to_data = _xlsx_reader.xlsx_to_data

# ---- 语义对齐 / 角色 / 字段 / 视图 / 索引 / 数据简表 ----
augment_xlsx_semantics = _xlsx_anchor.augment_xlsx_semantics
assign_roles = _roles.assign_roles
extract_fields = _fields.extract_fields
build_form_view = _form_view.build_form_view
build_index = _index.build_index
photo_to_sheet = _sheet_input.photo_to_sheet
parse_data_sheet = _sheet_input.parse_data_sheet
match_data_fields = _match.match_data_fields

# ---- 输出: 模板 / 简表 JSON / PDF 还原 / 前端 ----
build_template = _template.build_template
build_sheet_json = _sheet_json.build_sheet_json
collect_context = _sheet_json.collect_context
merge_sheet_fields = _sheet_json.merge_sheet_fields
fill_header_values = _sheet_json.fill_header_values
write_sheet_json = _sheet_json.write_sheet_json
json_to_pdf = _rebuild.json_to_pdf
generate_frontend = _frontend.generate_frontend

# ---- 流水线: 拼接 / 单页 / 文档 / 入口 ----
stitch_page_data = _stitch.stitch_page_data
scale_data = _stitch.scale_data
extract_page = _page.extract_page
convert_document = _document.convert_document
main = _cli.main

__all__ = [
    # 公开函数
    'load_image', 'office_to_pdf', 'detect_input_type',
    'binarize', 'extract_line_masks', 'close_gaps', 'find_line_positions',
    'filter_dangling_lines', 'extract_pdf_rules', 'rules_to_masks',
    'merge_line_sources', 'compute_intersections', 'find_cells',
    'analyze_layout', 'split_text_lines', 'draw_overlay', 'dump_lines_json',
    'ocr_cells', 'ocr_free_blocks', 'extract_pdf_text', 'build_table_data',
    'docx_to_data', 'xlsx_to_data',
    'augment_xlsx_semantics', 'assign_roles', 'extract_fields',
    'build_form_view', 'build_index', 'photo_to_sheet', 'parse_data_sheet',
    'match_data_fields',
    'build_template', 'build_sheet_json', 'collect_context',
    'merge_sheet_fields', 'fill_header_values', 'write_sheet_json',
    'json_to_pdf', 'generate_frontend',
    'stitch_page_data', 'scale_data', 'extract_page', 'convert_document',
    'main',
    # server.py / ocr_service.py 依赖的私有名字
    '_import_pymupdf', '_make_ocr_engine', '_prepare_crop', '_tight_crop',
    '_reading_order', '_OCR_TEXT_SCORE',
]

if __name__ == '__main__':
    main()
