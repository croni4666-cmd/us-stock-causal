"""
plot_gold.py - 黄金近期价格走势图 (1y K-line + 5 SMA + R1/S1 + 性能总览)

输出: output/gold_1y_<date>.{png,svg}
  - 上: GC=F 黄金期货 (1y 蜡烛)
  - 中: GLD SPDR Gold ETF (1y 蜡烛)
  - 下: 全标的 1d 涨跌幅总览 (Performance Dashboard)
  - 终端打印: 中文 Google 风格表格 (现价 / 1d 涨跌幅 / 52w 高低)

跑: python examples/plot_gold.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import matplotlib as mpl
import matplotlib.pyplot as plt

# 中文字体 (Windows 优先 Microsoft YaHei, 跨平台 fallback SimHei / Noto Sans CJK)
mpl.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'Noto Sans CJK SC', 'Arial Unicode MS', 'DejaVu Sans']
mpl.rcParams['axes.unicode_minus'] = False

from src import proxy  # noqa: F401
from src.kline import plot_single, savefig_multi_format
from src.performance_dashboard import (
    plot_performance_dashboard,
    render_performance_table,
    render_performance_table_html,
)


def main() -> int:
    print("=" * 72)
    print(f"us-stock-causal — 黄金近期价格走势图 (1y K-line + 性能总览)")
    print(f"Run time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Proxy active: {proxy.is_proxied()}")
    print("=" * 72)

    today_str = time.strftime('%Y-%m-%d')
    out_dir = PROJECT_ROOT / "output"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / f"gold_1y_{today_str}.png"

    # 3 subplot: 2 K-line + 1 performance dashboard
    # 比例: 上 3:3, 下 4 (performance dashboard 高一点, 因为 20 标的 + 2 行 label)
    fig = plt.figure(figsize=(15, 15))
    gs = fig.add_gridspec(3, 1, height_ratios=[3, 3, 4.5], hspace=0.40)
    axes = [fig.add_subplot(gs[0]), fig.add_subplot(gs[1]), fig.add_subplot(gs[2])]

    fig.suptitle(
        "黄金近期价格走势 — 1 Year K-line + 性能总览  (GC=F 期货 / GLD ETF)",
        fontsize=15, fontweight="bold", y=0.998,
    )

    # 上: GC=F 期货 (1y K-line, 5 SMA + R1/S1)
    plot_single(
        symbol="GC=F",
        ax=axes[0],
        layer="commodities_futures",
        lookback_days=252,
        show_50sma=True,
        compact_title=False,
    )
    axes[0].set_title("GC=F  Gold COMEX Futures (USD/oz) — 1y K-line", fontsize=11, fontweight="bold")

    # 中: GLD ETF (1y K-line, 5 SMA + R1/S1)
    plot_single(
        symbol="GLD",
        ax=axes[1],
        layer="commodities_spot_etf",
        lookback_days=252,
        show_50sma=True,
        compact_title=False,
    )
    axes[1].set_title("GLD  SPDR Gold Shares ETF (USD/share) — 1y K-line", fontsize=11, fontweight="bold")

    # 下: 全标的 1d 涨跌幅总览 (Google Finance 风格)
    plot_performance_dashboard(axes[2])

    plt.tight_layout(rect=[0, 0, 1, 0.97])

    # 输出 PNG + SVG
    written = savefig_multi_format(
        fig, out_path,
        formats=("png", "svg"),
        png_dpi=300,
    )

    print()
    print("=" * 72)
    print(f"Done. Output:")
    for w in written:
        kb = w.stat().st_size / 1024
        print(f"  {w}  ({kb:.0f} KB)")
    print(f"  Period: 1y (252 trading days, ~2025-07-23 -> 2026-07-22)")
    print(f"  Annotations: 5 SMA (20/50/100/150/200) + R1/S1 + FOMC/CPI/NFP event lines")
    print(f"  Y-axis: 52w high+20% / 52w low-20% (User 建议, v0.6.8h fix)")
    print("=" * 72)
    print()

    # 终端打印中文 Google 风格表格
    print("[PERF] 全标的现价 + 1d 涨跌幅 (Google Finance 风格):")
    print()
    print(render_performance_table())
    print()
    print("=" * 72)

    # 同时把 HTML 表格写到 output/, 邮件附 HTML 报告
    table_html_path = out_dir / f"performance_table_{today_str}.html"
    html_doc = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>us-stock-causal — Performance Dashboard {today_str}</title>
<style>
body {{ font-family: 'Microsoft YaHei', sans-serif; max-width: 1100px; margin: 20px auto; padding: 0 20px; }}
h1 {{ font-size: 18px; color: #202124; border-bottom: 2px solid #1a73e8; padding-bottom: 8px; }}
.note {{ color: #5f6368; font-size: 12px; margin: 12px 0; }}
</style>
</head>
<body>
<h1>us-stock-causal — 全标的 1d 涨跌幅总览 ({today_str})</h1>
<p class="note">数据来源: cache parquet + yfinance, 报告时点: {today_str}</p>
{render_performance_table_html()}
</body>
</html>"""
    table_html_path.write_text(html_doc, encoding="utf-8")
    print(f"HTML 表格: {table_html_path}  ({table_html_path.stat().st_size / 1024:.0f} KB)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
