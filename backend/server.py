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
    .venv/Scripts/python.exe backend/server.py [--root .] [--port 8000]
前端开发模式:
    cd frontend/frontend && npm run dev   # 已配 VITE_API_BASE_URL 时直连本服务

本文件位于 backend/, 项目根目录取其上一级; 脚本入口需把项目根加进
sys.path 才能 import backend 包。
"""
import argparse
import json
import os
import sys
import threading
import time

# 项目根目录 (backend/ 的上一级), --root 默认值与 _uploads/out/dist 定位基准
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# 转换管线公开函数 (叶子模块直取, 不经根目录兼容 shim)
from backend.template_pipeline.office_fb.render import render_data_background
from backend.template_pipeline.office_fb.xlsx_reader import xlsx_to_data
from backend.template_pipeline.output.frontend import generate_frontend
from backend.template_pipeline.output.template import build_template
from backend.template_pipeline.pipeline.document import convert_document
from backend.template_pipeline.pipeline.page import extract_page
from backend.template_pipeline.semantic.fields import extract_fields
from backend.template_pipeline.semantic.index import build_index
from backend.template_pipeline.semantic.match import match_data_fields
from backend.template_pipeline.semantic.roles import assign_roles
from backend.template_pipeline.semantic.sheet_input import (
    parse_data_sheet, photo_to_sheet)

# 扫描模板时跳过依赖、缓存与非模板生成目录 (与 .gitignore 对齐)
_SKIP_DIRS = {'.git', '.venv', 'node_modules', '_tmp_form', '_uploads',
              '_sandbox', 'dist', '__pycache__'}
_IMG_EXT = ('.png', '.jpg', '.jpeg', '.bmp', '.webp')
_EXT_OK = ('.xlsx', '.docx', '.pdf') + _IMG_EXT
_SCAN_TTL = 2.0
_DELETE_MARKER = '.template_deleted'

_registry = {}  # templateUuid -> template.json 绝对路径
_registry_lock = threading.RLock()
_registry_scanned_at = 0.0


def _index_score(template_path):
    """同 UUID 多份产物的回填可用性：数据行、上下文字段、通用标签。"""
    try:
        with open(os.path.join(os.path.dirname(template_path), 'form.json'),
                  encoding='utf-8') as f:
            index = json.load(f).get('index') or {}
        return (len(index.get('rows') or []),
                len(index.get('header_fields') or {}),
                len(index.get('by_label') or {}))
    except Exception:
        return (0, 0, 0)


def scan_templates(root):
    """按短 TTL 扫描模板, 构建完整新注册表后一次性替换。"""
    global _registry, _registry_scanned_at
    with _registry_lock:
        now = time.monotonic()
        if now - _registry_scanned_at < _SCAN_TTL:
            return
        new_registry = {}
        new_scores = {}
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames
                           if d not in _SKIP_DIRS and not d.startswith('.')]
            if 'template.json' not in filenames \
                    or _DELETE_MARKER in filenames:
                continue
            path = os.path.join(dirpath, 'template.json')
            try:
                with open(path, encoding='utf-8') as f:
                    tpl = json.load(f)
                tid = tpl['templateUuid']
                # 空壳 index 与完整索引不能同权：比较可用条目数，
                # 同 UUID 的多份产物中保留回填信息最完整的一份。
                score = _index_score(path)
                if tid not in new_registry or score > new_scores[tid]:
                    new_registry[tid] = path
                    new_scores[tid] = score
            except Exception as e:
                print(f'[scan] 跳过 {path}: {e}')
        _registry = new_registry
        _registry_scanned_at = time.monotonic()


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
    """与 main() 默认参数一致的 Namespace。"""
    import argparse
    return argparse.Namespace(
        page=0, dpi=300, h_ratio=0.1, v_ratio=0.03, h_min_span=0.28,
        v_min_span=0.04, h_span_ratio=0.45, v_span_ratio=0.20,
        no_ocr=False, force_ocr=False,
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


def _safe_upload_name(filename):
    """返回不含路径信息的 (stem, 小写扩展名), 非法文件名直接拒绝。"""
    from fastapi import HTTPException
    raw = filename or ''
    if ('/' in raw or '\\' in raw or '..' in raw
            or any(ord(c) < 32 or c in '<>:"|?*' for c in raw)):
        raise HTTPException(400, '文件名包含路径分隔符、.. 或非法字符')
    stem, ext = os.path.splitext(os.path.basename(raw))
    stem = stem.strip()
    reserved = {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)),
                *(f'LPT{i}' for i in range(1, 10))}
    if stem.upper() in reserved or stem.endswith(('.', ' ')):
        raise HTTPException(400, '文件名不是合法的 Windows 文件名')
    return stem or 'upload', ext.lower()


def _remove_file(path):
    try:
        if path and os.path.isfile(path):
            os.remove(path)
    except OSError:
        pass


def _parse_sheet_file(tmp, ext):
    """在线程池中解析已暂存的数据简表。"""
    from fastapi import HTTPException
    if ext == '.xlsx':
        sheet = parse_data_sheet(tmp)
        empty_hint = ''
    else:
        data = extract_page(tmp, 0, _convert_args())
        if not data or not data.get('cells'):
            raise HTTPException(400, '照片中未检测到表格, 请拍正拍清晰后重试')
        assign_roles(data)
        extract_fields(data)
        build_index(data)
        sheet = photo_to_sheet(data)
        print(f"[match-sheet] 照片简表: title={sheet['title']} "
              f"fields={len(sheet['fields'])}")
        empty_hint = ('; 照片识别率有限, 若简表本身是 Excel, '
                      '建议直接上传 .xlsx 文件而非截图/照片')
    if not sheet['fields']:
        raise HTTPException(400,
                            '未能从简表解析出字段 '
                            '(需要 项目/规定值/实测值 类表头)' + empty_hint)
    return sheet


async def _parse_sheet_upload(file, upload_dir):
    """校验并暂存数据简表, 在线程池解析, 返回 (sheet, 暂存路径)。"""
    import uuid
    from fastapi import HTTPException
    from fastapi.concurrency import run_in_threadpool
    _, ext = _safe_upload_name(file.filename)
    if ext not in ('.xlsx',) + _IMG_EXT:
        raise HTTPException(400, '仅支持 .xlsx 数据简表或已填表照片')
    os.makedirs(upload_dir, exist_ok=True)
    tmp = os.path.join(upload_dir, f'sheet_{uuid.uuid4().hex}{ext}')
    try:
        with open(tmp, 'wb') as f:
            f.write(await file.read())
        sheet = await run_in_threadpool(_parse_sheet_file, tmp, ext)
        return sheet, tmp
    except Exception:
        _remove_file(tmp)
        raise


def _sheet_preview_url(path, upload_dir):
    """给上传的数据简表生成左侧预览图, 返回 /files/... URL 或 None。

    图片直接复用; xlsx 由 office_fb 简化排版自渲染成 PNG (缩到 1400 宽)。
    按内容哈希缓存, 重复匹配不重复转换。失败静默返回 None (前端回退到
    模板原图)。"""
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
                data = xlsx_to_data(path)
                img = render_data_background(data)
                w = 1400
                if img.width > w:
                    img = img.resize((w, round(img.height * w / img.width)))
                img.save(dst)
        rel = os.path.relpath(dst, os.path.dirname(upload_dir)) \
            .replace(os.sep, '/')
        return '/files/' + rel
    except Exception as e:
        print(f'[sheet-preview] 生成失败: {e}')
        return None


def convert_upload(src_path, stem, root, out_base):
    """跑转换管线, 以源内容哈希重算 UUID; 失败时清理半成品目录。"""
    import hashlib
    import shutil
    import uuid
    out_dir = os.path.join(out_base, f'{stem}_{uuid.uuid4().hex[:6]}')
    os.makedirs(out_dir, exist_ok=True)
    try:
        args = _convert_args()
        args.input = src_path
        args.out = out_dir
        ext = os.path.splitext(src_path)[1].lower()
        bg_url = '/files/' + os.path.relpath(out_dir, root) \
            .replace(os.sep, '/') + '/background.png'
        if ext in ('.xlsx', '.docx'):
            data, office_pdf = convert_document(
                src_path, out_dir, args)
            build_template(
                data, out_dir, source_paths=[office_pdf] if office_pdf else [],
                name=stem, bg_url=bg_url,
                source_ext=None if office_pdf else ext)
        else:  # pdf / 图片: PDF 走文字层直提, 图片(扫描件)走 OCR 识别算法
            if ext != '.pdf' and ext not in _IMG_EXT:
                raise RuntimeError(
                    f'不支持的文件格式: {ext} (仅支持 pdf / 图片 / .docx / .xlsx)')
            data = extract_page(src_path, args.page, args)
            if not data:
                raise RuntimeError('页面提取失败')
            generate_frontend(data, out_dir)
            build_template(data, out_dir, source_paths=[src_path],
                           name=stem, bg_url=bg_url)
        template_path = os.path.join(out_dir, 'template.json')
        with open(template_path, encoding='utf-8') as f:
            tpl = json.load(f)
        digest = hashlib.sha256()
        with open(src_path, 'rb') as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b''):
                digest.update(chunk)
        old_tid = tpl.get('templateUuid')
        tpl['templateUuid'] = str(uuid.uuid5(
            uuid.NAMESPACE_URL, f'{digest.hexdigest()}\0{stem}'))
        tmp_path = template_path + '.tmp'
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(tpl, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, template_path)
        with _registry_lock:
            if old_tid and _registry.get(old_tid) == template_path:
                _registry.pop(old_tid, None)
            tid = tpl['templateUuid']
            registered = _registry.get(tid)
            if registered is None or not os.path.isfile(registered) \
                    or _index_score(template_path) > _index_score(registered):
                _registry[tid] = template_path
        return tpl
    except Exception:
        shutil.rmtree(out_dir, ignore_errors=True)
        raise


def create_app(root=ROOT):
    from fastapi import FastAPI, File, HTTPException, Request, UploadFile
    from fastapi.concurrency import run_in_threadpool
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import FileResponse, JSONResponse
    from fastapi.staticfiles import StaticFiles

    root = os.path.abspath(root)
    dist = os.path.join(root, 'frontend', 'frontend', 'dist')
    upload_dir = os.path.join(root, '_uploads')
    out_base = os.path.join(root, 'out')

    app = FastAPI(title='表单模板服务')
    app.add_middleware(CORSMiddleware, allow_origins=['*'],
                       allow_methods=['*'], allow_headers=['*'])

    @app.middleware('http')
    async def protect_files(request: Request, call_next):
        """静态目录仅放行普通产物, 拒绝敏感目录、点文件与路径穿越。"""
        path = request.url.path
        if path == '/files' or path.startswith('/files/'):
            parts = path.replace('\\', '/').split('/')[2:]
            # _uploads 虽不参与模板扫描, 但简表预览图需要正常访问。
            denied = {d.casefold() for d in (_SKIP_DIRS - {'_uploads'}) | {'deploy'}}
            if any(p.startswith('.') or p.casefold() in denied for p in parts):
                return JSONResponse({'detail': '禁止访问该路径'}, status_code=403)
        return await call_next(request)

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
    def save_template(tid: str, body: dict):
        scan_templates(root)
        path = _registry.get(tid)
        if not path:
            raise HTTPException(404, '模板不存在')
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(body, f, ensure_ascii=False, indent=2)
        return {'ok': True}

    @app.delete('/templates/{tid}')
    def delete_template(tid: str):
        import shutil
        scan_templates(root)
        path = _registry.get(tid)
        if not path:
            raise HTTPException(404, '模板不存在')
        template_dir = os.path.realpath(os.path.dirname(path))
        managed = False
        for base in (os.path.join(root, 'out'), os.path.join(root, 'grid_out')):
            base = os.path.realpath(base)
            try:
                managed |= template_dir != base and os.path.commonpath(
                    (template_dir, base)) == base
            except ValueError:
                pass
        if managed:
            shutil.rmtree(os.path.dirname(path))
        else:
            # 非托管目录不能整删; 留删除标记, 避免外部再生成 JSON 后复活。
            with open(os.path.join(os.path.dirname(path), _DELETE_MARKER), 'w'):
                pass
            if os.path.exists(path):
                os.remove(path)
        with _registry_lock:
            if _registry.get(tid) == path:
                _registry.pop(tid, None)
        return {'ok': True}

    @app.post('/templates/{tid}/match-sheet')
    async def match_sheet(tid: str, file: UploadFile = File(...)):
        """上传数据简表 (xlsx), 解析成一次性 JSON 并按指定模板索引匹配,
        返回 {title, fields, values: {fieldUuid: 值}, unmatched}。
        简表暂存文件在响应前清理, 内容哈希预览图可保留。"""
        tmp = None
        try:
            await run_in_threadpool(scan_templates, root)
            path = _registry.get(tid)
            if not path:
                raise HTTPException(404, '模板不存在')
            sheet, tmp = await _parse_sheet_upload(file, upload_dir)
            with open(os.path.join(os.path.dirname(path), 'form.json'),
                      encoding='utf-8') as f:
                index = (json.load(f).get('index')) or {}
            res = await run_in_threadpool(match_data_fields, sheet, index)
            print(f"[match-sheet] title={sheet['title']} "
                  f"fields={len(sheet['fields'])} "
                  f"命中={len(res['values'])} 未匹配={res['unmatched']}")
            preview = await run_in_threadpool(
                _sheet_preview_url, tmp, upload_dir)
            return {**sheet, **res, 'sheetImage': preview}
        finally:
            _remove_file(tmp)

    @app.post('/match-sheet')
    async def match_sheet_auto(file: UploadFile = File(...)):
        """上传数据简表: 解析后按 表名/编号 自动路由模板库并匹配回填,
        返回 {templateUuid, title, context, fields, values, unmatched}。"""
        tmp = None
        try:
            sheet, tmp = await _parse_sheet_upload(file, upload_dir)
            await run_in_threadpool(scan_templates, root)
            routed = await run_in_threadpool(_route_template, sheet)
            if not routed or routed[1] <= 0:
                raise HTTPException(
                    404, f"没有匹配到模板 (简表表名: {sheet['title'] or '未识别'}, "
                         f"请先在模板库制作/上传对应模板表)")
            tid = routed[0]
            with open(os.path.join(os.path.dirname(_registry[tid]), 'form.json'),
                      encoding='utf-8') as f:
                index = (json.load(f).get('index')) or {}
            res = await run_in_threadpool(match_data_fields, sheet, index)
            print(f"[match-sheet:auto] title={sheet['title']} -> {tid} "
                  f"score={routed[1]} 命中={len(res['values'])} "
                  f"未匹配={res['unmatched']}")
            preview = await run_in_threadpool(
                _sheet_preview_url, tmp, upload_dir)
            return {'templateUuid': tid, **sheet, **res, 'sheetImage': preview}
        finally:
            _remove_file(tmp)

    @app.post('/upload')
    async def upload(file: UploadFile = File(...)):
        import uuid
        stem, ext = _safe_upload_name(file.filename)
        if ext not in _EXT_OK:
            raise HTTPException(400, f'仅支持 {"/".join(_EXT_OK)}')
        os.makedirs(upload_dir, exist_ok=True)
        safe = os.path.join(upload_dir, f'{stem}_{uuid.uuid4().hex}{ext}')
        try:
            with open(safe, 'wb') as f:
                f.write(await file.read())
            tpl = await run_in_threadpool(
                convert_upload, safe, stem, root, out_base)
            return {'template': tpl}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(500, f'转换失败: {e}')
        finally:
            _remove_file(safe)

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
    # Windows 控制台/重定向默认 GBK, 管线打印可能含 GBK 无法编码的字符
    # (如排版引擎文字层解析出的 ¼ 类符号), 打印抛 UnicodeEncodeError 会把
    # 整个 /upload 请求打挂; 重配 stdout/stderr 为 UTF-8 容错输出
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding='utf-8', errors='backslashreplace')
        except Exception:
            pass
    print(f'表单模板服务: http://{cli.host}:{cli.port}')
    print(f'项目根: {os.path.abspath(cli.root)}')
    print('前端开发: cd frontend/frontend && npm run dev')
    uvicorn.run(app, host=cli.host, port=cli.port)
