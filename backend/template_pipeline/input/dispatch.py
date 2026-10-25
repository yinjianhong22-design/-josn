# -*- coding: utf-8 -*-

# ---------------------------------------------------------------------------
# 输入类型判定
# ---------------------------------------------------------------------------

import os

from ..constants import _IMG_EXT


def detect_input_type(input_path):
    """判断输入文件类型: 'pdf' / 'image' (图片扩展名) / 'other' (docx/xlsx 等 Office 文档)。"""
    ext = os.path.splitext(input_path)[1].lower()
    if ext == '.pdf':
        return 'pdf'
    if ext in _IMG_EXT:
        return 'image'
    return 'other'

