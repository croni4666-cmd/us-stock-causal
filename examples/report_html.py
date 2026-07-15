"""
examples/report_html.py - 5 段制报告 + K 线 SVG 合并为 1 个 HTML (v0.6.5 P6-2)

设计:
  - 跑 render_full_report() 拿 Markdown
  - 读 output/ 下的 K 线 SVG (indices_2y_<date>.svg + 可选 gold_1y_<date>.svg)
  - 用 render_html_report() 合并为 1 个独立 HTML
  - SVG inline, 邮件可发, 浏览器可看

输出:
  - output/report_<date>.html
  - 邮件附件 ≤ 1.5MB (含 2 个 SVG)
"""
from __future__ import annotations

import sys
import time
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from loguru import logger

from src import proxy  # noqa: F401
from src.report import render_full_report
from src.report_html import render_html_report


def main() -> int:
    print("=" * 72)
    print("us-stock-causal v0.6.5 - 5-segment report + K-line HTML (P6-2)")
    print(f"Run time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Proxy active: {proxy.is_proxied()}")
    print("=" * 72)

    t0 = time.time()
    today = date.today()
    today_str = today.isoformat()

    symbols = ["DIA", "QQQ", "RSP", "QQQE"]
    md_content = render_full_report(symbols)

    # 收集 SVG 文件 (按 LastWriteTime 倒序, 取每个 prefix 的最新 1 个)
    output_dir = PROJECT_ROOT / "output"
    svg_paths = []
    for prefix in ("indices_2y_", "gold_1y_"):
        # 找 prefix 开头的最新 SVG
        candidates = sorted(
            output_dir.glob(f"{prefix}*.svg"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if candidates:
            svg_paths.append(candidates[0])

    if not svg_paths:
        print(f"[warn] no K-line SVG found in {output_dir}, HTML will be report-only")
        print(f"[hint] 跑 python examples/indices_chart.py 先生成 K 线")
    else:
        print(f"[ok] found {len(svg_paths)} K-line SVG (latest by mtime):")
        for p in svg_paths:
            print(f"  - {p.name} ({p.stat().st_size // 1024}KB)")

    # 渲染 HTML
    html = render_html_report(
        md_content=md_content,
        kline_svg_paths=svg_paths,
        title=f"us-stock-causal Daily Report — {today_str}",
    )

    html_path = output_dir / f"report_{today_str}.html"
    html_path.write_text(html, encoding="utf-8")
    size_kb = html_path.stat().st_size // 1024

    elapsed = time.time() - t0
    print(f"\n{'=' * 72}")
    print(f"Done in {elapsed:.1f}s")
    print(f"  HTML:  {html_path} ({size_kb}KB)")
    print(f"  打开:  start {html_path}  (Windows) 或浏览器拖入")
    print(f"  邮件:  可直接附件, 单文件 ≤ {size_kb}KB")
    print(f"{'=' * 72}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
