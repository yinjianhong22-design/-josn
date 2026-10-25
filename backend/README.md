# Backend 说明（backend/）

本目录是项目后端：FastAPI 服务入口 + 转换管线包。

- `backend/server.py` —— 模板服务（默认 127.0.0.1:8000）：上传 xlsx/docx/pdf/图片跑转换管线、模板库增删查改、数据简表匹配回填、静态托管 Vue 前端 `frontend/frontend/dist` 与 `/files`（项目根）
- `backend/ocr_service.py` —— OCR 服务（默认 127.0.0.1:8100，可选）：RapidOCR 模型常驻内存，批量逐格识别；CLI `--ocr-url` 指向它后逐格 OCR 走 HTTP
- `backend/template_pipeline/` —— 转换管线全部实现（逐模块详解见根目录 `模块开发文档.md`）
- CLI 入口 —— `python -m backend.template_pipeline.pipeline.cli`（原根目录 `extract_grid.py` 兼容 shim 已删除；`server.py` / `ocr_service.py` 直接 import 本包叶子模块）。入口脚本会把项目根加进 `sys.path`，**从任意目录启动均可**

开发环境实测：Windows，Python 3.14.7。仓库根目录有 `requirements.txt`（与实测环境一致，可直接 `pip install -r requirements.txt`）；也可按下面清单手动装。

## 1. 依赖清单

| pip 包 | 必需性 | 用途 | 实测版本 |
|---|---|---|---|
| fastapi | 必需 | 两个 HTTP 服务的框架 | 0.143.0 |
| uvicorn | 必需 | ASGI 服务器 | 0.54.0 |
| pydantic | 必需 | fastapi 传递依赖，ocr_service 显式用 | 2.14.1 |
| pymupdf | 必需 | PDF 文字/矢量线提取、栅格化（懒加载，缺了直接退出） | 1.28.2 |
| opencv-python | 必需 | 图像加载、像素线提取、裁剪 | 5.0.0.93 |
| numpy | 必需 | 数组底座 | 2.5.3 |
| openpyxl | 必需 | xlsx 通路 + 数据简表 | 3.1.5 |
| python-docx | 必需 | docx 无排版引擎时的简化排版回退 | 1.2.0 |
| pillow | 必需 | office_fb 背景自渲染、服务端预览图 | 12.3.0 |
| rapidocr-onnxruntime | 可选 | 本地 OCR；不装则跳过文字识别，ocr_service 起不来（503） | 1.2.3 |
| onnxruntime-gpu | 可选（GPU） | OCR 推理后端。**与 `onnxruntime` 互斥**（同名模块），装 GPU 版即提供 `onnxruntime` 模块名；**不要**单独 `pip install onnxruntime`，也不要重装 rapidocr-onnxruntime（会拉回 CPU 版） | 1.24.1 |
| pywin32 | 仅 Windows / 可选 | Office COM 转 PDF 级；Linux 缺省自动跳过 | 312 |

GPU 版 OCR 还需要 CUDA 运行库（仅当走 GPU 时）：

| pip 包 | 实测版本 |
|---|---|
| nvidia-cublas-cu12 | 12.9.2.10 |
| nvidia-cudnn-cu12 | 9.27.0.42 |
| nvidia-cufft-cu12 | 11.4.1.4 |
| nvidia-cuda-runtime-cu12 | 12.9.79 |

说明：onnxruntime-gpu ≥1.24 的 Windows wheel 不捆绑 CUDA/cuDNN DLL，所以 Windows 上要从 pip 装这组 nvidia-* 运行库包（代码自动把它们的 `bin` 目录加进 PATH）；Linux wheel 一般自带。GPU 是否生效由 `backend/template_pipeline/text/ocr_engine.py` 的 `_make_ocr_engine()` 启动探测：三模型 session 都在 `CUDAExecutionProvider` 上才算成功，否则打印原因回退 CPU，**不中断转换**。

已验证的坑：

