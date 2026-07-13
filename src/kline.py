"""
src/kline.py - K 线图生成 (Phase 3.1 P3-2)

设计:
  - 1y daily K 线 (默认 252 交易日)
  - 3 条关键线:
    * 200 SMA (长期趋势) — 蓝色实线
    * R1 (短期阻力, floor trader pivot) — 红色虚线
    * S1 (短期支撑, floor trader pivot) — 绿色虚线
  - 50 SMA (中期趋势) — 橙色点线 (可选)
  - 4 subplot 2×2 网格: DIA / QQQ / RSP / QQQE

为什么不用 mplfinance:
  mplfinance 自己管理 figure,无法直接放 2x2 subplot。
  改用 matplotlib 手画蜡烛 + hlines,代码多 ~50 行但完全可控。

输出: output/kline_<date>.png (~300-500 KB)
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from loguru import logger

from src.thresholds import get_thresholds, load_prices


# 颜色 (Plotly 风格,跟 5 段报告配色一致)
COLOR_UP = "#26a69a"     # 涨绿
COLOR_DOWN = "#ef5350"   # 跌红
COLOR_SMA200 = "#1976d2" # 200 SMA 蓝
COLOR_SMA50 = "#f57c00"  # 50 SMA 橙
COLOR_R1 = "#d32f2f"     # 阻力红虚线
COLOR_S1 = "#388e3c"     # 支撑绿虚线


def _draw_candles(ax: plt.Axes, df: pd.DataFrame) -> None:
    """在 ax 上画 OHLC 蜡烛"""
    for idx, row in df.iterrows():
        is_up = row["close"] >= row["open"]
        color = COLOR_UP if is_up else COLOR_DOWN

        # Wick (high-low)
        ax.vlines(idx, row["low"], row["high"], color=color, linewidth=0.6, alpha=0.9)

        # Body (open-close rectangle)
        body_height = abs(row["close"] - row["open"])
        if body_height < 0.01:
            # Doji — 极小 body,画横线
            ax.hlines(
                row["close"],
                idx - pd.Timedelta(hours=12),
                idx + pd.Timedelta(hours=12),
                color=color,
                linewidth=0.9,
            )
        else:
            body_bottom = min(row["close"], row["open"])
            ax.bar(
                idx,
                body_height,
                bottom=body_bottom,
                width=pd.Timedelta(hours=22),
                color=color,
                alpha=0.9,
                edgecolor=color,
                linewidth=0,
            )


def _draw_thresholds(ax: plt.Axes, df: pd.DataFrame, symbol: str, show_50sma: bool = True) -> None:
    """在 ax 上画 3 (4) 条关键阈值线"""
    t = get_thresholds(symbol)

    # 实际 SMA 值在 t["smas"],vs_sma 只有百分比
    s200 = t["smas"]["sma_200"]
    r1 = t["pivots"]["r1"]
    s1 = t["pivots"]["s1"]
    s50 = t["smas"].get("sma_50")

    first_date = df.index[0]
    last_date = df.index[-1]

    # 200 SMA — 蓝实线 (主)
    ax.hlines(
        s200, first_date, last_date,
        colors=COLOR_SMA200, linestyles="-", linewidth=1.6,
        label=f"200 SMA ${s200:.2f}",
    )
    # R1 — 红虚线
    ax.hlines(
        r1, first_date, last_date,
        colors=COLOR_R1, linestyles="--", linewidth=1.2,
        label=f"R1 ${r1:.2f}",
    )
    # S1 — 绿虚线
    ax.hlines(
        s1, first_date, last_date,
        colors=COLOR_S1, linestyles="--", linewidth=1.2,
        label=f"S1 ${s1:.2f}",
    )
    # 50 SMA — 橙点线 (可选)
    if show_50sma and s50 is not None:
        ax.hlines(
            s50, first_date, last_date,
            colors=COLOR_SMA50, linestyles=":", linewidth=1.0,
            label=f"50 SMA ${s50:.2f}",
            alpha=0.7,
        )


def plot_single(
    symbol: str,
    ax: plt.Axes,
    layer: str = "indices",
    lookback_days: int = 252,
    show_50sma: bool = True,
) -> plt.Axes:
    """Plot single symbol K-line on given axes"""
    df = load_prices(symbol, layer)
    df = df.iloc[-lookback_days:].copy()

    # 蜡烛
    _draw_candles(ax, df)
    # 阈值线
    _draw_thresholds(ax, df, symbol, show_50sma=show_50sma)

    # 标题
    t = get_thresholds(symbol)
    s200_pct = t["vs_sma"]["sma_200"]["pct"]
    pos52w = t["range_52w"]["position_pct"]
    title = (
        f"{symbol}  1y  |  close ${t['last_close']}  |  "
        f"200 SMA {s200_pct:+.2f}%  |  52w {pos52w}%"
    )
    ax.set_title(title, fontsize=10, fontweight="bold", loc="left", pad=8)
    ax.set_ylabel("Price ($)", fontsize=8)
    ax.legend(loc="upper left", fontsize=7, framealpha=0.85, ncol=2)
    ax.grid(True, alpha=0.3, linestyle="-", linewidth=0.5)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=0, fontsize=7)
    plt.setp(ax.yaxis.get_majorticklabels(), fontsize=7)

    # Y 轴留点 margin,让标签不全贴边
    y_min, y_max = ax.get_ylim()
    y_range = y_max - y_min
    ax.set_ylim(y_min - y_range * 0.02, y_max + y_range * 0.05)

    return ax


def plot_4_indices(
    symbols: Optional[list[str]] = None,
    layer: str = "indices",
    lookback_days: int = 252,
    output_path: Optional[Path] = None,
    show: bool = False,
) -> plt.Figure:
    """Plot 4 indices in 2×2 grid"""
    if symbols is None:
        symbols = ["DIA", "QQQ", "RSP", "QQQE"]

    fig, axes = plt.subplots(2, 2, figsize=(16, 9))
    fig.suptitle(
        "US Stock Indices — 1y K-line with Key Thresholds  (Phase 3.1 P3-2)",
        fontsize=14, fontweight="bold", y=0.998,
    )

    for ax, sym in zip(axes.flat, symbols):
        plot_single(sym, ax, layer=layer, lookback_days=lookback_days)

    plt.tight_layout(rect=[0, 0, 1, 0.99])

    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(output_path, dpi=120, bbox_inches="tight", facecolor="white")
        logger.info(f"[kline] saved: {output_path}")

    if show:
        plt.show()
    else:
        plt.close(fig)

    return fig


if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    plot_4_indices(show=True)
