# -*- coding: utf-8 -*-

# ---------------------------------------------------------------------------
# Word/Excel -> PDF (排版引擎降级链: wpscli -> WPS/Office COM; 都不可用
# 返回 None, 由调用方回退 python-docx/openpyxl 简化排版)
# ---------------------------------------------------------------------------

# 只用标准库 os (不 from ..common import), 保持零重依赖:
# 本模块可被 office2pdf.py 独立引用而不拖入 opencv/numpy 等重包
import os


def _find_wpscli():
    """在本机常见路径找 WPS 命令行工具 wpscli.exe。"""
    import glob
    patterns = [
        r'C:\Program Files*\WPS Office\*\clitool\wpscli.exe',
        r'C:\Program Files*\WPS Office\*\office6\wpscli.exe',
        os.path.expandvars(r'%LOCALAPPDATA%\Kingsoft\WPS Office\*'
                           r'\clitool\wpscli.exe'),
        os.path.expandvars(r'%LOCALAPPDATA%\Kingsoft\WPS Office\*'
                           r'\office6\wpscli.exe'),
    ]
    for pat in patterns:
        hit = glob.glob(pat)
        if hit:
            return sorted(hit)[-1]  # 取最新版本目录
    return None


def _set_attr(tag, name, value):
    """在 XML 开标签里设置/替换一个属性, 返回新标签文本。"""
    import re
    if re.search(rf'\s{name}="[^"]*"', tag):
        return re.sub(rf'\s{name}="[^"]*"', f' {name}="{value}"', tag)
    if tag.endswith('/>'):
        return tag[:-2] + f' {name}="{value}"/>'
    return tag[:-1] + f' {name}="{value}">'


def _fit_sheet_xml(data):
    """在一个 worksheet XML 里打开"调整为 1 页宽" (fitToPage)。

    只做三处原子修改: sheetPr 里加 <pageSetUpPr fitToPage="1"/>;
    pageSetup 去掉 scale、写上 fitToWidth="1" fitToHeight="0"
    (高度 0 = 纵向不限制页数)。其余字节原样保留。
    """
    import re
    xml = data.decode('utf-8')

    # 1) sheetPr/pageSetUpPr: fitToPage 开关
    if '<pageSetUpPr' in xml:
        xml = re.sub(r'<pageSetUpPr[^>]*/>',
                     lambda m: _set_attr(m.group(0), 'fitToPage', '1'), xml)
    elif re.search(r'<sheetPr[^>]*/>', xml):
        xml = re.sub(r'<sheetPr([^>]*)/>',
                     r'<sheetPr\1><pageSetUpPr fitToPage="1"/></sheetPr>', xml,
                     count=1)
    elif re.search(r'<sheetPr[^>]*>', xml):
        xml = re.sub(r'(</sheetPr>)',
                     r'<pageSetUpPr fitToPage="1"/>\1', xml, count=1)
    else:
        xml = re.sub(r'(<worksheet[^>]*>)',
                     r'\1<sheetPr><pageSetUpPr fitToPage="1"/></sheetPr>',
                     xml, count=1)

    # 2) pageSetup: 删 scale, 写 fitToWidth/fitToHeight
    def fix_page_setup(m):
        tag = re.sub(r'\sscale="[^"]*"', '', m.group(0))
        tag = _set_attr(tag, 'fitToWidth', '1')
        return _set_attr(tag, 'fitToHeight', '0')

    if '<pageSetup' in xml:
        xml = re.sub(r'<pageSetup[^>]*/>', fix_page_setup, xml)
    elif '<pageMargins' in xml:
        xml = re.sub(r'(<pageMargins[^>]*/>)',
                     r'\1<pageSetup fitToWidth="1" fitToHeight="0"/>',
                     xml, count=1)
    return xml.encode('utf-8')


