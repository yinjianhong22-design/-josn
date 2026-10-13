"""表单模板服务: Vue 前端 (frontend/frontend/dist) + 转换管线的对接后端。

接口与 frontend/src/api/template.ts 一一对应:
    GET  /templates                 模板库列表 (扫描 root 下所有 template.json)
    GET  /templates/{id}            加载模板 -> {template: Template}
    POST /templates/{id}/save       保存前端编辑后的 Template JSON
    DELETE /templates/{id}          删除模板文件
    POST /upload                    上传 xlsx/docx/pdf, 跑转换管线, 返回模板
    POST /match-sheet               上传数据简表, 按 表名/编号 自动路由模板
                                    并匹配回填, 返回 templateUuid + values
静态:
    /        Vue 前端 (dist/, 未构建时提示)
    /files/  项目根目录 (转换输出目录的背景图等, template.json 里的
             page.background 相对路径在加载时改写为 /files/...)

用法:
    .venv/Scripts/python.exe server.py [--root .] [--port 8000]
前端开发模式:
    cd frontend/frontend && npm run dev   # 已配 VITE_API_BASE_URL 时直连本服务
"""
import argparse
import json
import os

ROOT = os.path.dirname(os.path.abspath(__file__))

# 扫描模板时跳过的目录
_SKIP_DIRS = {'.git', '.venv', 'node_modules', '_tmp_form', '_uploads',
              'dist', '__pycache__'}
_EXT_OK = ('.xlsx', '.xls', '.docx', '.doc', '.pdf',
           '.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff', '.webp')

_registry = {}  # templateUuid -> template.json 绝对路径


def scan_templates(root):
    """扫描 root 下所有 template.json, 重建 uuid -> 路径注册表。"""
    _registry.clear()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames
                       if d not in _SKIP_DIRS and not d.startswith('.')]
        if 'template.json' not in filenames:
            continue
        path = os.path.join(dirpath, 'template.json')
        try:
            with open(path, encoding='utf-8') as f:
                tpl = json.load(f)
            tid = tpl['templateUuid']
            if tid in _registry:
                # 同名模板多处产出 (CLI grid_out 与服务端 out/), 优先保留
                # form.json 带 index 的 (回填能力完整)
                def has_index(p):
                    try:
                        with open(os.path.join(os.path.dirname(p),
                                               'form.json'),
                                  encoding='utf-8') as f:
                            return bool(json.load(f).get('index'))
                    except Exception:
                        return False
                if not has_index(_registry[tid]) and has_index(path):
                    _registry[tid] = path
            else:
                _registry[tid] = path
        except Exception as e:
            print(f'[scan] 跳过 {path}: {e}')


def bg_to_url(tpl, path, root):
    """page.background 相对路径改写为 /files/... 服务地址。"""
    base = '/files/' + os.path.dirname(os.path.relpath(path, root)) \
        .replace(os.sep, '/')
    for page in tpl.get('pages') or []:
        bg = page.get('background') or ''
        if bg and not bg.startswith('/') and not bg.startswith('http'):
            page['background'] = base + '/' + bg
    return tpl


def _convert_args():
    """与 extract_grid.main() 默认参数一致的 Namespace。"""
    import argparse
    return argparse.Namespace(
        page=0, dpi=300, h_ratio=0.1, v_ratio=0.03, h_min_span=0.28,
        v_min_span=0.04, no_ocr=False, force_ocr=False, no_office=False,
        out=None, input=None, h_ratio_set=None)


