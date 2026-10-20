# -*- coding: utf-8 -*-

# ---------------------------------------------------------------------------
# 加载: 图片/PDF -> 位图
# ---------------------------------------------------------------------------

from ..common import os, sys, cv2, np, _import_pymupdf


def load_image(path, page=0, dpi=300):
    """加载图片；PDF 先用 PyMuPDF 按指定 dpi 渲染成位图。"""
    ext = os.path.splitext(path)[1].lower()
    if ext == '.pdf':
        fitz = _import_pymupdf()
        doc = fitz.open(path)
        if not (0 <= page < len(doc)):
            sys.exit(f'PDF 共 {len(doc)} 页, 无效的页码 {page}')
        pix = doc[page].get_pixmap(dpi=dpi)
        img = np.frombuffer(pix.samples, dtype=np.uint8)
        img = img.reshape(pix.height, pix.width, pix.n)
        if pix.n == 4:
            img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
        elif pix.n == 1:
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        doc.close()
        return img
    # cv2.imread 在 Windows 上走 ANSI 代码页, 中文路径读不出来;
    # imdecode(fromfile) 按字节读盘, 与路径编码无关
    # (np 用模块级 import, 这里不能再局部 import——否则整个函数里
    #  np 变为局部名, 上面 PDF 分支提前使用会直接 UnboundLocalError)
    img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        sys.exit(f'无法读取图片: {path}')
    return img
