# -*- coding: utf-8 -*-

# ---------------------------------------------------------------------------
# OCR 引擎构造 (RapidOCR, 本地 GPU/CPU 自动探测)
# ---------------------------------------------------------------------------

from ..common import os, _OCR_TEXT_SCORE


def _prepend_nvidia_cuda_dlls():
    """onnxruntime-gpu >= 1.24 的 Windows wheel 不再捆绑 CUDA/cuDNN DLL;
    若通过 nvidia-*-cu12 pip 包提供, 需要把它们的 bin 目录加进 PATH,
    供 onnxruntime_providers_cuda.dll 解析依赖 (cublasLt/cudnn/cufft/
    cudart)。返回是否找到并加入。
    """
    from pathlib import Path
    try:
        import onnxruntime
    except ImportError:
        return False
    nvidia = Path(onnxruntime.__file__).resolve().parent.parent / 'nvidia'
    bins = [str(d) for d in sorted(nvidia.glob('*/bin')) if d.is_dir()]
    if not bins:
        return False
    os.environ['PATH'] = os.pathsep.join(bins + [os.environ.get('PATH', '')])
    return True


def _patch_rapidocr_cuda_kwargs():
    """修补 rapidocr-onnxruntime 1.2.3 的参数更新 bug: det 会剥 'det_'
    前缀, cls/rec 不剥, 导致 cls_use_cuda/rec_use_cuda 写不进配置,
    识别和方向分类模型永远落 CPU。这里按 det 的同等逻辑打补丁
    (只影响进程内 rapidocr 的 UpdateParameters 类)。
    """
    from rapidocr_onnxruntime.utils import UpdateParameters, root_dir

    def _mk(prefix):
        def _update(self, config, kw):
            if not kw:
                return config
            kw = {k.split(prefix, 1)[1]: v for k, v in kw.items()}
            if not kw.get('model_path'):
                kw['model_path'] = str(root_dir / config['model_path'])
            config.update(kw)
            return config
        return _update

    UpdateParameters.update_cls_params = _mk('cls_')
    UpdateParameters.update_rec_params = _mk('rec_')


def _engine_sessions_on_cuda(engine):
    """确认 det/cls/rec 三个 onnxruntime session 都真的在 CUDA provider
    上 (CUDAExecutionProvider 在可用列表里不代表 DLL 依赖能加载成功)。"""
    try:
        sess = [engine.text_detector.infer.session,
                engine.text_cls.infer.session,
                engine.text_recognizer.session.session]
        return all('CUDAExecutionProvider' in s.get_providers() for s in sess)
    except Exception:
        return False


def _make_ocr_engine(use_gpu=None):
    """构造 RapidOCR 实例, 识别阈值与逐格兜底的 text_score 一致 (0.3)。

    本地 (ocr_cells) 与服务端 (ocr_service.py) 共用此入口, 避免两处写死
    参数日后改不一致; 未安装 rapidocr-onnxruntime 时返回 None。

    use_gpu: True 强制 GPU, False 强制 CPU, None 自动 (装的是
    onnxruntime-gpu 且 CUDA 初始化成功才用 GPU)。GPU 初始化失败
    (缺 CUDA/cuDNN DLL、驱动不匹配等) 打印提示并回退 CPU, 不中断转换。
    """
    from pathlib import Path
    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError:
        return None
    if use_gpu is None:
        try:
            import onnxruntime as ort
            use_gpu = 'CUDAExecutionProvider' in ort.get_available_providers()
        except ImportError:
            use_gpu = False
    if use_gpu:
        _prepend_nvidia_cuda_dlls()
        _patch_rapidocr_cuda_kwargs()
        import rapidocr_onnxruntime
        models = Path(rapidocr_onnxruntime.__file__).resolve().parent / 'models'
        try:
            engine = RapidOCR(
                text_score=_OCR_TEXT_SCORE,
                det_use_cuda=True,
                det_model_path=str(models / 'ch_PP-OCRv3_det_infer.onnx'),
                cls_use_cuda=True,
                cls_model_path=str(models / 'ch_ppocr_mobile_v2.0_cls_infer.onnx'),
                rec_use_cuda=True,
                rec_model_path=str(models / 'ch_PP-OCRv3_rec_infer.onnx'))
            if _engine_sessions_on_cuda(engine):
                print('RapidOCR 引擎: CUDA (GPU)')
                return engine
            print('RapidOCR 引擎: CUDA 初始化失败, 回退 CPU')
        except Exception as e:
            print(f'RapidOCR 引擎: GPU 构造失败 ({e}), 回退 CPU')
    try:
        return RapidOCR(text_score=_OCR_TEXT_SCORE)
    except Exception:
        return RapidOCR()
