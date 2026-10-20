# -*- coding: utf-8 -*-

"""
extract_grid.py

图片/扫描件: OpenCV 提取横竖直线 -> 交点 -> 小格子(含合并单元格), 版面分析
(文字块/行切分)约束字号与位置, OCR 识别文字。
电子档 PDF: 文字层 span(字体/字号/颜色/基线) + 矢量线段直接提取, 免 OCR。
Word (.docx): 段落遍历 + 样式继承链(run->段落样式->文档默认), 标题层级按
样式名判定, 表格处理 gridSpan/vMerge 合并。
Excel (.xlsx): 逐 sheet 遍历, 值/公式/样式/合并区域分开记录。
所有格式统一组织成标准 JSON (data.json), 由 JSON 还原整页 PDF 和 HTML。

可回填表单模板 (docx/xlsx): Office 通路上用文本锚点把探测网格对齐到
原生 workbook, 给格子赋稳定地址 addr (Sheet1!B2) 和 value/formula/
number_format; 再做角色标注 (title|header|label|value|data) 与字段配对,
产出 fields (标签->填空格/内联冒号) 和 table_fields (表体行->可填列)。
data['form'] 是可索引视图: 每条字段一个扁平文档 (唯一 id/name/mode/addr/
几何平铺, 同名带 context 消歧); data['index'] 是可填充索引, 表头行为
分界线: header_fields (以上, 目录 context 纯字典填充) + rows (以下, 数
据简表按 行标签+列名 填充) + by_label (全表兜底), uuid 确定性生成,
cells 表带几何与填充 mode (overwrite/replace/append/inline), 边界情况
全部进 report。渲染层 cells/texts/rules 保持不变。
回填契约: 按 addr 找到格子, 改 text、删 lines, 几何与边框不动。

用法:
    python extract_grid.py input.png [-o out_dir]
    python extract_grid.py input.pdf [--page 0] [--dpi 300]
    python extract_grid.py input.docx | input.xlsx

依赖:
    pip install opencv-python numpy rapidocr-onnxruntime
    (PDF 输入另需: pip install pymupdf)

输出 (输出目录下):
    lines.json   横线/竖线坐标、交点、每个格子(含 rowspan/colspan/文字)
    overlay.png  在原图上画出线、交点、格子编号，便于人工核对
    data.json    标准 JSON: dpi + 整页几何 + 格子(边框/文字) + 格外游离文字
    rebuilt.pdf  按 data.json 重画的矢量 PDF 整页 (表格 + 页眉标题页码)
    data.js      同一份数据包成 window.TABLE_DATA, 供 file:// 直接打开
    index.html   纯渲染层: 读 data.js, 按 JSON 映射还原出像素级表格
"""

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request

import cv2
import numpy as np

# ---------------------------------------------------------------------------
# 共享模块级内容: PyMuPDF 导入 / 跨模块常量 / 小工具
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 加载
# ---------------------------------------------------------------------------

def _import_pymupdf():
    """导入 PyMuPDF (新版包名 pymupdf, 旧版 fitz)。"""
    try:
        import pymupdf
        return pymupdf
    except ImportError:
        try:
            import fitz
            return fitz
        except ImportError:
            sys.exit('读取 PDF 需要 PyMuPDF:  pip install pymupdf')

# 识别置信度阈值: 构造引擎 (text_score) 与逐格兜底判定共用,
# ocr_service.py 侧也引用此值, 改一处两端一致
_OCR_TEXT_SCORE = 0.3

_NO_LABEL_PREFIX = tuple('0123456789△▲□■＋±+-≤≥<>＝=%')

def _jsonable(v):
    """把 openpyxl 单元格值转成 JSON 可序列化形态。"""
    import datetime
    if v is None or isinstance(v, (int, float, str, bool)):
        return v
    if isinstance(v, (datetime.datetime, datetime.date, datetime.time)):
        return v.isoformat()
    return str(v)

_IMG_EXT = ('.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff', '.webp')