- `opencv-python` 与 `opencv-python-headless` 不要同时装（当前开发 venv 两者共存，部署时只保留一个，推荐 `opencv-python`，读图统一走 `cv2.imdecode`）。
- rapidocr-onnxruntime 1.2.3 的 `UpdateParameters` 有 bug（cls/rec 不剥参数前缀，导致方向分类和识别模型永远落 CPU），`_make_ocr_engine` 内有 monkey-patch；升级该包前先验证补丁是否仍必要。

## 2. 外部可执行程序（Office → PDF 降级链）

Word/Excel 先经排版引擎转 PDF 冻结版式，降级顺序在 `backend/template_pipeline/input/office_convert.py: office_to_pdf()`：

1. **wpscli**（仅 Windows）：自动在 `C:\Program Files*\WPS Office\...` 与 `%LOCALAPPDATA%\Kingsoft\WPS Office\...` 下找 `wpscli.exe`
2. **WPS/Office COM**（仅 Windows，需 pywin32）

两条引擎都不可用（比如 Linux 服务器）也不报错中断，而是回退 python-docx/openpyxl 简化排版 + PIL 自渲染背景（近似版式）。**注意：Linux 版 WPS 只有 GUI 程序，无 wpscli，不能无头转 PDF**——要保留高保真排版就必须在 Windows（本机或 Windows 云服务器）上跑。

## 3. 安装

Windows（开发机）：

```bash
py -3.14 -m venv .venv
.venv/Scripts/python.exe -m pip install fastapi uvicorn pymupdf opencv-python numpy openpyxl python-docx pillow
# 可选：OCR
.venv/Scripts/python.exe -m pip install rapidocr-onnxruntime onnxruntime-gpu nvidia-cublas-cu12 nvidia-cudnn-cu12 nvidia-cufft-cu12 nvidia-cuda-runtime-cu12
# 可选：Windows COM 转 PDF 级
.venv/Scripts/python.exe -m pip install pywin32
```

Linux（服务器，注意没有排版引擎，Word/Excel 会走近似版式回退）：

```bash
python3 -m venv .venv && .venv/bin/pip install fastapi uvicorn pymupdf opencv-python-headless numpy openpyxl python-docx pillow
```

注意 Linux 上装 `opencv-python-headless` 而非 `opencv-python`（无 GUI 依赖）；若不用 OCR 可跳过 rapidocr 一组。

## 4. 配置项

### 环境变量（全后端只有 2 个）

| 变量 | 默认值 | 用途 |
|---|---|---|
| `OCR_SERVICE_URL` | 空 | OCR 服务地址（如 `http://127.0.0.1:8100`），等价于 CLI `--ocr-url`；设置了但服务不可达 = 直接报错 |
| `PATH`（写入） | — | Windows GPU 路径下，代码把 nvidia-* pip 包的 `bin` 目录 prepend 进去，无需手工配置 |

### 命令行参数

`server.py`：

| 参数 | 默认 | 说明 |
|---|---|---|
| `--root` | `backend/` 的上级目录（项目根） | 决定 `_uploads/`、`out/`、`/files` 静态挂载、`frontend/frontend/dist` 位置 |
| `--host` | `127.0.0.1` | 只绑本机，无鉴权，不要直接暴露公网 |
| `--port` | 8000 | |

`ocr_service.py`：

| 参数 | 默认 | 说明 |
|---|---|---|
| `--host` | `127.0.0.1` | |
| `--port` | 8100 | 模型在启动时加载一次常驻内存，识别请求由全局锁串行化 |

CLI（`python -m backend.template_pipeline.pipeline.cli`，完整参数表见根目录 `模块开发文档.md` §2.8，关键几个）：

| 参数 | 默认 | 说明 |
|---|---|---|
| `input` | — | 输入文件（位置参数） |
| `-o/--out` | `grid_out` | 输出目录 |
| `--page` / `--dpi` | 0 / 300 | 页码 / 栅格化精度 |
| `--ocr-url` | 取 `OCR_SERVICE_URL` | 指向 OCR 服务后逐格 OCR 走 HTTP |
| `--no-ocr` / `--force-ocr` | — | OCR 开关 |
| 6 个启发式阈值 | 见 `--help` | 线长比例类参数，CLI 可调；**服务端 `/upload` 路径硬编码默认值，不可调**（`backend/server.py: _convert_args()`） |

