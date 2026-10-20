# -*- coding: utf-8 -*-

# ---------------------------------------------------------------------------
# Word/Excel -> PDF (本机 WPS/Office COM 排版引擎, 高保真)
# ---------------------------------------------------------------------------

from ..common import os


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
    找不到再退到 WPS/Office COM 接口; 都不可用返回 None,
    由调用方回退到 python-docx/openpyxl 简化排版。
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

    try:
        import pythoncom
        import win32com.client
    except ImportError:
        print('未安装 pywin32, 跳过 Office 转换 (pip install pywin32)')
        return None
    progids = (['Kwps.Application', 'wps.Application', 'Word.Application']
               if ext == '.docx'
               else ['Ket.Application', 'et.Application', 'Excel.Application'])
    pythoncom.CoInitialize()
    app = None
    try:
        for pid in progids:
            try:
                app = win32com.client.DispatchEx(pid)
                print(f'Office 转换: 使用 {pid}')
                break
            except Exception:
                app = None
        if app is None:
            print('未找到可用的 WPS/Office COM 接口')
            return None
        try:
            app.Visible = False
        except Exception:
            pass
        err = None
        for _ in range(2):  # WPS 冷启动/残留实例时第一次调用可能失败, 重试一次
            try:
                if ext == '.docx':
                    doc = app.Documents.Open(abs_in, ReadOnly=True)
                    try:
                        doc.ExportAsFixedFormat(abs_out, 17)
                    except Exception:
                        doc.SaveAs(abs_out, FileFormat=17)  # wdFormatPDF
                    doc.Close(False)
                else:
                    # 注意: ET 的 Workbooks.Open 不支持 ReadOnly 关键字
                    wb = app.Workbooks.Open(cur_in)
                    wb.ExportAsFixedFormat(0, abs_out)    # xlTypePDF
                    wb.Close(False)
                break
            except Exception as e:
                err = e
        if not os.path.exists(abs_out):
            print(f'Office 转换失败: {err}')
            return None
        return abs_out
    except Exception as e:
        print(f'Office 转换失败: {e}')
        return None
    finally:
        try:
            if app is not None:
                app.Quit()
        except Exception:
            pass
        pythoncom.CoUninitialize()
