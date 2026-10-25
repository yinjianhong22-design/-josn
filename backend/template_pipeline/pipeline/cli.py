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
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)

    ext = os.path.splitext(args.input)[1].lower()
    stem = os.path.splitext(os.path.basename(args.input))[0]
    if ext in ('.docx', '.xlsx'):
        data, office_pdf = convert_document(args.input, args.out, args)
        build_template(data, args.out,
                       source_paths=[office_pdf] if office_pdf else [],
                       name=stem, source_ext=None if office_pdf else ext)
        print(f'格子 {len(data["cells"])} 个, '
              f'段落 {len(data["texts"])} 行, 线段 {len(data["rules"])} 条')
        print(f'前端代码: {os.path.join(args.out, "index.html")} '
              f'(数据: data.json / data.js / template.json)')
        return

    if ext == '.pdf' and args.page == 0:
        # 默认转换完整 PDF，让横向宽表与 xlsx 走同一拼接逻辑；显式
        # 选择其他页时仍只识别目标页。独立页/纵向页由 stitch 原样保留。
        from ..common import _import_pymupdf
        from .document import _render_stitched_background
        from .stitch import stitch_page_data

        doc = _import_pymupdf().open(args.input)
        try:
            pages = [extract_page(args.input, p, args, diagnostics=(p == 0))
                     for p in range(len(doc))]
        finally:
            doc.close()
        data = stitch_page_data(pages)
        if len((data.get('_stitch') or {}).get('pages') or []) > 1:
            background = os.path.join(args.out, 'stitched_background.png')
            _render_stitched_background(args.input, data, background)
            data['_background_path'] = background
    else:
        data = extract_page(args.input, args.page, args)
    index_path = None
    if data:
        index_path = generate_frontend(data, args.out)
        build_template(data, args.out,
                       source_paths=([args.input] if ext == '.pdf' or
                                     ext in _IMG_EXT else []),
                       name=stem)
    if index_path:
        print(f'前端代码: {index_path} (数据: data.json / data.js)')


if __name__ == '__main__':
    main()
