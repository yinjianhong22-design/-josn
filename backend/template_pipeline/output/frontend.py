# -*- coding: utf-8 -*-

# ---------------------------------------------------------------------------
# 前端代码生成 (数据驱动: data.json + index.html)
# ---------------------------------------------------------------------------

from ..common import json, os


def generate_frontend(data, out_dir):
    """把标准 JSON 落成前端产物:

    form.json   完整 JSON (含 form 可索引视图), 转换的直接产物,
                建索引/回填/还原都以它为准
    data.json   同一份内容的原名, 兼容已有消费方
    data.js     同一份数据包成 window.TABLE_DATA, 供 index.html 以 file:// 打开
    template.json  前端 Template 结构 (背景图 + 字段覆盖层), Vue 复现层消费,
                由 build_template 生成, 见 build_template docstring
    index.html  纯渲染层: 读数据, 为每个格子生成绝对定位的 div,
                几何与原图像素一一对应, 边框只在原图有线处绘制。
    """
    json_text = json.dumps(data, ensure_ascii=False, indent=2)
    for name in ('form.json', 'data.json'):
        with open(os.path.join(out_dir, name), 'w', encoding='utf-8') as f:
            f.write(json_text)
    with open(os.path.join(out_dir, 'data.js'), 'w', encoding='utf-8') as f:
        f.write(f'window.TABLE_DATA = {json_text};\n')

    index_path = os.path.join(out_dir, 'index.html')
    with open(index_path, 'w', encoding='utf-8') as f:
        f.write(INDEX_HTML)
    return index_path


INDEX_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>还原表格</title>
<style>
  body { background: #f5f5f5; font-family: "Microsoft YaHei", sans-serif; }
  .sheet { position: relative; background: #fff; margin: 24px auto; }
  .cell { position: absolute; box-sizing: border-box; padding: 4px 8px;
          white-space: pre-line; overflow: hidden;
          display: flex; align-items: center; }
  .freetext { position: absolute; white-space: nowrap; line-height: 1; }
</style>
</head>
<body>
  <div class="sheet" id="sheet"></div>
  <script src="data.js"></script>
  <script>
    const data = window.TABLE_DATA;
    const sheet = document.getElementById('sheet');
    sheet.style.width = data.width + 'px';
    sheet.style.height = data.height + 'px';
    const pxPerPt = (data.dpi || 300) / 72;
    const rules = data.rules || [];
    for (const c of data.cells) {
      const div = document.createElement('div');
      div.className = 'cell';
      div.style.left = c.x + 'px';
      div.style.top = c.y + 'px';
      div.style.width = c.w + 'px';
      div.style.height = c.h + 'px';
      if (!rules.length)  // 有矢量线段时由 rules 负责描线
        for (const side of ['top', 'bottom', 'left', 'right'])
          div.style['border' + side[0].toUpperCase() + side.slice(1)] =
            c.borders[side] ? '2px solid #333' : '0';
      div.textContent = c.text;
      sheet.appendChild(div);
    }
    // 电子档原始矢量线段: 精确坐标 + 原线宽, 每根线只画一次
    for (const rl of rules) {
      const div = document.createElement('div');
      const w = Math.abs(rl.x1 - rl.x0), h = Math.abs(rl.y1 - rl.y0);
      div.style.position = 'absolute';
      div.style.left = Math.min(rl.x0, rl.x1) + 'px';
      div.style.top = Math.min(rl.y0, rl.y1) + 'px';
      if (h > w) {  // 竖线
        div.style.width = Math.max(1, rl.width) + 'px';
        div.style.height = h + 'px';
      } else {      // 横线
        div.style.width = w + 'px';
        div.style.height = Math.max(1, rl.width) + 'px';
      }
      div.style.background = '#000';
      sheet.appendChild(div);
    }
    // 表格线框外的游离文字 (页眉/标题/页码等): x,y 为基线坐标(px), size 单位 pt
    for (const t of (data.texts || [])) {
      const div = document.createElement('div');
      div.className = 'freetext';
      const fs = t.size * pxPerPt;
      div.style.left = t.x + 'px';
      div.style.top = (t.y - fs * 0.85) + 'px';
      div.style.fontSize = fs + 'px';
      div.style.color = t.color || '#000';
      if (t.bold || t.role === 'title' || t.role === 'heading')
        div.style.fontWeight = 'bold';
      div.dataset.role = t.role || 'body';
      div.textContent = t.text;
      sheet.appendChild(div);
    }
  </script>
</body>
</html>
"""