def _route_template(sheet):
    """按 表名/编号 给注册表里的模板打分, 返回 (tid, score) 最高者。

    表名完全相等 +10 / 互相包含 +5; 编号 (从 '编 号:JB12-4.5.2-4'
    类文本提取代码) 相等 +10 / 前缀家族 +3。编号在数据简表上是逐记录
    流水, 与模板印刷编号不一定全等, 所以表名是主键、编号是辅键。"""
    import re

    def norm(s):
        s = str(s or '').translate({ord('（'): '(', ord('）'): ')'})
        return re.sub(r'\s+', '', s)

    def code_of(text):
        m = re.search(r'编号\s*[::]\s*([A-Za-z0-9]+(?:[-.][A-Za-z0-9]+)*)',
                      str(text or ''))
        return m.group(1) if m else None

    title = norm(sheet.get('title'))
    sheet_code = code_of((sheet.get('context') or {}).get('编号'))
    best = None
    for tid, path in _registry.items():
        try:
            with open(os.path.join(os.path.dirname(path), 'form.json'),
                      encoding='utf-8') as f:
                form = json.load(f)
        except Exception:
            continue
        score = 0
        t_title = norm((form.get('form') or {}).get('meta', {}).get('title'))
        if title and t_title:
            if title == t_title:
                score += 10
            elif len(title) >= 4 and (title in t_title or t_title in title):
                score += 5
        if sheet_code:
            idx = form.get('index') or {}
            hf = idx.get('header_fields') or {}
            num_u = hf.get('编号')
            num_u = num_u.get('cell') if isinstance(num_u, dict) else num_u
            t_code = code_of(((idx.get('cells') or {}).get(num_u) or {})
                             .get('text'))
            if t_code:
                if norm(sheet_code) == norm(t_code):
                    score += 10
                elif t_code.startswith(sheet_code) \
                        or sheet_code.startswith(t_code):
                    score += 3
        if best is None or score > best[1]:
            best = (tid, score)
    return best


async def _parse_sheet_upload(file, upload_dir):
    """校验/暂存/解析数据简表上传, 返回 (sheet, 暂存路径)。

    暂存文件保留 (前端左侧画板要拿它生成预览图)。"""
    from fastapi import HTTPException
    import extract_grid
    stem, ext = os.path.splitext(file.filename or '')
    if ext.lower() not in ('.xlsx', '.xls'):
        raise HTTPException(400, '仅支持 .xlsx/.xls 数据简表')
    os.makedirs(upload_dir, exist_ok=True)
    tmp = os.path.join(upload_dir, f'sheet_{os.getpid()}{ext}')
    with open(tmp, 'wb') as f:
        f.write(await file.read())
    sheet = extract_grid.parse_data_sheet(tmp)
    if not sheet['fields']:
        raise HTTPException(400,
                            '未能从简表解析出字段 '
                            '(需要 项目/规定值/实测值 类表头)')
    return sheet, tmp


_IMG_EXT = ('.png', '.jpg', '.jpeg', '.bmp', '.webp')


def _sheet_preview_url(path, upload_dir):
    """给上传的数据简表生成左侧预览图, 返回 /files/... URL 或 None。

    图片直接复用; xlsx 走 WPS->PDF->PNG。按内容哈希缓存, 重复匹配不重复
    转换。失败静默返回 None (前端回退到模板原图)。"""
    import hashlib
    ext = os.path.splitext(path)[1].lower()
    try:
        digest = hashlib.md5(open(path, 'rb').read()).hexdigest()[:8]
        if ext in _IMG_EXT:
            dst = os.path.join(upload_dir, f'sheet_preview_{digest}{ext}')
            if not os.path.exists(dst):
                import shutil
                shutil.copy(path, dst)
        else:
            dst = os.path.join(upload_dir, f'sheet_preview_{digest}.png')
            if not os.path.exists(dst):
                import extract_grid
                pdf = extract_grid.office_to_pdf(path, upload_dir)
                if not pdf:
                    return None
                fitz = extract_grid._import_pymupdf()
                doc = fitz.open(pdf)
                page = doc[0]
                zoom = 1400 / max(page.rect.width, 1)
                pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
                pix.save(dst)
                doc.close()
                os.remove(pdf)
        rel = os.path.relpath(dst, os.path.dirname(upload_dir)) \
            .replace(os.sep, '/')
        return '/files/' + rel
    except Exception as e:
        print(f'[sheet-preview] 生成失败: {e}')
        return None


