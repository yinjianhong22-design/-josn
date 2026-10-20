# AGENTS.md

面向 AI 编码代理的项目说明。读完本文件应能独立完成常见改动。

## 项目概述

把 png / Word / Excel / PDF 表单转换成结构化 JSON，并用"背景图 + 字段覆盖层"方案在浏览器里复现原表，支持按数据简表自动回填字段、重新出 PDF。

核心思想：**版式与数据分离**。模板制作阶段把表单定格成"背景图 + 字段覆盖层 + 可索引 JSON"（一次性）；填数阶段只做字典查找并写入字段的 `textOverride`，不碰版式。

权威文档：`README.md`（用法与产物清单）、`技术方案.md`（架构、启发式规则细节、通用性边界）。两者与本文件冲突时以代码实际行为为准，并及时更新。

## 技术栈与目录结构

后端/管线（Python 3.14，虚拟环境 `.venv/`）：

- `extract_grid.py`（兼容 shim，不再含实现）：全部转换逻辑已迁至 `backend/template_pipeline/` 包，本文件仅 re-export 公开函数及 `server.py` / `ocr_service.py` 依赖的私有名字（`_import_pymupdf` / `_make_ocr_engine` / `_prepare_crop` / `_tight_crop` / `_reading_order` / `_OCR_TEXT_SCORE`），并保留 `main()` 入口。包内按流水线层级组织（依赖只允许下游 import 上游；跨子包引用统一在模块顶部用 `importlib.import_module('..x.y', __package__)` 取别名，函数体调用点不变）：
  - `common.py`：顶层 import、跨模块常量（`_OCR_TEXT_SCORE` / `_NO_LABEL_PREFIX` / `_IMG_EXT` / `_jsonable`）、`_import_pymupdf()`
  - `input/`：输入加载（`load_image`）、Office 转 PDF（`office_to_pdf`）、`detect_input_type`
  - `layout/`：像素/矢量线提取与合并（`binarize` … `merge_line_sources`）、交点格子（`find_cells`）、版面分析、诊断落盘（`dump_lines_json`）
  - `text/`：OCR 引擎与逐格识别、PDF 文字层（`extract_pdf_text`）、标准 JSON（`build_table_data`）
  - `office_fb/`：python-docx/openpyxl 简化排版回退（`docx_to_data` / `xlsx_to_data`）
  - `align/`：`augment_xlsx_semantics`（对齐 openpyxl 赋稳定地址 `Sheet!A1`）与网格启发式小工具（`_pick_header_row` 等）
  - `semantic/`：角色标注 `assign_roles`、字段配对 `extract_fields`、`build_form_view`、`build_index`、数据简表（`parse_data_sheet` / `photo_to_sheet`）与匹配 `match_data_fields`
  - `output/`：`build_template`、`json_to_pdf`、`generate_frontend`、`sheet_json`（简化.json 导出，与 `parse_data_sheet` 互逆）
  - `pipeline/`：`extract_page`、`convert_document`、`stitch_page_data`/`scale_data`、`main`
- `server.py`：FastAPI + uvicorn 模板服务，静态托管 Vue 前端（`frontend/frontend/dist`），接口与 `frontend/frontend/src/api/template.ts` 一一对应。
- `ocr_service.py`：RapidOCR 本地 OCR 服务（FastAPI，默认 127.0.0.1:8100），模型启动时加载一次常驻内存，识别调用全局锁串行化；`extract_grid.py --ocr-url` 指向它后，逐格 OCR 批量走 HTTP（整图 + 格子坐标一次提交），裁剪/漏检兜底逻辑复用 `extract_grid.py` 的函数

前端（`frontend/frontend/`，Vue 3 + TypeScript + Vite，Node ≥ 22.18）：

- `src/types/template.ts` —— `template.json` 的 TypeScript 镜像（后端 JSON 的契约）
- `src/api/template.ts` —— 后端接口客户端
- `src/components/TemplatePage.vue` —— 核心复现组件（背景图 `<img>` 底层 + 字段覆盖层，`rect` 为占页宽高的百分比坐标，字号用容器查询单位 cqw 换算）
- `src/views/TemplateDisplayView.vue` 为唯一路由页面（`src/routers/index.ts`）
- 其余组件：`DataPanel.vue`（数据面板）、`PrintPreview.vue`、`ColorPicker.vue`、`StyleSelect.vue` 等；`src/utils/` 为纯函数工具

生成目录（gitignore，勿手工提交）：`grid_out/`（CLI 默认输出）、`out/`（服务端按内容哈希去重的模板输出）、`_uploads/`、`__pycache__/`。

## 构建与运行命令

命令行转换（Windows，用 Git Bash）：

```bash
.venv/Scripts/python.exe extract_grid.py 1.xlsx -o grid_out
```

