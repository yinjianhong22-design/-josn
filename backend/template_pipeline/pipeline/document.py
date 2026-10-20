# -*- coding: utf-8 -*-

# ---------------------------------------------------------------------------
# docx/xlsx 完整转换流水线 (main 与 server 共用)
# ---------------------------------------------------------------------------

from importlib import import_module as _import_module

from ..common import os, _import_pymupdf
from .page import extract_page
from .stitch import stitch_page_data, scale_data

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
_rebuild = _import_module('..output.rebuild', __package__)
json_to_pdf = _rebuild.json_to_pdf


def convert_document(input_path, out_dir, args):
    """docx/xlsx 完整转换流水线 (main 与 server 共用)。

    优先用本机 WPS/Office 排版引擎 100% 原样转 PDF, 走电子档通路;
    失败才回退到 python-docx/openpyxl 的简化排版。
    依次产出: form.json/data.json/data.js/index.html (generate_frontend)
    和 rebuilt.pdf。返回 (data, office_pdf, pdf_path): office_pdf 是
    排版引擎转出的原样 PDF (无 WPS/Office 时为 None)。
    """
    ext = os.path.splitext(input_path)[1].lower()
    conv = None if args.no_office else office_to_pdf(input_path, out_dir)
    if conv:
        fitz = _import_pymupdf()
        doc = fitz.open(conv)
        n_pages = len(doc)
        doc.close()
        pages = [extract_page(conv, p, args, diagnostics=(p == 0))
                 for p in range(n_pages)]
        if ext == '.xlsx':
            # 语义对齐: 逐页把探测网格锚定到原生 workbook,
            # 给格子/游离文字赋稳定地址 addr (stitch 只平移 x, 先行列号不变)
            try:
                import openpyxl
                wb_f = openpyxl.load_workbook(input_path)
                wb_v = openpyxl.load_workbook(input_path, data_only=True)
                for pg in pages:
                    augment_xlsx_semantics(pg, wb_f, wb_v)
            except ImportError:
                print('未安装 openpyxl, 跳过语义对齐')
            # 宽表被分页: 先横向拼回一整张, 再在数据层等比缩放到
            # A4 页宽 (纯数学缩放, 相对位置严格不变)
            data = stitch_page_data(pages)
            if data['width'] > pages[0]['width']:
                s = pages[0]['width'] / data['width']
                data = scale_data(data, s)
                print(f'按 A4 页宽等比缩放到 {s:.0%}')
        else:
            data = pages[args.page] if args.page < n_pages else pages[0]
    else:
        data = (docx_to_data(input_path) if ext == '.docx'
                else xlsx_to_data(input_path))
    assign_roles(data)
    extract_fields(data)
    build_form_view(data)
    build_index(data)
    generate_frontend(data, out_dir)
    pdf_path = json_to_pdf(data, os.path.join(out_dir, 'rebuilt.pdf'))
    return data, conv, pdf_path
