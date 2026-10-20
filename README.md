# -josn

将 png / Word / Excel / PDF 表单转换成结构化 JSON，并用"背景图 + 字段覆盖层"方案在浏览器里复现原表。

## 流水线

```
图片/PDF/Word/Excel
  → Office 排版引擎落成 PDF (冻结打印版式, WPS/Office 不可用时回退 python-docx/openpyxl)
  → pymupdf 提取矢量表格和坐标 (OpenCV 兜底扫描件, OCR 补文字)
  → openpyxl 语义对齐 (格子/游离文字赋稳定地址 Sheet!A1)
  → fields 配对 / form 视图 / index 索引
  → 输出目录落盘
```

## 命令行转换

```bash
.venv/Scripts/python.exe extract_grid.py 1.xlsx -o grid_out
```

输出目录产物：

- `form.json` —— 完整 JSON，权威产物。含 `cells`（几何+文字）、`fields`/`table_fields`（字段配对）、`form`（可索引视图）、`index`（回填索引：`by_label` + `header_fields` 上下文区 + `rows` 数据区 + `cells` + `report`）
- `template.json` —— 前端 Template 结构（`pages[].background` 背景图 + `fields[]` 覆盖层，`fieldUuid` 与 `index.cells` 的 uuid 一致）
- `background.png` —— 原样 PDF 按 2px/pt 栅格化的背景图
- `data.json` / `data.js` / `index.html` —— 纯渲染层（file:// 直接打开 index.html 可看还原效果）
- `rebuilt.pdf` / `1_office.pdf` —— 还原 PDF 与排版引擎原样 PDF

## OCR 服务（可选）

把 RapidOCR 包成本地 HTTP 服务，模型常驻内存，`extract_grid.py` 的逐格 OCR 不再进程内加载模型：

```bash
.venv/Scripts/python.exe ocr_service.py            # 默认 127.0.0.1:8100
.venv/Scripts/python.exe extract_grid.py scan.png --ocr-url http://127.0.0.1:8100 -o grid_out
```

- 不传 `--ocr-url`（且环境变量 `OCR_SERVICE_URL` 为空）时保持进程内识别，行为不变
- 设置了服务地址但服务不可达：直接报错，不静默回退
- 接口：`POST /ocr/cells`，请求整图 PNG(base64) + 格子坐标列表批量提交，响应只含有文字的格子；裁剪/漏检兜底逻辑与本地路径一致
- 引擎自动探测 GPU：装 `onnxruntime-gpu`（+ nvidia cu12 运行库 pip 包）时三模型全部上 CUDA，初始化失败自动回退 CPU 并打印提示

## 模板服务（前后端联调）

```bash
.venv/Scripts/python.exe server.py            # 默认 127.0.0.1:8000
```

- 静态托管 Vue 前端（`frontend/frontend/dist`）与 `/files`（项目根，背景图等）
- `GET /templates` 模板库（扫描项目下所有 `template.json`）
- `GET /templates/{id}` 加载模板（背景相对路径自动改写为 `/files/...`）
- `POST /templates/{id}/save` 保存前端编辑
- `POST /upload` 上传 xlsx/docx/pdf，跑转换管线，返回 Template JSON

前端开发模式（热更新，接口指向本服务）：

```bash
cd frontend/frontend
npm run dev   # 如需非默认端口: VITE_API_BASE_URL=http://127.0.0.1:8017 npm run dev
```

前端构建：`cd frontend/frontend && npm run build`（Windows 上若遇 Node 堆内存崩溃，加 `NODE_OPTIONS=--max-old-space-size=4096`）。

## 前端复现方式

不是从头渲染文档，而是两层混合（`frontend/frontend/src/components/TemplatePage.vue`）：

- 底层：原页栅格图 `<img :src="imageUrl(page.background)">`，即 `background.png`，"原样张"由它保证
- 上层：每个 field 按 `rect`（占页宽高的比例坐标）绝对定位，应用 `style`（字号/对齐等），带 `textOverride` 的格以白底覆盖层重画文字

`frontend/frontend/src/types/template.ts` 是 `template.json` 的 TypeScript 镜像，`api/template.ts` 与 `server.py` 接口一一对应。

## 回填索引（form.json 的 index）

表头行（含"规定值"类列名的行）为分界线，构建时自动识别：

- 表头行以上 → `header_fields`：上下文区 label 格配同排右侧值格，目录 context 纯字典查找填充
- 表头行以下 → `rows`：数据区按行还原 字段→规定值/实测值/合格率，数据简表按 行标签+列名 填充
- 全表 → `by_label`：所有带 label 的字段（兜底和通用查找）

填充语义（`index.cells[uuid].mode`）：`overwrite` 空格直写 / `replace` 整格替换（占位文字视为示例值）/ `append` 值插在占位（标签）之后 / `inline` 替换占位文本片段（同行冒号内联）。占位文本、缺列等边界情况全部进 `index.report`。
