"""
examples/indices_chart.py - 4 指数 (DIA/QQQ/RSP/QQQE) 2y K 线图 (v0.6.2 quality boost)

用途:
  - 验证 v0.6.2 SVG + DPI 300 + anti-aliasing 在 4 subplot 上的效果
  - 对比 indices layer vs gold_chart (commodities_futures layer) 的渲染一致性
  - 复用 src/kline.py 的 plot_4_indices + savefig_multi_format

设计:
  - 2x2 subplot: DIA / QQQ / RSP / QQQE
  - lookback 500d (2y) 让 SMA200 滑动平均有完整曲线
  - 输出 PNG@300dpi + SVG 双格式
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt

# 把项目根加进 path, 避免 import src 子包找不到
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.kline import plot_4_indices, savefig_multi_format, DEFAULT_DPI


def main() -> None:
    # v0.6.2: lookback 252 (1y) → 500 (2y) 让 SMA200 滑动平均有完整曲线
    fig = plot_4_indices(
        symbols=["DIA", "QQQ", "RSP", "QQQE"],
        layer="indices",
        lookback_days=500,
        show=False,
    )
    # 替换 suptitle 反映 2y
    fig.suptitle(
        "US Stock Indices — 2y K-line with 5 SMA + Thresholds  (v0.6.2 quality boost)",
        fontsize=15, fontweight="bold", y=0.998,
    )
    # 4 subplot 长标题容易挤, wspace 给点空间
    fig.subplots_adjust(wspace=0.15, hspace=0.35)

    # 写到项目根 output/
    project_root = Path(__file__).resolve().parent.parent
    output_base = project_root / "output" / "indices_2y_2026-07-13"
    written = savefig_multi_format(
        fig, output_base,
        formats=("png", "svg"),
        png_dpi=DEFAULT_DPI,
    )
    plt.close(fig)
    print(f"[indices_chart] saved {len(written)} formats:")
    for p in written:
        print(f"  - {p} ({p.stat().st_size // 1024}KB)")


if __name__ == "__main__":
    main()