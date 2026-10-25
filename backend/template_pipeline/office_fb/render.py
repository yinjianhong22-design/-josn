# -*- coding: utf-8 -*-

# ---------------------------------------------------------------------------
# 标准 JSON -> 背景图 (PIL 自渲染, office_fb 简化排版通路的背景来源)
# ---------------------------------------------------------------------------

from ..common import os

# 字体候选链 (Windows 常见中文字体, 模块常量, 新环境加一行即可);
# 优先微软雅黑, 黑体/宋体兜底。粗体优先微软雅黑 Bold。
_FONT_CANDIDATES = ('msyh.ttc', 'simhei.ttf', 'simsun.ttc')
_FONT_BOLD_CANDIDATES = ('msyhbd.ttc', 'simhei.ttf', 'simsun.ttc')
_FONT_DIR = r'C:\Windows\Fonts'
_LINE_COLOR = (0, 0, 0)
_TEXT_COLOR = (0, 0, 0)

_font_cache = {}


def _load_font(px, bold=False):
    """按像素字号加载中文字体 (带缓存), 找不到回退 PIL 默认位图字体。"""
    from PIL import ImageFont

    key = (px, bool(bold))
    if key in _font_cache:
        return _font_cache[key]
    font = None
    for name in (_FONT_BOLD_CANDIDATES if bold else _FONT_CANDIDATES):
        p = os.path.join(_FONT_DIR, name)
        if os.path.exists(p):
            try:
                font = ImageFont.truetype(p, px)
                break
            except Exception:
                font = None
    if font is None:
        print('未找到中文字体, 背景文字将用 PIL 默认字体 (可能无法显示中文)')
        font = ImageFont.load_default()
    _font_cache[key] = font
    return font


def _fit_font(draw, text, px, bold, max_w):
    """文字宽度超格时逐级缩小字号 (最多到 60%), 仍超则原样画 (允许视觉裁切)。"""
    from PIL import ImageFont

    font = _load_font(px, bold)
    while px > 6 and draw.textlength(text, font=font) > max_w:
        px = max(6, int(px * 0.85))
        font = _load_font(px, bold)
    return font


def _draw_block(draw, text, box, size_pt, bold, color, align, s):
    """在 (x, y, w, h) 里画多行文字: 垂直居中, 水平按 align
    (left/center/right, 默认 center)。字号 pt -> 像素乘 dpi 比 s。"""
    if not text or not text.strip():
        return
    x, y, w, h = box
    px = max(6, int(round((size_pt or 10.5) * s)))
    lines = str(text).split('\n')
    pad = 3 * s
    max_w = max(8, w - 2 * pad)
    line_h = int(px * 1.35)
    total_h = line_h * len(lines)
    ty = y + max(0, (h - total_h) // 2)
    for ln in lines:
        t = ln.strip()
        if not t:
            ty += line_h
            continue
        font = _fit_font(draw, t, px, bold, max_w)
        tw = draw.textlength(t, font=font)
        if align == 'left':
            tx = x + pad
        elif align == 'right':
            tx = x + w - pad - tw
        else:
            tx = x + max(0, (w - tw) // 2)
        draw.text((tx, ty), t, font=font, fill=color or _TEXT_COLOR)
        ty += line_h


def render_data_background(data):
    """标准 JSON -> 背景 PIL.Image (2px/pt 约定, 与 build_template 一致)。

    白底 -> rules 画线 -> cells 按 size/align/bold/color 画文字
    -> texts 游离文字 (y 视为基线)。只消费标准 JSON 字段, 通用,
    不特判任何具体表。字体/行高是近似值 (无真实排版引擎),
    视觉保真度低于真实排版引擎底图, 仅用于 office_fb 简化排版。
    """
    from PIL import Image, ImageDraw

    dpi = data.get('dpi') or 96
    s = dpi / 72.0
    w, h = int(data['width']), int(data['height'])
    img = Image.new('RGB', (max(1, w), max(1, h)), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    for r in data.get('rules') or []:
        # 标准 JSON 的 rules.width 与坐标一样，均为最终像素。
        wd = max(1, int(round(r.get('width') or 1.0)))
        draw.line([(r['x0'], r['y0']), (r['x1'], r['y1'])],
                  fill=_LINE_COLOR, width=wd)
    for c in data.get('cells') or []:
        color = None
        if c.get('color'):
            try:
                color = tuple(int(c['color'].lstrip('#')[i:i + 2], 16)
                              for i in (0, 2, 4))
            except Exception:
                color = None
        _draw_block(draw, c.get('text'),
                    (c['x'], c['y'], c['w'], c['h']),
                    c.get('size'), c.get('bold'), color,
                    c.get('align'), s)
    # 游离文字换行后可能超出原版面高 (docx 多页流式下排), 以实际
    # 文字底边为准扩画布, 防底部裁切; 段落间用 cursor 顺序下推,
    # 防换行多出的行与下一段重叠
    bottom = h
    cursor = None
    for t in data.get('texts') or []:
        size_pt = t.get('size') or 10.5
        px = max(6, int(round(size_pt * s)))
        font = _load_font(px, t.get('bold'))
        color = None
        if t.get('color'):
            try:
                color = tuple(int(t['color'].lstrip('#')[i:i + 2], 16)
                              for i in (0, 2, 4))
            except Exception:
                color = None
        text = str(t.get('text') or '')
        # 按内容宽贪心换行 (docx 段落的 w = 版心宽), 防长行溢出画布
        maxw = t.get('w') or 0
        raw_lines = []
        for ln in text.split('\n'):
            if maxw and draw.textlength(ln, font=font) > maxw:
                buf = ''
                for ch in ln:
                    if buf and draw.textlength(buf + ch, font=font) > maxw:
                        raw_lines.append(buf)
                        buf = ch
                    else:
                        buf += ch
                raw_lines.append(buf)
            else:
                raw_lines.append(ln)
        # 游离文字 y 视为基线 (docx_reader 契约), 逐行下排;
        # 前段换行撑高后用 cursor 顺序下推, 与下一段不重叠
        ty = int(max(t['y'] - px, cursor)) if cursor is not None \
            else int(t['y']) - px
        for ln in raw_lines:
            if not ln.strip():
                ty += int(px * 1.35)
                continue
            if t.get('align') == 'center' and t.get('w'):
                tw = draw.textlength(ln.strip(), font=font)
                tx = t['x'] + max(0, (t['w'] - tw) // 2)
            elif t.get('align') == 'right' and t.get('w'):
                tw = draw.textlength(ln.strip(), font=font)
                tx = t['x'] + t['w'] - tw
            else:
                tx = t['x']
            draw.text((tx, ty), ln.strip(), font=font,
                      fill=color or _TEXT_COLOR)
            ty += int(px * 1.35)
        cursor = ty
        bottom = max(bottom, ty)
    if bottom > h:
        ext = Image.new('RGB', (w, bottom), (255, 255, 255))
        ext.paste(img, (0, 0))
        img = ext
        h = bottom
        draw = ImageDraw.Draw(img)
    # 输出按 2px/pt 约定缩放 (与 build_template 背景尺寸/前端字号公式一致)
    tw = round(w * 72.0 / dpi * 2)
    th = round(h * 72.0 / dpi * 2)
    if (tw, th) != (w, h):
        img = img.resize((tw, th), Image.LANCZOS)
    return img


def save_background(data, out_path):
    """渲染背景并落盘, 返回 (宽, 高) 像素。"""
    img = render_data_background(data)
    img.save(out_path)
    return img.size
