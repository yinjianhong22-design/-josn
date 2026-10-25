# -*- coding: utf-8 -*-

# ---------------------------------------------------------------------------
# 前端 Template JSON (template.json) + 背景图 background.png
# ---------------------------------------------------------------------------

from importlib import import_module as _import_module

from ..common import (cv2, json, np, os, _import_pymupdf, _IMG_EXT)

# _INDEX_NS 是 semantic.index 的延迟初始化全局状态 (uuid5
# namespace), 通过模块引用访问以保持与原全局变量同等的惰性
_index_mod = _import_module('..semantic.index', __package__)


# ---------------------------------------------------------------------------
# 字体映射/字段样式 (PDF 重画链路已删除, 仅服务字段覆盖层)
# ---------------------------------------------------------------------------

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


def build_template(data, out_dir, source_paths=(), name=None,
                   bg_url='background.png', source_ext=None, source_page=None):
    """生成前端 Template JSON (template.json) + 背景图 background.png。

    前端复现采用"背景图 + 字段覆盖层"混合方案 (frontend TemplatePage.vue):
    - 背景图: 有排版引擎 PDF/原始图片/PDF 候选时, pymupdf/解码归一化成
      background.png, "原样张"视觉上由它保证; 无候选 (office_fb 简化排版
      通路) 时由 data 自渲染 (office_fb.render, 白底 + 线 + 文字);
    - 字段层: OpenCV 探测网格的每一格变成一个 Field (与背景表格线严格
      对齐), rect 为占页宽/页高的比例坐标, uuid = uuid5(addr) 与
      index.cells 同一 uuid —— header_fields/rows/by_label 的 value
      引用同一 uuid, 回填定位零换算; index 解析好的样式/填充语义按
      uuid 挂载, 识别文字进 label (不做覆盖层重画, 视觉以背景图为
      唯一真相, 覆盖层只在填值时出现)。
    page.width/height 用背景图像素尺寸 (2px/pt 栅格的宽/高), 不是 PDF 点:
    前端字号公式 fontSizePt*2/page.width*100cqw (TemplatePage.vue) 和
    PrintPreview 的 page.width/2*25.4/72 (mm) 都按这个约定消费。
    无 index 的通路 (图片/PDF) 退化为逐格生成 Field。
    背景候选 (source_paths) 的几何 (页面点大小) 必须与探测网格一致才
    采用; 传了候选但全部不匹配时直接 raise RuntimeError (不静默产出
    几何不可信的模板); source_paths 为空时自渲染背景 (source_ext
    提供 sourceFormat, 如 '.xlsx'/'.docx')。
    """
    import uuid as _uuid
    fitz = _import_pymupdf()
    dpi = data.get('dpi') or 300
    pt_w = data['width'] * 72.0 / dpi
    pt_h = data['height'] * 72.0 / dpi

    # 背景源: 逐个候选试, 几何 (页面点大小) 与 data 一致才采用;
    # 图片(扫描件)候选直接作背景, 归一化到 2px/pt 约定
    bg_path = os.path.join(out_dir, 'background.png')
    used_src = None
    bg_wh = None
    if source_page is None:
        source_page = data.get('source_page', 0)
    synthetic_bg = data.get('_background_path')
    candidates = ([synthetic_bg] if synthetic_bg else []) + list(source_paths)
    for cand in candidates:
        if not cand or not os.path.exists(cand):
            continue
        if os.path.splitext(cand)[1].lower() in _IMG_EXT:
            # np 用模块级 import; 不在这里局部 import (局部 import 会让
            # np 成为本函数局部名, 函数内其他分支一旦用 np 即 UnboundLocal)
            img = cv2.imdecode(np.fromfile(cand, dtype=np.uint8),
                               cv2.IMREAD_COLOR)
            if img is None:
                continue
            tw, th = round(pt_w * 2), round(pt_h * 2)
            if (img.shape[1], img.shape[0]) != (tw, th):
                interp = (cv2.INTER_AREA if img.shape[1] > tw
                          else cv2.INTER_CUBIC)
                img = cv2.resize(img, (tw, th), interpolation=interp)
            cv2.imwrite(bg_path, img)
            used_src = cand
            bg_wh = (tw, th)
            break
        doc = None
        try:
            doc = fitz.open(cand)
            if not 0 <= source_page < len(doc):
                raise RuntimeError(
                    f'背景 PDF 共 {len(doc)} 页, 无效的页码 {source_page}')
            p = doc[source_page]
            if abs(p.rect.width - pt_w) <= max(2.0, pt_w * 0.02) and \
                    abs(p.rect.height - pt_h) <= max(2.0, pt_h * 0.02):
                pix = p.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                pix.save(bg_path)
                used_src = cand
                bg_wh = (pix.width, pix.height)
        except RuntimeError:
            raise
        except Exception:
            pass
        finally:
            if doc is not None:
                doc.close()
        if used_src:
            break
    if not used_src:
        if candidates:
            cands = [p for p in candidates if p]
            raise RuntimeError(
                '背景图生成失败: 所有背景候选的几何都与探测网格不匹配 '
                f'(data 尺寸 {pt_w:.1f}x{pt_h:.1f} pt, 候选 {cands})')
        # 无背景候选: office_fb 简化排版通路, 由 data 自渲染背景
        from ..office_fb.render import save_background
        bg_wh = save_background(data, bg_path)
        print('背景: 自渲染 (office_fb 简化排版)')

    # 字段层: OpenCV 探测网格的每一格 -> Field, 与背景表格线严格对齐;
    # uuid = uuid5(addr), 与 index.cells 同一 uuid, 回填定位零换算;
    # index 解析好的样式 (字号/字体/颜色/对齐/合并文本/填充语义) 按 uuid
    # 挂到对应格上, 没进 index 的普通格直接用自身文字层的样式。
    # 识别文字一律进 label (不进 textOverride, 覆盖层只在运行时填值出现)
    ns = _index_mod._INDEX_NS or _uuid.UUID('7d4f2a90-3b1c-5e6a-9f08-2d5b8c4a7e91')
    idx_cells = ((data.get('index') or {}).get('cells')) or {}
    # 坐标分母与最终背景同源；自渲染扩画布后不能使用原 data.height。
    # 背景统一为 2px/pt，换算回 data 所使用的 dpi 像素坐标。
    W, H = bg_wh[0] * dpi / 144.0, bg_wh[1] * dpi / 144.0
    fields = []
    seen = set()

    def _emit(u, x, y, w, h, ent, text, addr):
        w = min(w, W)
        h = min(h, H)
        x = max(0.0, min(x, W - w))
        y = max(0.0, min(y, H - h))
        f = {'fieldUuid': u,
             'rect': {'x': round(x / W, 6), 'y': round(y / H, 6),
                      'w': round(w / W, 6), 'h': round(h / H, 6)},
             'style': _field_style(ent, round(ent.get('size') or 10, 2))}
        if text:
            f['label'] = text
        if addr:
            f['source'] = {'range': addr}
        if ent.get('mode'):
            f['mode'] = ent['mode']
            if ent.get('placeholder'):
                f['placeholder'] = ent['placeholder']
        fields.append(f)
        seen.add(u)

    for c in data.get('cells') or []:
        a = c.get('addr')
        u = str(_uuid.uuid5(ns, a)) if a else str(
            _uuid.uuid5(ns, f"#{c.get('row')},{c.get('col')}"))
        e = idx_cells.get(u) or {}
        # index 合并文本 (同 addr 游离文字按视觉行拼接) 优先于格内 text;
        # 样式: index 解析结果覆盖格内原始属性
        text = e.get('text') or (c.get('text') or '').strip() or None
        ent = dict(c)
        ent.update(e)
        _emit(u, c['x'], c['y'], c['w'], c['h'], ent, text, a)
    # index 里的游离文字实体 (监理单位/编号等, 无格子) 也生成字段,
    # 几何按字号估算
    for u, e in idx_cells.items():
        if u in seen:
            continue
        x, y, w, h = e['x'], e['y'], e['w'], e['h']
        size = e.get('size') or 10
        if (not w or not h) and e.get('text'):
            n = len(''.join(str(e['text']).split()))
            w = w or n * size * dpi / 72.0
            h = h or size * dpi / 72.0 * 1.4
            y = y - h * 0.85
        _emit(u, x, y, w, h, e, e.get('text'), e.get('addr'))
    # 渲染层游离文字 (标题/页眉/拍照件整页文字) 也生成字段:
    # 拍照件没有格子, 文字字段就是全部可点区域
    for i, t in enumerate(data.get('texts') or []):
        a = t.get('addr')
        u = str(_uuid.uuid5(ns, a)) if a else str(
            _uuid.uuid5(ns, f'#T{i}'))
        if u in seen:
            continue
        size = t.get('size') or 10
        txt = (t.get('text') or '').strip()
        n = len(''.join(txt.split()))
        w = n * size * dpi / 72.0
        h = size * dpi / 72.0 * 1.4
        _emit(u, t['x'], t['y'] - h * 0.85, w, h, dict(t), txt or None, a)

    form_meta = ((data.get('form') or {}).get('meta')) or {}
    tpl_name = (name or form_meta.get('title') or '未命名表单')
    ext = (os.path.splitext(os.path.basename(used_src))[1]
           if used_src else (source_ext or ''))
    template = {
        'templateUuid': str(_uuid.uuid5(ns, 'template:' + tpl_name)),
        'name': tpl_name,
        'version': 1,
        'sourceFormat': ext.lstrip('.'),
        'pages': [{
            'pageUuid': str(_uuid.uuid5(ns, 'page:' + tpl_name)),
            'pageNo': 1,
            # 背景像素尺寸 (2px/pt 栅格的宽/高)
            'width': bg_wh[0],
            'height': bg_wh[1],
            'background': bg_url,
            'fields': fields,
        }],
    }
    tpl_path = os.path.join(out_dir, 'template.json')
    with open(tpl_path, 'w', encoding='utf-8') as f:
        json.dump(template, f, ensure_ascii=False, indent=2)
    print(f'前端模板: {tpl_path} (字段 {len(fields)} 个, 背景 '
          f'{os.path.basename(used_src) if used_src else "自渲染"})')
    return tpl_path
