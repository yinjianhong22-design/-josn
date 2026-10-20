# -*- coding: utf-8 -*-

# ---------------------------------------------------------------------------
# 逐格 OCR (本地 RapidOCR / 转发本地 OCR 服务)
# ---------------------------------------------------------------------------

from ..common import (base64, cv2, json, np, os, urllib,
                       _OCR_TEXT_SCORE)
from .ocr_engine import _make_ocr_engine


def _tight_crop(crop, margin=8):
    """裁掉留白, 只保留内容包围盒(含少量边距)。"""
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    dark = np.column_stack(np.where(gray < 128))
    if dark.size == 0:
        return None
    y0, x0 = dark.min(axis=0)
    y1, x1 = dark.max(axis=0)
    return crop[max(0, y0 - margin):y1 + margin,
                max(0, x0 - margin):x1 + margin]


def _prepare_crop(img, c, inset=4):
    """从原图裁出一个格子: 内缩避开边框, 空格跳过(返回 None),
    极端长宽比补白到不超过 5:1 (否则检测器会退化为整格单行识别)。
    """
    x0, y0 = c['x'] + inset, c['y'] + inset
    x1, y1 = c['x'] + c['w'] - inset, c['y'] + c['h'] - inset
    if x1 <= x0 or y1 <= y0:
        return None
    crop = img[y0:y1, x0:x1]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    if int((gray < 128).sum()) < 30:
        return None  # 深色像素太少, 格内基本没有内容
    ch, cw = crop.shape[:2]
    if cw > ch * 5:
        pad = (cw // 5 - ch) // 2
        crop = cv2.copyMakeBorder(crop, pad, pad, 0, 0,
                                  cv2.BORDER_CONSTANT, value=(255, 255, 255))
    elif ch > cw * 5:
        pad = (ch // 5 - cw) // 2
        crop = cv2.copyMakeBorder(crop, 0, 0, pad, pad,
                                  cv2.BORDER_CONSTANT, value=(255, 255, 255))
    # 小格放大再识别: 检测/识别模型对短边过小的图会系统性误读
    # (实测 "99%" 在 72px 宽格内被读成 "666", 放大到 ~300px 后正确),
    # 只放大不缩小, 放大倍数封顶 4
    ch, cw = crop.shape[:2]
    short = max(ch, cw)
    if short < 300:
        k = min(4, 300 / short)
        crop = cv2.resize(crop, None, fx=k, fy=k,
                          interpolation=cv2.INTER_CUBIC)
    return crop


def _reading_order(res):
    """把 RapidOCR 检测结果还原成按阅读顺序的行文本列表。

    按框中心 y 聚成行 (容差取行高比例, 防同行轻微错位被拆行), 行内按
    中心 x 排序。只按 y 全局排序会把同一行里 y 略有高低差的多个框
    排反 (小格子里符号框与汉字框错位常见), 产生"(%)xxx"这类倒序串行;
    这是通用阅读顺序还原, 不针对特定文字内容。
    """
    items = []
    for box, t, _ in res:
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        items.append({'cx': sum(xs) / 4.0, 'cy': sum(ys) / 4.0,
                      'h': max(ys) - min(ys), 't': t})
    lines = []
    for it in sorted(items, key=lambda d: (d['cy'], d['cx'])):
        for line in lines:
            if abs(line['cy'] - it['cy']) <= max(6.0, line['h'] * 0.7):
                line['items'].append(it)
                n = len(line['items'])
                line['cy'] = (line['cy'] * (n - 1) + it['cy']) / n
                line['h'] = max(line['h'], it['h'])
                break
        else:
            lines.append({'cy': it['cy'], 'h': it['h'], 'items': [it]})
    lines.sort(key=lambda l: l['cy'])
    return [''.join(i['t'] for i in sorted(line['items'],
                                           key=lambda d: d['cx']))
            for line in lines]


def ocr_cells(img, cells, inset=4):
    """逐格 OCR (RapidOCR 本地): 按格子坐标裁出小图单独识别。

    整图一次识别容易在表格场景漏检/串行, 逐格识别区域小、干扰少。
    检测对单字格会漏检, 这种情况退化为"紧贴内容整格识别"。
    返回 {(row,col): 文本}; 未安装 rapidocr-onnxruntime 时返回 None。
    """
    engine = _make_ocr_engine()
    if engine is None:
        return None
    texts = {}
    for c in cells:
        crop = _prepare_crop(img, c, inset)
        if crop is None:
            continue
        try:
            res, _ = engine(crop)
        except Exception:
            res = None
        if res:
            texts[(c['row'], c['col'])] = '\n'.join(_reading_order(res))
            continue
        # 检测漏检 (单字/连体手写等): 紧贴内容, 整格作为一行直接识别
        sub = _tight_crop(crop)
        if sub is None:
            continue
        try:
            rec_res, _ = engine.text_recognizer([sub])
        except Exception:
            continue
        if rec_res and float(rec_res[0][1]) >= _OCR_TEXT_SCORE:
            texts[(c['row'], c['col'])] = rec_res[0][0]
    return texts


def _ocr_cells_remote(img, cells, inset, base_url, timeout=600):
    """把逐格 OCR 批量转发给本地 OCR 服务 (ocr_service.py): 整图编码
    一次, 连同格子坐标列表 POST {base_url}/ocr/cells, 返回 {(row,col): 文本}。

    服务不可达或返回非 2xx 时抛 RuntimeError (含地址与原因), 不静默回退;
    timeout 默认 600s, 大表逐格串行识别耗时较长。
    """
    ok, buf = cv2.imencode('.png', img)
    if not ok:
        raise RuntimeError('OCR 服务调用失败: 整图 PNG 编码失败')
    payload = {
        'image_b64': base64.b64encode(buf.tobytes()).decode('ascii'),
        'cells': [{'row': c['row'], 'col': c['col'], 'x': int(c['x']),
                   'y': int(c['y']), 'w': int(c['w']), 'h': int(c['h'])}
                  for c in cells],
        'inset': inset,
    }
    url = base_url.rstrip('/') + '/ocr/cells'
    req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'),
                                 headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f'OCR 服务返回 {e.code}: {url}') from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise RuntimeError(f'OCR 服务不可达 ({url}): {e}') from e
    return {(int(r['row']), int(r['col'])): r['text']
            for r in body.get('results', [])}


def _pick_ocr_backend(args):
    """OCR 后端: 返回 (名称, (img, cells) -> dict)。

    --ocr-url / 环境变量 OCR_SERVICE_URL 非空 → 批量提交给本地 OCR 服务
    (ocr_service.py), 服务不可达时 _ocr_cells_remote 直接抛错, 不静默回退;
    未配置 → 进程内 RapidOCR 逐格识别 (未安装 rapidocr-onnxruntime 时
    ocr_cells 返回 None, 跳过文字识别只还原结构)。
    """
    base_url = (getattr(args, 'ocr_url', None)
                or os.environ.get('OCR_SERVICE_URL', ''))
    if base_url:
        return ('RapidOCR (服务)',
                lambda img, cells: _ocr_cells_remote(img, cells, 4, base_url))
    return 'RapidOCR (本地)', ocr_cells


def _attach_line_pos(cells, texts):
    """把 OCR 出的每行文字对号到投影切分出的行位置上。

    OCR 逐格返回多行文本但不含坐标; 这里用横向投影的行切分结果
    (cell['text_lines']) 按顺序对位, 供 PDF 还原按行高定字号和位置。
    行数对不上时放弃该格的位置约束, 退回整体自动适配。
    """
    for c in cells:
        t = texts.get((c['row'], c['col']))
        spans = c.get('text_lines') or []
        if not t or len(spans) != len(t.split('\n')):
            continue
        c['lines'] = [{'y': y0, 'h': y1 - y0, 'text': txt}
                      for (y0, y1), txt in zip(spans, t.split('\n'))]
