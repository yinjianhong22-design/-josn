"""表单模板服务: Vue 前端 (frontend/frontend/dist) + 转换管线的对接后端。

接口与 frontend/src/api/template.ts 一一对应:
    GET  /templates                 模板库列表 (扫描 root 下所有 template.json)
    GET  /templates/{id}            加载模板 -> {template: Template}
    POST /templates/{id}/save       保存前端编辑后的 Template JSON
    DELETE /templates/{id}          删除模板文件
    POST /upload                    上传 xlsx/docx/pdf, 跑转换管线, 返回模板
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
            _registry[tpl['templateUuid']] = path
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
