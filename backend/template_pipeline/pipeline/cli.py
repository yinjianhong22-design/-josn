# -*- coding: utf-8 -*-

# ---------------------------------------------------------------------------
# 命令行入口
# ---------------------------------------------------------------------------

from importlib import import_module as _import_module

from ..common import argparse, os, _IMG_EXT
from .document import convert_document
from .page import extract_page

_template = _import_module('..output.template', __package__)
build_template = _template.build_template
_rebuild = _import_module('..output.rebuild', __package__)
json_to_pdf = _rebuild.json_to_pdf
_frontend = _import_module('..output.frontend', __package__)
generate_frontend = _frontend.generate_frontend


def main():
    ap = argparse.ArgumentParser(
        description='图片/PDF/Word/Excel 表格提取与还原')
    ap.add_argument('input', help='图片、PDF、Word(.docx) 或 Excel(.xlsx) 路径')
    ap.add_argument('-o', '--out', default='grid_out', help='输出目录')
    ap.add_argument('--page', type=int, default=0, help='PDF 页码 (从 0 开始)')
    ap.add_argument('--dpi', type=int, default=300, help='PDF 渲染 dpi')
    ap.add_argument('--h-ratio', type=float, default=0.1,
                    help='横线形态学核占图宽比例 (默认 0.1)')
    ap.add_argument('--v-ratio', type=float, default=0.03,
                    help='竖线形态学核占图高比例 (默认 0.03, 竖线常有短段)')
    ap.add_argument('--h-min-span', type=float, default=0.28,
                    help='横线最小覆盖度 (默认 0.28, 用于滤掉页眉下划线等)')
    ap.add_argument('--v-min-span', type=float, default=0.04,
                    help='竖线最小覆盖度 (默认 0.04, 短竖线覆盖度低)')
    ap.add_argument('--h-span-ratio', type=float, default=0.45,
                    help='横线自适应覆盖比例: 只保留 ≥ 最长横线该比例的线, '
                         '与整图比例取 min (默认 0.45, 角落表格防全灭)')
    ap.add_argument('--v-span-ratio', type=float, default=0.20,
                    help='竖线自适应覆盖比例, 语义同上 (默认 0.20)')
    ap.add_argument('--no-ocr', action='store_true',
                    help='跳过 OCR, 生成的 HTML 只还原结构不填文字')
    ap.add_argument('--force-ocr', action='store_true',
                    help='PDF 即使有文字层也强制走 OCR')
    ap.add_argument('--ocr-url', default=os.environ.get('OCR_SERVICE_URL', ''),
                    help='OCR 服务地址 (如 http://127.0.0.1:8100), 设置后'
                         '逐格 OCR 批量提交给该服务 (见 ocr_service.py), '
                         '服务不可达直接报错; 默认取环境变量 OCR_SERVICE_URL')
    ap.add_argument('--no-office', action='store_true',
                    help='docx/xlsx 不调用本机 WPS/Office 转 PDF, '
                         '直接用 python-docx/openpyxl 简化排版')
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)

    ext = os.path.splitext(args.input)[1].lower()
    stem = os.path.splitext(os.path.basename(args.input))[0]
    if ext in ('.docx', '.xlsx'):
        data, office_pdf, pdf_path = convert_document(args.input, args.out,
                                                      args)
        build_template(data, args.out, source_paths=[office_pdf],
                       fallback_pdf=pdf_path, name=stem)
        print(f'格子 {len(data["cells"])} 个, '
              f'段落 {len(data["texts"])} 行, 线段 {len(data["rules"])} 条')
        print(f'还原 PDF: {pdf_path} (数据源: data.json)')
        print(f'前端代码: {os.path.join(args.out, "index.html")} '
              f'(数据: data.json / data.js / template.json)')
        return

    data = extract_page(args.input, args.page, args)
    index_path = pdf_path = None
    if data:
        index_path = generate_frontend(data, args.out)
        pdf_path = json_to_pdf(data, os.path.join(args.out, 'rebuilt.pdf'))
        build_template(data, args.out,
                       source_paths=([args.input] if ext == '.pdf' or
                                     ext in _IMG_EXT else []),
                       fallback_pdf=pdf_path, name=stem)
    if pdf_path:
        print(f'还原 PDF: {pdf_path} (数据源: data.json)')
    if index_path:
        print(f'前端代码: {index_path} (数据: data.json / data.js)')
