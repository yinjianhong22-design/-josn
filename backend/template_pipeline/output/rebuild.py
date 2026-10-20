# -*- coding: utf-8 -*-

# ---------------------------------------------------------------------------
# JSON -> PDF 还原 + 字体映射/字段样式
# ---------------------------------------------------------------------------

from ..common import np, os, _import_pymupdf


def _find_cjk_font():
    """在常见路径里找一个支持中文的 TTF 字体 (PDF 嵌入用)。"""
    candidates = [
        r'C:\Windows\Fonts\simhei.ttf',
        r'C:\Windows\Fonts\msyh.ttc',
        r'C:\Windows\Fonts\simsun.ttc',
        '/System/Library/Fonts/PingFang.ttc',
        '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
    ]
    return next((p for p in candidates if os.path.exists(p)), None)


def _map_font(font_name):
    """把 PDF 里的原字体名映射到本机字体文件 (宋体/黑体/常见西文)。

    找不到对应文件时返回 None, 由调用方退回默认中文字体。
    """
    name = (font_name or '').lower()
    table = [
        (('simsun', 'songti', 'song'), [r'C:\Windows\Fonts\simsun.ttc']),
        (('simhei', 'heiti', 'hei'), [r'C:\Windows\Fonts\simhei.ttf']),
        (('msyh', 'yahei'), [r'C:\Windows\Fonts\msyh.ttc']),
        (('kaiti', 'kai'), [r'C:\Windows\Fonts\simkai.ttf']),
        (('fangsong', 'fang'), [r'C:\Windows\Fonts\simfang.ttf']),
        (('arial',), [r'C:\Windows\Fonts\arial.ttf']),
        (('times',), [r'C:\Windows\Fonts\times.ttf']),
    ]
    for keys, paths in table:
        if any(k in name for k in keys):
            hit = next((p for p in paths if os.path.exists(p)), None)
            if hit:
                return hit
    return None


