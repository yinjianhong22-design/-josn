# -*- coding: utf-8 -*-

# ---------------------------------------------------------------------------
# docx/xlsx 完整转换流水线 (main 与 server 共用)
# ---------------------------------------------------------------------------

from importlib import import_module as _import_module

from ..common import cv2, np, os, _import_pymupdf
from .page import extract_page
from .stitch import stitch_page_data, scale_data


def _render_stitched_background(pdf_path, data, out_path, scale=1.0):
    """按 data 的拼接偏移/缩放合成源 PDF 背景，确保与字段同几何。"""
    info = data.get('_stitch') or {}
    pages = info.get('pages') or []
    offsets = info.get('offsets') or []
    if len(pages) < 2 or len(pages) != len(offsets):
        raise RuntimeError('拼接背景缺少完整的页码/偏移信息')
    fitz = _import_pymupdf()
    dpi = data.get('dpi') or 300
    doc = fitz.open(pdf_path)
    try:
        width = max(1, int(round(info['width'])))
        height = max(1, int(round(info['height'])))
        canvas = np.full((height, width, 3), 255, dtype=np.uint8)
        for page_no, dx in zip(pages, offsets):
            if not 0 <= page_no < len(doc):
                raise RuntimeError(f'拼接背景页码越界: {page_no}')
            pix = doc[page_no].get_pixmap(dpi=dpi, alpha=False)
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                pix.height, pix.width, pix.n)
            if pix.n == 4:
                img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
            elif pix.n == 3:
                img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
            elif pix.n == 1:
                img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
            x = int(round(dx))
            src_x0 = max(0, -x)
            dst_x0 = max(0, x)
            copy_w = min(pix.width - src_x0, width - dst_x0)
            copy_h = min(pix.height, height)
            if copy_w > 0 and copy_h > 0:
                canvas[:copy_h, dst_x0:dst_x0 + copy_w] = \
                    img[:copy_h, src_x0:src_x0 + copy_w]
    finally:
        doc.close()
    final_size = (max(1, int(round(data['width']))),
                  max(1, int(round(data['height']))))
    if canvas.shape[1] != final_size[0] or canvas.shape[0] != final_size[1]:
        canvas = cv2.resize(canvas, final_size,
                            interpolation=cv2.INTER_AREA if scale < 1
                            else cv2.INTER_CUBIC)
    ok, encoded = cv2.imencode('.png', canvas)
    if not ok:
        raise RuntimeError('拼接背景 PNG 编码失败')
    encoded.tofile(out_path)

_office_convert = _import_module('..input.office_convert', __package__)
office_to_pdf = _office_convert.office_to_pdf
_docx_reader = _import_module('..office_fb.docx_reader', __package__)
docx_to_data = _docx_reader.docx_to_data
_xlsx_reader = _import_module('..office_fb.xlsx_reader', __package__)
xlsx_to_data = _xlsx_reader.xlsx_to_data
_xlsx_anchor = _import_module('..align.xlsx_anchor', __package__)
augment_xlsx_semantics = _xlsx_anchor.augment_xlsx_semantics
_roles = _import_module('..semantic.roles', __package__)
assign_roles = _roles.assign_roles
_fields = _import_module('..semantic.fields', __package__)
extract_fields = _fields.extract_fields
_form_view = _import_module('..semantic.form_view', __package__)
build_form_view = _form_view.build_form_view
_index = _import_module('..semantic.index', __package__)
build_index = _index.build_index
_frontend = _import_module('..output.frontend', __package__)
generate_frontend = _frontend.generate_frontend


def convert_document(input_path, out_dir, args):
    """docx/xlsx 完整转换流水线 (main 与 server 共用)。

    优先用本机 WPS/Office 排版引擎转 PDF, 走电子档通路 (版式原样);
    失败回退 python-docx/openpyxl 简化排版 (背景由 build_template 自渲染,
    见 office_fb.render)。依次产出: form.json/data.json/data.js/index.html
    (generate_frontend)。返回 (data, office_pdf): office_pdf 是排版引擎
    转出的原样 PDF (无排版引擎时为 None)。
    """
    ext = os.path.splitext(input_path)[1].lower()
    conv = office_to_pdf(input_path, out_dir)
    if conv:
        fitz = _import_pymupdf()
        doc = fitz.open(conv)
        n_pages = len(doc)
        doc.close()
        if ext == '.xlsx':
            # 默认第 0 页时保留宽表拼接通路；显式选择其他页则只识别
            # 目标页，避免全页 OCR 后又回到第 0 页拼接。
            if args.page:
                if not 0 <= args.page < n_pages:
                    raise ValueError(f'文档共 {n_pages} 页, 无效的页码 {args.page}')
                page_numbers = [args.page]
            else:
                page_numbers = range(n_pages)
            pages = [extract_page(conv, p, args, diagnostics=(p == args.page))
                     for p in page_numbers]
            # 语义对齐: 逐页把探测网格锚定到原生 workbook,
            # 给格子/游离文字赋稳定地址 addr (stitch 平移 x 并累加 col)
            try:
                import openpyxl
                wb_f = openpyxl.load_workbook(input_path)
                wb_v = openpyxl.load_workbook(input_path, data_only=True)
                for pg in pages:
                    augment_xlsx_semantics(pg, wb_f, wb_v)
            except ImportError:
                print('未安装 openpyxl, 跳过语义对齐')
            # 宽表被分页: 先横向拼回一整张, 再在数据层等比缩放到
            # A4 页宽；源 PDF 背景使用相同页序列、偏移和缩放。
            data = stitch_page_data(pages)
            scale = 1.0
            if data['width'] > pages[0]['width']:
                scale = pages[0]['width'] / data['width']
                data = scale_data(data, scale)
                print(f'按 A4 页宽等比缩放到 {scale:.0%}')
            if len((data.get('_stitch') or {}).get('pages') or []) > 1:
                background = os.path.join(out_dir, 'stitched_background.png')
                _render_stitched_background(conv, data, background, scale)
                data['_background_path'] = background
        else:
            # 保持单页语义：先验证并确定目标页，避免无效页的全页 OCR。
            if not 0 <= args.page < n_pages:
                raise ValueError(f'文档共 {n_pages} 页, 无效的页码 {args.page}')
            data = extract_page(conv, args.page, args, diagnostics=True)
    else:
        data = (docx_to_data(input_path) if ext == '.docx'
                else xlsx_to_data(input_path))
    assign_roles(data)
    extract_fields(data)
    build_form_view(data)
    build_index(data)
    generate_frontend(data, out_dir)
    return data, conv
