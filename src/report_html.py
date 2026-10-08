"""
src/report_html.py - 5 段制报告 HTML 渲染 (Phase 6 P6-2)

设计:
  - 输入: 5 段制 Markdown (render_full_report 输出) + K 线 SVG 文件路径
  - 输出: 1 个独立 HTML 文件, inline SVG + Markdown 转 HTML
  - 邮件友好: 单文件, 不用外链, 浏览器直接打开
  - 矢量: SVG 内嵌, 任意缩放清晰

为什么不用 base64 inline:
  - SVG 本身是 XML 文本, 直接 inline 浏览器识别最稳
  - base64 编码后体积 +33%, 邮件附件更大
  - debug 也方便 (grep 找 SVG 内容)

Markdown → HTML:
  - 不依赖外部 markdown lib (markdown / mistune), 简单 regex 处理够用
  - 5 段制结构简单: ## NNN \n**① 段名**: ... \n**② 段名**: ...
"""
from __future__ import annotations

import re
from html import escape
from urllib.parse import urlsplit
from pathlib import Path
from typing import Optional

import markdown  # type: ignore


def _md_to_html(md: str) -> str:
    """Markdown → HTML 转换"""
    # 用 markdown lib (轻量, PyPI 标准)
    md_lib = markdown.Markdown(extensions=["extra", "sane_lists"])
    return _sanitize_html(md_lib.convert(md))


def _sanitize_html(content: str) -> str:
    """Rebuild a passive report fragment with a small Markdown tag allowlist."""
    from lxml import etree, html
    allowed = set('p br hr h1 h2 h3 h4 h5 h6 strong em b i del s blockquote pre code '
                  'ul ol li dl dt dd table thead tbody tfoot tr th td a div span sup sub'.split())
    source = html.fragment_fromstring(content, create_parent='div')
    def clean(node):
        if not isinstance(node.tag, str) or node.tag not in allowed:
            return None
        out = etree.Element(node.tag)
        out.text = node.text
        for key in ('id', 'class', 'title'):
            if key in node.attrib:
                out.set(key, node.get(key))
        if node.tag == 'a' and node.get('href'):
            href = node.get('href').strip()
            try:
                safe_scheme = urlsplit(href).scheme.lower() in ('', 'http', 'https', 'mailto')
            except ValueError:
                safe_scheme = False
            if (not any(ord(c) < 32 or c == '\\' for c in href)
                    and not href.startswith('//')
                    and safe_scheme):
                out.set('href', href)
                out.set('rel', 'noopener noreferrer')
        if node.tag in ('td', 'th'):
            for key in ('colspan', 'rowspan'):
                value = node.get(key, '')
                if value.isdigit() and 0 < int(value) <= 100:
                    out.set(key, value)
        for child in node:
            item = clean(child)
            if item is not None:
                out.append(item)
                item.tail = child.tail
            elif child.tail:
                if len(out):
                    out[-1].tail = (out[-1].tail or '') + child.tail
                else:
                    out.text = (out.text or '') + child.tail
        return out
    wrapper = clean(source)
    return (escape(wrapper.text or '') + ''.join(
        etree.tostring(child, encoding='unicode', method='html') for child in wrapper))


def _read_svg_inline(svg_path: Path) -> str:
    """读 SVG 文件, 返回去 XML decl 的内容 (适合 inline)"""
    with svg_path.open('rb') as source:
        raw = source.read(20 * 1024 * 1024 + 1)
    if len(raw) > 20 * 1024 * 1024:
        raise ValueError('oversized SVG XML')
    text = raw.decode('utf-8')
    from lxml import etree
    from src.svg_metadata import namespace_svg_ids, sanitize_svg
    if re.search(r'<!ENTITY\b', text, re.I):
        raise ValueError('unsafe or oversized SVG XML')
    try:
        root = etree.fromstring(text.encode('utf-8'), parser=etree.XMLParser(
            resolve_entities=False, load_dtd=False, no_network=True))
    except etree.XMLSyntaxError as exc:
        raise ValueError('invalid SVG XML') from exc
    sanitize_svg(root)
    namespace_svg_ids(root)
    return etree.tostring(root,encoding='unicode')