def convert_upload(src_path, stem, root, out_base):
    """跑转换管线, 返回 template_dict。失败抛异常。"""
    import uuid
    import extract_grid
    out_dir = os.path.join(out_base, f'{stem}_{uuid.uuid4().hex[:6]}')
    os.makedirs(out_dir, exist_ok=True)
    args = _convert_args()
    args.input = src_path
    args.out = out_dir
    ext = os.path.splitext(src_path)[1].lower()
    bg_url = '/files/' + os.path.relpath(out_dir, root) \
        .replace(os.sep, '/') + '/background.png'
    if ext in ('.xlsx', '.xls', '.docx', '.doc'):
        data, office_pdf, pdf_path = extract_grid.convert_document(
            src_path, out_dir, args)
        extract_grid.build_template(data, out_dir,
                                    source_paths=[office_pdf],
                                    fallback_pdf=pdf_path, name=stem,
                                    bg_url=bg_url)
    else:  # pdf / 图片: PDF 走文字层直提, 图片(扫描件)走 OCR 识别算法
        data = extract_grid.extract_page(src_path, args.page, args)
        if not data:
            raise RuntimeError('页面提取失败')
        extract_grid.generate_frontend(data, out_dir)
        pdf_path = extract_grid.json_to_pdf(
            data, os.path.join(out_dir, 'rebuilt.pdf'))
        extract_grid.build_template(data, out_dir, source_paths=[src_path],
                                    fallback_pdf=pdf_path, name=stem,
                                    bg_url=bg_url)
    with open(os.path.join(out_dir, 'template.json'), encoding='utf-8') as f:
        tpl = json.load(f)
    _registry[tpl['templateUuid']] = os.path.join(out_dir, 'template.json')
    return tpl