def _xlsx_fit_to_page(src, dst):
    """复制 xlsx 并打开"调整为 1 页宽", 供排版引擎转 PDF 时等比缩放。

    与内容级缩放(改列宽/字号)不同: 这里只在 worksheet XML 里注入
    fitToPage 页面设置, 其余内容逐字节保持原样, 副本与原文件完全一致;
    缩放由 WPS/Excel 的排版引擎在转 PDF 时统一等比完成, 内容的相对
    位置严格不变, 生成的 PDF 就是缩放好的完整页面 (横向永不溢出分页)。
    """
    import re
    import zipfile

    with zipfile.ZipFile(src) as zin, \
            zipfile.ZipFile(dst, 'w', zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if re.fullmatch(r'xl/worksheets/sheet\d+\.xml', item.filename):
                data = _fit_sheet_xml(data)
            zout.writestr(item, data)
    return dst


def office_to_pdf(path, out_dir):
    """把 docx/xlsx 转成 PDF, 排版由真正的排版引擎完成(高保真),
    转出的 PDF 走电子档通路。

    优先用 WPS 官方命令行 wpscli (word2pdf/excel2pdf, 渲染正确);
    找不到再退到 WPS/Office COM 接口 (Windows, 需 pywin32); 都不可用返回
    None, 由调用方回退到 python-docx/openpyxl 简化排版。
    """
    import subprocess

    ext = os.path.splitext(path)[1].lower()
    abs_in = os.path.abspath(path)
    abs_out = os.path.abspath(os.path.join(
        out_dir, os.path.splitext(os.path.basename(path))[0] + '_office.pdf'))

    cur_in = abs_in
    if ext == '.xlsx':
        # 转换前注入"调整为 1 页宽"页面设置 (XML 级, 内容逐字节不动),
        # 转出的 PDF 就是排版引擎等比缩放好的完整页面, 横向永不溢出
        try:
            cur_in = _xlsx_fit_to_page(abs_in, abs_out.replace(
                '_office.pdf', '_print.xlsx'))
        except Exception as e:
            print(f'xlsx 页面设置注入失败(按原样转换): {e}')
            cur_in = abs_in

    wpscli = _find_wpscli()
    if wpscli:
        sub = 'word2pdf' if ext == '.docx' else 'excel2pdf'
        try:
            if os.path.exists(abs_out):
                os.remove(abs_out)  # 存在时 wpscli 会自动改名, 先删掉
            subprocess.run([wpscli, sub, cur_in, '-o', abs_out],
                           timeout=300, capture_output=True)
            if os.path.exists(abs_out):
                print(f'Office 转换: wpscli {sub}')
                return abs_out
        except Exception as e:
            print(f'wpscli 转换失败: {e}')

    return _office_com_to_pdf(ext, abs_in, cur_in, abs_out)


def _office_com_to_pdf(ext, abs_in, cur_in, abs_out, timeout=300):
    """WPS/Office COM 转换 (Windows 本机), 成功返回 pdf 路径, 失败返回 None。

    COM 调用放在守护工作线程中并限制等待时间; 超时后尝试 Quit, 但不强行
    终止仍在 COM 调用里的线程。目标旧文件先删除, 避免误认上次转换结果。
    """
    try:
        import pythoncom
        import win32com.client
    except ImportError:
        print('未安装 pywin32, 跳过 Office COM 转换 (pip install pywin32)')
        return None
    import threading

    try:
        if os.path.exists(abs_out):
            os.remove(abs_out)
    except OSError as e:
        print(f'Office 转换失败: 无法删除旧 PDF ({e})')
        return None

    progids = (['Kwps.Application', 'wps.Application', 'Word.Application']
               if ext == '.docx'
               else ['Ket.Application', 'et.Application', 'Excel.Application'])
    state = {'app': None, 'err': None}
    done = threading.Event()

    def convert():
        app = None
        pythoncom.CoInitialize()
        try:
            for pid in progids:
                try:
                    app = win32com.client.DispatchEx(pid)
                    state['app'] = app
                    print(f'Office 转换: 使用 {pid}')
                    break
                except Exception:
                    app = None
            if app is None:
                state['err'] = '未找到可用的 WPS/Office COM 接口'
                return
            try:
                app.Visible = False
            except Exception:
                pass
            for _ in range(2):  # 冷启动/残留实例时首次调用可能失败, 重试一次
                doc = wb = None
                try:
                    if ext == '.docx':
                        doc = app.Documents.Open(abs_in, ReadOnly=True)
                        try:
                            doc.ExportAsFixedFormat(abs_out, 17)
                        except Exception:
                            doc.SaveAs(abs_out, FileFormat=17)  # wdFormatPDF
                    else:
                        # 注意: ET 的 Workbooks.Open 不支持 ReadOnly 关键字
                        wb = app.Workbooks.Open(cur_in)
                        wb.ExportAsFixedFormat(0, abs_out)    # xlTypePDF
                    break
                except Exception as e:
                    state['err'] = e
                finally:
                    for item in (doc, wb):
                        try:
                            if item is not None:
                                item.Close(False)
                        except Exception:
                            pass
        except Exception as e:
            state['err'] = e
        finally:
            try:
                if app is not None:
                    app.Quit()
            except Exception:
                pass
            pythoncom.CoUninitialize()
            done.set()

    worker = threading.Thread(target=convert, name='office-com-to-pdf',
                              daemon=True)
    worker.start()
    if not done.wait(timeout):
        print(f'Office 转换失败: COM 操作超过 {timeout} 秒, 尝试退出 Office')
        app = state.get('app')
        if app is not None:
            initialized = False
            try:
                pythoncom.CoInitialize()
                initialized = True
                app.Quit()
            except Exception:
                pass
            finally:
                if initialized:
                    pythoncom.CoUninitialize()
        return None

    try:
        valid_output = os.path.isfile(abs_out) and os.path.getsize(abs_out) > 0
    except OSError:
        valid_output = False
    if not valid_output:
        print(f'Office 转换失败: {state["err"] or "未生成新的 PDF 文件"}')
        return None
    return abs_out