def json_to_pdf(data, out_path, border_width=0.7):
    """按标准 JSON 重画出 PDF: 逐格画真实存在的边框, 文字自动适配填入。

    坐标换算: point = px * 72 / dpi (dpi 取自 JSON, 即渲染原图时的 dpi)。
    字体按 JSON 里记录的原字体名映射到本机字体文件 (宋体/黑体/西文),
    映射不到时退回默认中文字体; 都没有才用 PyMuPDF 内置 "china-s"
    (内置字体是逐 glyph 绘制的 fallback, 字符间会出现多余空隙)。
    文字落位三档: 带基线+字号的行 (PDF 文字层) 原样落位 > 带行高的行
    (OCR 行切分) 按行高定字号 > 无位置信息时 insert_textbox 自动适配。
    """
    fitz = _import_pymupdf()
    s = 72.0 / data.get('dpi', 300)
    doc = fitz.open()
    page = doc.new_page(width=data['width'] * s, height=data['height'] * s)
    default_file = _find_cjk_font()
    registry = {}  # fontfile -> (pdf 内字体名, fitz.Font)

    def font_for(orig_name=None):
        """按原字体名取 (pdf 内字体名, Font), 按需嵌入并缓存。"""
        file = _map_font(orig_name) or default_file
        if file:
            if file not in registry:
                fn = f'F{len(registry)}'
                page.insert_font(fontname=fn, fontfile=file)
                registry[file] = (fn, fitz.Font(fontfile=file))
            return registry[file]
        if 'china-s' not in registry:
            registry['china-s'] = ('china-s', fitz.Font('china-s'))
        return registry['china-s']

    # 电子档有原始矢量线段: 直接按精确坐标+原线宽逐条画, 每根线只画一次,
    # 不再按格子边逐边描绘 (避免共享边重复描、粗外框被画成细线、下划线丢失)
    rules = data.get('rules') or []
    for rl in rules:
        page.draw_line((rl['x0'] * s, rl['y0'] * s),
                       (rl['x1'] * s, rl['y1'] * s),
                       width=max(0.1, rl['width'] * s))

    for c in data['cells']:
        x, y = c['x'] * s, c['y'] * s
        r = fitz.Rect(x, y, x + c['w'] * s, y + c['h'] * s)
        b = c.get('borders') or {}
        if not rules:
            if b['top']:
                page.draw_line(r.tl, r.tr, width=border_width)
            if b['bottom']:
                page.draw_line(r.bl, r.br, width=border_width)
            if b['left']:
                page.draw_line(r.tl, r.bl, width=border_width)
            if b['right']:
                page.draw_line(r.tr, r.br, width=border_width)

        max_w = c['w'] * s - 4
        if c.get('lines') and 'size' in c['lines'][0]:
            # PDF 文字层: 每行按基线坐标 + 原字号/字体/颜色精确落位, 不重排
            for ln in c['lines']:
                txt = ln['text'].strip()
                if not txt:
                    continue
                fn, fnt = font_for(ln.get('font'))
                col = ln.get('color') or '#000000'
                rgb = tuple(int(col[i:i + 2], 16) / 255 for i in (1, 3, 5))
                size = ln['size']
                tw = fnt.text_length(txt, fontsize=size)
                orig_w = (ln.get('w') or 0) * s
                pt = (ln['x'] * s, ln['y'] * s)
                if len(txt) > 1 and orig_w > tw * 1.05:
                    # 原件用字符间距撑开的行 (如 "年 月 日"): 逐字均摊间距
                    gap = (orig_w - tw) / (len(txt) - 1)
                    cx = pt[0]
                    for ch in txt:
                        page.insert_text((cx, pt[1]), ch, fontsize=size,
                                         fontname=fn, color=rgb)
                        cx += fnt.text_length(ch, fontsize=size) + gap
                    continue
                if tw > max_w:  # 嵌入字体度量差异超宽时同比缩小
                    size *= max_w / tw
                page.insert_text(pt, txt, fontsize=size,
                                 fontname=fn, color=rgb)
                if ln.get('bold'):
                    page.insert_text((pt[0] + 0.3, pt[1]), txt,
                                     fontsize=size, fontname=fn, color=rgb)
            continue

        fontname, font = font_for(c.get('font'))
        if c.get('lines'):
            # OCR 行切分: 逐行按行高定字号、按行位置落基线。
            # 同一格内 >=3 行或有任一行接近格宽 -> 按段落处理(整格左对齐),
            # 避免段落里较短的行被居中造成参差不齐
            para = len(c['lines']) >= 3 or any(
                font.text_length(ln['text'].strip(),
                                 fontsize=ln['h'] * s * 0.75) > max_w * 0.7
                for ln in c['lines'] if ln['text'].strip())
            for ln in c['lines']:
                txt = ln['text'].strip()
                if not txt:
                    continue
                size = ln['h'] * s * 0.75
                tw = font.text_length(txt, fontsize=size)
                if tw > max_w:  # 字体度量差异导致超宽时同比缩小
                    size *= max_w / tw
                    tw = max_w
                lx = r.x0 + 2 if para else r.x0 + (c['w'] * s - tw) / 2
                ly = (ln['y'] + ln['h'] * 0.82) * s
                page.insert_text((lx, ly), txt, fontsize=size,
                                 fontname=fontname)
            continue

        text = (c.get('text') or '').strip()
        if not text:
            continue
        inner = fitz.Rect(r.x0 + 2, r.y0 + 1, r.x1 - 2, r.y1 - 1)
        lines = text.split('\n')
        size = min(float(c.get('size') or 12.0), inner.height * 0.8)
        if len(lines) == 1:
            # 单行文字先按宽度预缩, 避免 insert_textbox 把短行折成两行
            tw = font.text_length(text, fontsize=size)
            if tw > inner.width:
                size = max(4.0, size * inner.width / tw)
        col = c.get('color') or '#000000'
        crgb = tuple(int(col[i:i + 2], 16) / 255 for i in (1, 3, 5))
        while size > 4:
            widest = max(font.text_length(l, fontsize=size) for l in lines)
            # 显式对齐优先; 否则段落(最宽行接近格宽)左对齐, 短文字居中
            al = c.get('align')
            if al == 'left':
                align = fitz.TEXT_ALIGN_LEFT
            elif al == 'right':
                align = fitz.TEXT_ALIGN_RIGHT
            elif al == 'center':
                align = fitz.TEXT_ALIGN_CENTER
            else:
                align = fitz.TEXT_ALIGN_LEFT if widest > inner.width * 0.7 \
                    else fitz.TEXT_ALIGN_CENTER
            # 估算换行后的行数, 把文字块整体垂直居中
            n = sum(max(1, int(np.ceil(
                font.text_length(l, fontsize=size) / inner.width)))
                for l in lines)
            block_h = n * size * 1.3
            box = fitz.Rect(inner.x0, inner.y0, inner.x1, inner.y1)
            if block_h < inner.height:
                box.y0 += (inner.height - block_h) / 2
            rc = page.insert_textbox(box, text, fontsize=size,
                                     fontname=fontname, align=align,
                                     color=crgb)
            if rc >= 0:
                if c.get('bold'):  # 模拟加粗
                    page.insert_textbox(
                        fitz.Rect(box.x0 + 0.3, box.y0, box.x1 + 0.3,
                                  box.y1),
                        text, fontsize=size, fontname=fontname,
                        align=align, color=crgb)
                break
            size -= 0.5

    # 表格线框外的游离文字(页眉/标题/页码等): 按基线坐标、原字号、
    # 原字体、原色落位; 粗体/标题用微偏移二次绘制模拟加粗
    for t in data.get('texts', []):
        fn, fnt = font_for(t.get('font'))
        col = t.get('color') or '#000000'
        rgb = tuple(int(col[i:i + 2], 16) / 255 for i in (1, 3, 5))
        size = t.get('size', 10)
        tx = t['x'] * s
        tw = fnt.text_length(t['text'], fontsize=size)
        if t.get('align') and t.get('w'):  # 居中/右对齐的段落
            if t['align'] == 'center':
                tx += (t['w'] * s - tw) / 2
            elif t['align'] == 'right':
                tx += t['w'] * s - tw
        pt = (tx, t['y'] * s)
        page.insert_text(pt, t['text'], fontsize=size,
                         fontname=fn, color=rgb)
        if t.get('bold') or t.get('role') in ('title', 'heading'):
            page.insert_text((pt[0] + 0.3, pt[1]), t['text'], fontsize=size,
                             fontname=fn, color=rgb)

    err = None
    for k in range(10):
        # 目标文件被占用(如在 PDF 阅读器中打开)时自动换名: _1, _2, ...
        name = out_path if k == 0 else out_path.replace('.pdf', f'_{k}.pdf')
        try:
            doc.save(name, deflate=True)
            if k:
                print(f'{out_path} 被占用, 已改存 {name}')
            out_path = name
            break
        except Exception as e:
            err = e
    else:
        doc.close()
        raise err
    doc.close()
    return out_path


def _font_family(name):
    """归一化字体名: 去 PDF 子集前缀 (ABCDEE+SimSun), 中文名映射英文，
    对齐前端 fonts.ts 的 documentFonts 候选。"""
    if not name:
        return None
    name = str(name).split('+')[-1].strip()
    return _FONT_ALIASES.get(name, name)


_FONT_ALIASES = {
    '宋体': 'SimSun', '黑体': 'SimHei', '微软雅黑': 'Microsoft YaHei',
    '仿宋': 'FangSong', '楷体': 'KaiTi', '等线': 'DengXian',
    'ArialMT': 'Arial', 'TimesNewRomanPSMT': 'Times New Roman',
}


def _field_style(e, size):
    """index.cells 实体 -> 前端 FieldStyle (字体/字号/颜色/对齐)。"""
    style = {'fontSizePt': size,
             'horizontalAlign': e.get('align') or 'center',
             'verticalAlign': 'center'}
    fam = _font_family(e.get('font'))
    if fam:
        style['fontFamily'] = fam
    if e.get('color'):
        style['color'] = e['color']
    if e.get('bold'):
        style['bold'] = True
    return style
