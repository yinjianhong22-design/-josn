# -*- coding: utf-8 -*-

"""不依赖 OpenCV/NumPy 的共享常量与小工具。"""

# 识别置信度阈值: 构造引擎 (text_score) 与逐格兜底判定共用,
# ocr_service.py 侧也引用此值, 改一处两端一致
_OCR_TEXT_SCORE = 0.3

_NO_LABEL_PREFIX = tuple('0123456789△▲□■＋±+-≤≥<>＝=%')

_IMG_EXT = ('.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff', '.webp')


def _jsonable(v):
    """把 openpyxl 单元格值转成 JSON 可序列化形态。"""
    import datetime
    if v is None or isinstance(v, (int, float, str, bool)):
        return v
    if isinstance(v, (datetime.datetime, datetime.date, datetime.time)):
        return v.isoformat()
    return str(v)