def render_html_report(
    md_content: str,
    kline_svg_paths: Optional[list[Path]] = None,
    title: str = "us-stock-causal Daily Report",
    css_path: Optional[Path] = None,
) -> str:
    """
    v0.6.5 (P6-2): 5 段制报告 + K 线 SVG 合并为 1 个 HTML 文件

    Args:
        md_content: 5 段制 Markdown 文本 (render_full_report 输出)
        kline_svg_paths: K 线 SVG 文件路径列表 (按时间顺序, 插在 ## NNN 标题之后)
        title: HTML <title>
        css_path: 自定义 CSS 路径, None 用默认

    Returns:
        完整 HTML 字符串
    """
    md_html = _md_to_html(md_content)
    title = escape(title)

    # 把 K 线 SVG 嵌入对应位置 — 简化方案: 全部放报告底部
    # 高级方案: 按日期或 symbol 对应到 ## NNN 段 (留 v0.6.6 做)
    svg_html_blocks = []
    if kline_svg_paths:
        for svg_path in kline_svg_paths:
            if svg_path.exists():
                svg_content = _read_svg_inline(svg_path)
                svg_html_blocks.append(
                    f'<div class="kline-block">\n'
                    f'  <h3 class="kline-title">{escape(svg_path.stem)}</h3>\n'
                    f'  <div class="kline-svg">{svg_content}</div>\n'
                    f'</div>'
                )

    kline_section = ""
    if svg_html_blocks:
        kline_section = (
            '<hr class="section-divider">\n'
            '<section id="kline-section">\n'
            '<h2>📈 价格走势与均线（SVG矢量，收盘价日期及单位见图）</h2>\n'
            + "\n".join(svg_html_blocks)
            + "\n</section>"
        )

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
                   "Microsoft YaHei", sans-serif;
      max-width: 1200px;
      margin: 0 auto;
      padding: 24px;
      line-height: 1.6;
      color: #1f2937;
      background: #fafafa;
    }}
    h1, h2, h3 {{ color: #0f172a; }}
    h1 {{ font-size: 1.8em; border-bottom: 3px solid #1976d2; padding-bottom: 8px; }}
    h2 {{ font-size: 1.4em; margin-top: 32px; border-left: 4px solid #1976d2; padding-left: 12px; }}
    h3 {{ font-size: 1.15em; color: #475569; }}
    p, li {{ font-size: 14px; }}
    strong {{ color: #0f172a; }}
    hr {{ border: none; border-top: 1px dashed #cbd5e1; margin: 24px 0; }}
    .kline-block {{
      margin: 24px 0;
      padding: 16px;
      background: #ffffff;
      border: 1px solid #e2e8f0;
      border-radius: 8px;
      box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }}
    .kline-title {{
      margin: 0 0 12px 0;
      color: #475569;
      font-size: 1.1em;
    }}
    .kline-svg {{
      overflow-x: auto;
      text-align: center;
    }}
    .kline-svg svg {{
      max-width: 100%;
      height: auto;
    }}
    .section-divider {{
      margin: 48px 0 24px 0;
    }}
    code {{
      background: #f1f5f9;
      padding: 2px 6px;
      border-radius: 3px;
      font-size: 0.9em;
    }}
  </style>
</head>
<body>
  <header>
    <h1>📊 {title}</h1>
    <p><em>由 us-stock-causal 自动化生成 · v0.6.5 (P6-2 HTML 合并) · SVG 矢量 K 线</em></p>
  </header>

  <main>
    <section id="report-md">
{md_html}
    </section>
{kline_section}
  </main>

  <footer style="margin-top: 48px; padding-top: 16px; border-top: 1px solid #e2e8f0; color: #64748b; font-size: 12px;">
    <p><strong>免责声明</strong>: 本报告由自动化分析生成, 基于历史数据 + 公开 sector weights。
    <strong>不构成投资建议</strong>。信号矛盾 score 越高, 越要谨慎。事件前 1 周内的预测需打折。</p>
  </footer>
</body>
</html>
"""
    return html