模板服务（默认 127.0.0.1:8000）：

```bash
.venv/Scripts/python.exe server.py [--root .] [--port 8000]
```

OCR 服务（可选，默认 127.0.0.1:8100；起服后 extract_grid 的逐格 OCR 批量走 HTTP）：

```bash
.venv/Scripts/python.exe ocr_service.py [--port 8100]
.venv/Scripts/python.exe extract_grid.py scan.png --ocr-url http://127.0.0.1:8100 -o grid_out
# 或用环境变量 OCR_SERVICE_URL；服务不可达直接报错，不静默回退
```

前端开发（热更新，经 `VITE_API_BASE_URL` 指向本服务）：

```bash
cd frontend/frontend && npm run dev
```

前端构建（`npm run build` = 先 `vue-tsc` 类型检查再 `vite build`）：

```bash
cd frontend/frontend && npm run build
# Windows 上若 Node 堆内存崩溃，加 NODE_OPTIONS=--max-old-space-size=4096
```

依赖安装：后端无 requirements 文件，直接用 `.venv/Scripts/python.exe -m pip install <pkg>`（关键包见下）；前端 `cd frontend/frontend && npm install`。

关键 Python 依赖：FastAPI/uvicorn、pymupdf、opencv-python、rapidocr-onnxruntime（本地 OCR，无云端依赖）、onnxruntime-gpu + nvidia-cublas-cu12/nvidia-cudnn-cu12/nvidia-cufft-cu12/nvidia-cuda-runtime-cu12（GPU 推理）、openpyxl、python-docx、numpy、pywin32（COM 回退）。

注意：`onnxruntime-gpu` 与 `onnxruntime` 互斥（同名模块），**不要**单独 `pip install onnxruntime` 或重装 rapidocr-onnxruntime（它会拉回 CPU 版）。GPU 初始化由 `extract_grid._make_ocr_engine(use_gpu=None)` 自动探测：装的是 onnxruntime-gpu 且 CUDA/cuDNN DLL 就绪则三模型全部上 GPU，否则打印提示回退 CPU。nvidia-* pip 包的 bin 目录加 PATH 也在该函数内完成。另：rapidocr-onnxruntime 1.2.3 的 `cls_/rec_` 参数前缀解析有 bug，`_make_ocr_engine` 里打了补丁，升级该包时先验证补丁是否仍必要。

## 测试

仓库中**没有自动化测试**。验证方式是端到端跑管线并人工核对产物：

- CLI 跑一张表，检查输出目录的 `overlay.png`（格子/交点标注）与 `rebuilt.pdf`（JSON 重画的还原件）保真度
- 起 `server.py`，上传 xlsx/docx/pdf/图片，在前端核对"背景图 + 覆盖层"复现效果
- 用 `样表（简单表+复杂表）(1).xlsx`（双层表头+45 处合并的复杂表与单层表头简单表）做回归样例——README 宣称两套表通用，改动启发式规则后必须两者都过

## 代码约定

- 注释与文档用简体中文；docstring 风格与 `extract_grid.py` 头部模块注释一致
- `extract_grid.py` 用函数分区注释（`# ---- 标题 ----`）分隔，改动保持在对应分区内
- 所有识别/配对/索引规则必须是**纯通用启发式**，禁止针对具体某张表特判、打表（见 `技术方案.md` 第六节"已验证的通用性边界"）
- 可变化的阈值（线长比例、对齐候选数等）写成函数参数并带默认值，不写死在调用处
- Windows 环境约束：读图用 `cv2.imdecode(np.fromfile(...))` 而非 `cv2.imread`（中文路径）；WPS/Office 转换注意 `~$*` 锁文件
- uuid 由地址派生（uuid5），保证同一表重转后 uuid 稳定——改动寻址/对齐逻辑时不得破坏这一点
- 边界情况（占位文本、缺列、重名、对齐失败）一律进 `index.report`，不允许让整页转换中断

## 前后端契约（改动需双侧同步）

- `template.json`：`templateUuid` 与 `form.json` 的 `index.cells` uuid 一致；`pages[].background` 为相对路径，服务端加载时改写为 `/files/...`
- 填充语义 `index.cells[uuid].mode`：`overwrite`（空格直写）/ `replace`（整格覆盖占位）/ `append` / `inline`
- 改后端 JSON 结构时，必须同步更新 `src/types/template.ts`、`src/api/template.ts` 与 `server.py` 的 docstring 接口清单

## 安全与部署

- 纯本地工具，无认证、无云端调用；`server.py` 只绑 127.0.0.1，供本机前后端联调
- 不做生产部署；若对外开放需先加访问控制
- 不要提交：`.venv/`、`grid_out/`、`out/`、`_uploads/`、`_tmp_form/`、`__pycache__/`、WPS 锁文件 `~$*`（均已 gitignore）