## 5. 启动

```bash
# 模板服务（前端联调 / 上传转换）
.venv/Scripts/python.exe backend/server.py            # 127.0.0.1:8000

# OCR 服务（可选，先起它再让 CLI 走 HTTP）
.venv/Scripts/python.exe backend/ocr_service.py       # 127.0.0.1:8100

# CLI 单次转换（不启服务）
.venv/Scripts/python.exe -m backend.template_pipeline.pipeline.cli 1.xlsx -o grid_out
.venv/Scripts/python.exe -m backend.template_pipeline.pipeline.cli scan.png --ocr-url http://127.0.0.1:8100 -o grid_out
```

## 6. 安全说明

- 两个服务都**无鉴权、无上传大小限制**，默认只绑 `127.0.0.1`；对外开放前必须先加访问控制和上传限制。
- 边界情况（占位文本、缺列、重名、对齐失败）不会中断转换，统一进 `index.report`。

## 7. frp 部署（暴露到公网）

场景：本机有 GPU/排版环境，想让外网调用本机的 OCR 服务（或模板服务）。用 frp 内网穿透，配置在根目录 `deploy/`（`frps.toml` / `frpc.toml` / `bin/frpc.exe`，细节见 `deploy/README.md`）。**注意两个 toml 里的 token 是明文提交的，对外用务必换掉。**

结构：公网服务器跑 **frps**（7000 接入端口），本机跑 **frpc** 把 `127.0.0.1:8100` 转发为公网 `107.182.190.191:18100`。

**步骤一：公网服务器部署 frps**（Linux 示例，frp 0.71.1）

```bash
wget https://github.com/fatedier/frp/releases/download/v0.71.1/frp_0.71.1_linux_amd64.tar.gz
tar xzf frp_0.71.1_linux_amd64.tar.gz && cd frp_0.71.1_linux_amd64
cp /path/to/repo/deploy/frps.toml .   # 换掉 token
./frps -c ./frps.toml                  # 常驻建议配 systemd: Restart=always
```

防火墙/安全组放通 **TCP 7000**（frpc 接入）和 **TCP 18100**（OCR 访问端口）。

**步骤二：本机（Windows）跑 frpc**

前置：给 Defender 加排除项（frpc 常被误报，见 frp issue 3637），frpc.exe 已放 `deploy/bin/`。

```bash
# 1. 启动 OCR 服务（另开一个终端；模板服务同理用 8000）
.venv/Scripts/python.exe backend/ocr_service.py

# 2. 项目根目录启动 frpc
./deploy/bin/frpc.exe -c deploy/frpc.toml
```

**步骤三：验证**

```bash
# 经公网调用 OCR（接口与本地一致）
curl -X POST http://107.182.190.191:18100/ocr/cells \
     -H "Content-Type: application/json" -d @body.json
# body.json 格式见 ocr_service.py 的 /ocr/cells 接口定义
```

注意事项：

- OCR/模板服务本身**无鉴权**，端口对公网开放后任何人都能调用——建议仅在需要时启动 frpc，或在服务器防火墙做来源 IP 白名单。
- 要暴露模板服务（8000）：在 `frpc.toml` 加一个 `[[proxies]]`，`remotePort` 选 18101 等（须在 frps 的 `allowPorts` 18100-18109 范围内）。
- 换公网端口改 `frpc.toml` 的 `remotePort`；换服务器改两个 toml 的 `serverAddr` / token。

## 8. 改动自查

- 新 pip 依赖 → 同步本文第 1 节表格和根目录 `AGENTS.md` 的"关键 Python 依赖"段
- 新环境变量 → 同步本文第 4 节表格和 `模块开发文档.md`
- 新启动参数 → 同步本文、`backend/server.py` docstring 接口清单、根目录 `README.md`
- 引入新的 Office 引擎或 OCR 引擎 → 同步 `技术方案.md` 第五章技术清单