def create_app(root=ROOT):
    from fastapi import FastAPI, File, HTTPException, UploadFile
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    dist = os.path.join(root, 'frontend', 'frontend', 'dist')
    upload_dir = os.path.join(root, '_uploads')
    out_base = os.path.join(root, 'out')

    app = FastAPI(title='表单模板服务')
    app.add_middleware(CORSMiddleware, allow_origins=['*'],
                       allow_methods=['*'], allow_headers=['*'])

    @app.get('/templates')
    def list_templates():
        scan_templates(root)
        summaries = []
        for tid, path in _registry.items():
            try:
                with open(path, encoding='utf-8') as f:
                    tpl = json.load(f)
                summaries.append({
                    'templateUuid': tid,
                    'name': tpl.get('name'),
                    'sourceFormat': tpl.get('sourceFormat'),
                    'pageCount': len(tpl.get('pages') or []),
                })
            except Exception:
                continue
        return summaries

    @app.get('/templates/{tid}')
    def load_template(tid: str):
        scan_templates(root)
        path = _registry.get(tid)
        if not path:
            raise HTTPException(404, '模板不存在')
        with open(path, encoding='utf-8') as f:
            return {'template': bg_to_url(json.load(f), path, root)}

    @app.post('/templates/{tid}/save')
    async def save_template(tid: str, body: dict):
        scan_templates(root)
        path = _registry.get(tid)
        if not path:
            raise HTTPException(404, '模板不存在')
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(body, f, ensure_ascii=False, indent=2)
        return {'ok': True}

    @app.delete('/templates/{tid}')
    def delete_template(tid: str):
        scan_templates(root)
        path = _registry.pop(tid, None)
        if not path:
            raise HTTPException(404, '模板不存在')
        if os.path.exists(path):
            os.remove(path)
        return {'ok': True}

    @app.post('/templates/{tid}/match-sheet')
    async def match_sheet(tid: str, file: UploadFile = File(...)):
        """上传数据简表 (xlsx), 解析成一次性 JSON 并按指定模板索引匹配,
        返回 {title, fields, values: {fieldUuid: 值}, unmatched}。
        简表解析结果不落盘, 用完即弃。"""
        import extract_grid
        scan_templates(root)
        path = _registry.get(tid)
        if not path:
            raise HTTPException(404, '模板不存在')
        sheet, tmp = await _parse_sheet_upload(file, upload_dir)
        with open(os.path.join(os.path.dirname(path), 'form.json'),
                  encoding='utf-8') as f:
            index = (json.load(f).get('index')) or {}
        res = extract_grid.match_data_fields(sheet, index)
        print(f"[match-sheet] title={sheet['title']} "
              f"fields={len(sheet['fields'])} "
              f"命中={len(res['values'])} 未匹配={res['unmatched']}")
        return {**sheet, **res,
                'sheetImage': _sheet_preview_url(tmp, upload_dir)}

    @app.post('/match-sheet')
    async def match_sheet_auto(file: UploadFile = File(...)):
        """上传数据简表: 解析后按 表名/编号 自动路由模板库并匹配回填,
        返回 {templateUuid, title, context, fields, values, unmatched}。"""
        import extract_grid
        sheet, tmp = await _parse_sheet_upload(file, upload_dir)
        scan_templates(root)
        routed = _route_template(sheet)
        if not routed or routed[1] <= 0:
            raise HTTPException(
                404, f"没有匹配到模板 (简表表名: {sheet['title'] or '未识别'}, "
                     f"请先在模板库制作/上传对应模板表)")
        tid = routed[0]
        with open(os.path.join(os.path.dirname(_registry[tid]), 'form.json'),
                  encoding='utf-8') as f:
            index = (json.load(f).get('index')) or {}
        res = extract_grid.match_data_fields(sheet, index)
        print(f"[match-sheet:auto] title={sheet['title']} -> {tid} "
              f"score={routed[1]} 命中={len(res['values'])} "
              f"未匹配={res['unmatched']}")
        return {'templateUuid': tid, **sheet, **res,
                'sheetImage': _sheet_preview_url(tmp, upload_dir)}

    @app.post('/upload')
    async def upload(file: UploadFile = File(...)):
        stem, ext = os.path.splitext(file.filename or '')
        ext = ext.lower()
        if ext not in _EXT_OK:
            raise HTTPException(400, f'仅支持 {"/".join(_EXT_OK)}')
        stem = stem or 'upload'
        os.makedirs(upload_dir, exist_ok=True)
        safe = os.path.join(upload_dir, f'{stem}_{os.getpid()}{ext}')
        with open(safe, 'wb') as f:
            f.write(await file.read())
        try:
            return {'template': convert_upload(safe, stem, root, out_base)}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, f'转换失败: {e}')

    # /files: 项目根 (转换输出目录的背景图等)
    app.mount('/files', StaticFiles(directory=root), name='files')

    # Vue 前端 SPA (dist 不存在时给出提示)
    @app.get('/{full_path:path}')
    def spa(full_path: str):
        candidate = os.path.join(dist, full_path)
        if full_path and os.path.isfile(candidate):
            return FileResponse(candidate)
        index = os.path.join(dist, 'index.html')
        if os.path.isfile(index):
            return FileResponse(index)
        raise HTTPException(
            404, '前端未构建: 先运行 cd frontend/frontend && npm run build')

    return app


app = create_app()

if __name__ == '__main__':
    ap = argparse.ArgumentParser(description='表单模板服务')
    ap.add_argument('--root', default=ROOT, help='项目根目录 (默认脚本所在)')
    ap.add_argument('--host', default='127.0.0.1')
    ap.add_argument('--port', type=int, default=8000)
    cli = ap.parse_args()
    app = create_app(os.path.abspath(cli.root))
    import uvicorn
    print(f'表单模板服务: http://{cli.host}:{cli.port}')
    print(f'项目根: {os.path.abspath(cli.root)}')
    print('前端开发: cd frontend/frontend && npm run dev')
    uvicorn.run(app, host=cli.host, port=cli.port)
