"""src/performance_dashboard.py - 全标的 1d 涨跌幅总览 (v0.6.8h 新增)

设计:
- 1 张 horizontal bar chart: 1d % change for all 报告里的标的
- 1 张 markdown table: 中文名 / 现价 USD / 1d 涨跌幅 / 52w 高低

数据源: cache parquet (data/raw/{layer}/{safe_name}.parquet)
涵盖标的 (默认):
  - 4 指数 (indices): DIA / QQQ / RSP / QQQE
  - 11 行业 (sectors): XLK / XLF / XLV / XLY / XLP / XLE / XLI / XLB / XLU / XLC / XLRE
  - 2 黄金 (commodities_futures + commodities_spot_etf): GC=F / GLD
  - 3 宏观 (macro): ^VIX / ^TNX / DX-Y.NYB

颜色:
- 涨 (正): 绿色 (#26a69a) 跟 K 线涨绿一致
- 跌 (负): 红色 (#ef5350) 跟 K 线跌红一致
- 横轴 0% 一根虚线
"""
from __future__ import annotations
import sys
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]

import pandas as pd
import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, MaxNLocator
from loguru import logger

from src.thresholds import load_prices


# 中英文对照表 (用于表格显示)
SYMBOL_CN_NAMES = {
    # 指数
    "DIA":   "道琼斯 30 指数 ETF",
    "QQQ":   "纳斯达克 100 ETF",
    "RSP":   "标普 500 等权 ETF",
    "QQQE":  "纳斯达克 100 等权 ETF",
    # 行业
    "XLK":   "信息技术",
    "XLF":   "金融",
    "XLV":   "医疗保健",
    "XLY":   "可选消费",
    "XLP":   "必需消费",
    "XLE":   "能源",
    "XLI":   "工业",
    "XLB":   "材料",
    "XLU":   "公用事业",
    "XLC":   "通信服务",
    "XLRE":  "房地产",
    # 黄金
    "GC=F":  "黄金期货 (COMEX)",
    "GLD":   "黄金 ETF (SPDR)",
    # 宏观
    "^VIX":  "波动率指数 (VIX)",
    "^TNX":  "10 年期美债收益率",
    "DXY":   "美元指数 (DXY)",
}

# 颜色
COLOR_UP = "#26a69a"   # 涨绿 (跟 K 线一致)
COLOR_DOWN = "#ef5350" # 跌红 (跟 K 线一致)
COLOR_NEUTRAL = "#9e9e9e"  # 0% 灰


# 默认全标的 (layer, symbol) — 报告常用
DEFAULT_SYMBOLS: list[tuple[str, str]] = [
    # 4 指数
    ("indices", "DIA"),
    ("indices", "QQQ"),
    ("indices", "RSP"),
    ("indices", "QQQE"),
    # 11 行业 (按字母顺序)
    ("sectors", "XLB"),
    ("sectors", "XLC"),
    ("sectors", "XLE"),
    ("sectors", "XLF"),
    ("sectors", "XLI"),
    ("sectors", "XLK"),
    ("sectors", "XLP"),
    ("sectors", "XLRE"),
    ("sectors", "XLU"),
    ("sectors", "XLV"),
    ("sectors", "XLY"),
    # 2 黄金
    ("commodities_futures", "GC=F"),
    ("commodities_spot_etf", "GLD"),
    # 3 宏观
    ("macro", "^VIX"),
    ("macro", "^TNX"),
    ("macro", "DXY"),
]


def compute_1d_change(symbol: str, layer: str) -> Optional[dict]:
    """算 1d 涨跌幅 + 52w 高低 + 现价

    Returns:
        dict {symbol, layer, last_close, prev_close, change_pct, high_52w, low_52w}
        or None if data missing
    """
    try:
        df = load_prices(symbol, layer)
    except FileNotFoundError:
        logger.warning(f"[perf] {symbol} ({layer}) 无 cache, 跳过")
        return None
    if df is None or len(df) < 2:
        return None
    last_close = float(df["close"].iloc[-1])
    prev_close = float(df["close"].iloc[-2])
    change_pct = (last_close - prev_close) / prev_close * 100

    # 52w = 252 trading days
    window_52w = min(len(df), 252)
    high_52w = float(df["high"].iloc[-window_52w:].max())
    low_52w = float(df["low"].iloc[-window_52w:].min())

    return {
        "symbol": symbol,
        "layer": layer,
        "last_close": last_close,
        "prev_close": prev_close,
        "change_pct": change_pct,
        "high_52w": high_52w,
        "low_52w": low_52w,
    }


def collect_performance(symbols: Optional[list[tuple[str, str]]] = None) -> list[dict]:
    """收集所有标的的 1d 涨跌幅 + 52w 数据"""
    if symbols is None:
        symbols = DEFAULT_SYMBOLS
    results = []
    for layer, sym in symbols:
        r = compute_1d_change(sym, layer)
        if r is not None:
            results.append(r)
    return results


def plot_performance_dashboard(
    ax: plt.Axes,
    symbols: Optional[list[tuple[str, str]]] = None,
    top_n: Optional[int] = None,
) -> plt.Axes:
    """画 1 张 1d 涨跌幅 horizontal bar chart

    按涨跌幅降序 (涨在上, 跌在下), 颜色按方向
    v0.6.8h hotfix 2: y-tick 只放 symbol (1 行), 中文名做 annotation 放 bar 末端
    解决 20 标的时 y-tick 2 行 label 垂直重叠问题
    """
    results = collect_performance(symbols)
    if not results:
        ax.text(0.5, 0.5, "无数据", ha="center", va="center", transform=ax.transAxes)
        return ax

    # 按涨跌幅降序
    results.sort(key=lambda r: r["change_pct"], reverse=True)

    if top_n is not None and len(results) > top_n:
        # 涨 top_n + 跌 top_n
        top_up = results[:top_n]
        top_dn = results[-top_n:]
        results = top_up + top_dn
        results.sort(key=lambda r: r["change_pct"], reverse=True)

    labels_cn = [SYMBOL_CN_NAMES.get(r["symbol"], r["symbol"]) for r in results]
    values = [r["change_pct"] for r in results]
    colors = [COLOR_UP if v > 0 else COLOR_DOWN if v < 0 else COLOR_NEUTRAL for v in values]

    # 横向 bar
    y_pos = list(range(len(results)))
    bars = ax.barh(y_pos, values, color=colors, alpha=0.85, edgecolor="white", linewidth=0.5)

    # v0.6.8h hotfix 2: y-tick 只放 symbol (1 行, 短), 中文名 annotation 放 bar 末端
    # 这样 y-tick 不会因为 2 行 label 在 16px/row 时垂直重叠
    ax.set_yticks(y_pos)
    ax.set_yticklabels([r["symbol"] for r in results], fontsize=8, fontfamily="monospace")
    ax.tick_params(axis="y", pad=4)

    # 0% 参考线
    ax.axvline(0, color=COLOR_NEUTRAL, linestyle="--", linewidth=0.8, alpha=0.6)

    # X 轴格式: 百分比
    def pct_fmt(x, _):
        return f"{x:+.1f}%"
    ax.xaxis.set_major_formatter(FuncFormatter(pct_fmt))
    ax.xaxis.set_major_locator(MaxNLocator(nbins=6, steps=[1, 2, 5, 10]))
    ax.tick_params(axis="x", labelsize=8)

    # Bar 末端显示百分比 + 中文名
    xmax = max(values) if values else 0
    xmin = min(values) if values else 0
    x_range = max(abs(xmax), abs(xmin), 0.5)
    for i, (bar, val, name_cn) in enumerate(zip(bars, values, labels_cn)):
        # 缩短中文名 (去掉括号注释, 比如 "黄金期货 (COMEX)" → "黄金期货")
        name_short = name_cn.split(" (")[0]
        if val >= 0:
            # bar 右端: 百分比 + 短中文名
            ax.text(val + x_range * 0.01, i, f"{val:+.2f}%  {name_short}",
                    va="center", ha="left", fontsize=7, color="#333")
        else:
            # bar 左端: 短中文名 + 百分比 (中文名在左, 数字在右贴近 bar)
            ax.text(val - x_range * 0.01, i, f"{name_short}  {val:+.2f}%",
                    va="center", ha="right", fontsize=7, color="#333")

    # 标题
    ax.set_title(f"全标的 1d 涨跌幅总览 ({len(results)} 只)", fontsize=11, fontweight="bold", pad=8)
    ax.set_xlabel("1d 涨跌幅", fontsize=9)
    ax.grid(axis="x", alpha=0.3, linestyle=":", linewidth=0.5)
    ax.set_axisbelow(True)

    # 给右端 annotation 留空间
    xlim_left, xlim_right = ax.get_xlim()
    # 加宽 xlim 给 annotation 留位置
    if xlim_right > 0:
        ax.set_xlim(xlim_left, xlim_right * 1.35)
    if xlim_left < 0:
        ax.set_xlim(xlim_left * 1.35, xlim_right)

    # 反转 Y 轴 (涨在上)
    ax.invert_yaxis()

    return ax


def render_performance_table(symbols: Optional[list[tuple[str, str]]] = None) -> str:
    """渲染中文 Google-Finance 风格表格 (markdown)

    | 中文名 | 标的 | 现价 USD | 1d 涨跌幅 | 52w 高 | 52w 低 | 当日位置 |
    |--------|------|----------|-----------|--------|--------|----------|
    | 信息技术 | XLK | $234.56 | +1.23% | $240.00 | $180.00 | 73% |
    ...
    """
    results = collect_performance(symbols)
    if not results:
        return "无数据"

    results.sort(key=lambda r: r["change_pct"], reverse=True)

    lines = [
        "| 中文名 | 标的 | 现价 (USD) | 1d 涨跌幅 | 52w 高 | 52w 低 | 区间位置 |",
        "|--------|------|-----------:|----------:|-------:|-------:|---------:|",
    ]
    for r in results:
        name = SYMBOL_CN_NAMES.get(r["symbol"], r["symbol"])
        last = r["last_close"]
        pct = r["change_pct"]
        hi = r["high_52w"]
        lo = r["low_52w"]
        # 区间位置 (0-100%): (last - low) / (high - low)
        if hi > lo:
            pos = (last - lo) / (hi - lo) * 100
        else:
            pos = 50.0
        # 涨/跌 ASCII 标记 (GBK 兼容, 不用 emoji)
        arrow = "▲" if pct > 0 else "▼" if pct < 0 else "─"
        lines.append(
            f"| {name} | `{r['symbol']}` | {last:,.2f} | {arrow} {pct:+.2f}% | {hi:,.2f} | {lo:,.2f} | {pos:.0f}% |"
        )

    return "\n".join(lines)


def render_performance_table_html(symbols: Optional[list[tuple[str, str]]] = None) -> str:
    """HTML 风格 (Google Finance 风, 涨绿跌红 inline color)"""
    results = collect_performance(symbols)
    if not results:
        return "<p>无数据</p>"

    results.sort(key=lambda r: r["change_pct"], reverse=True)

    parts = [
        '<table style="border-collapse: collapse; width: 100%; font-size: 13px;">',
        '<thead><tr style="background: #f5f5f5; border-bottom: 2px solid #ddd;">',
        '<th style="text-align: left; padding: 8px;">中文名</th>',
        '<th style="text-align: left; padding: 8px;">标的</th>',
        '<th style="text-align: right; padding: 8px;">现价 (USD)</th>',
        '<th style="text-align: right; padding: 8px;">1d 涨跌幅</th>',
        '<th style="text-align: right; padding: 8px;">52w 高</th>',
        '<th style="text-align: right; padding: 8px;">52w 低</th>',
        '<th style="text-align: right; padding: 8px;">区间位置</th>',
        '</tr></thead><tbody>',
    ]
    for r in results:
        name = SYMBOL_CN_NAMES.get(r["symbol"], r["symbol"])
        last = r["last_close"]
        pct = r["change_pct"]
        hi = r["high_52w"]
        lo = r["low_52w"]
        pos = (last - lo) / (hi - lo) * 100 if hi > lo else 50.0
        if pct > 0:
            color = "#137333"  # Google green
            bg = "#e6f4ea"
        elif pct < 0:
            color = "#c5221f"  # Google red
            bg = "#fce8e6"
        else:
            color = "#5f6368"
            bg = "#f8f9fa"
        parts.append(
            f'<tr style="border-bottom: 1px solid #eee;">'
            f'<td style="padding: 6px 8px;">{name}</td>'
            f'<td style="padding: 6px 8px;"><code>{r["symbol"]}</code></td>'
            f'<td style="padding: 6px 8px; text-align: right;">{last:,.2f}</td>'
            f'<td style="padding: 6px 8px; text-align: right; color: {color}; background: {bg}; font-weight: 500;">{pct:+.2f}%</td>'
            f'<td style="padding: 6px 8px; text-align: right;">{hi:,.2f}</td>'
            f'<td style="padding: 6px 8px; text-align: right;">{lo:,.2f}</td>'
            f'<td style="padding: 6px 8px; text-align: right;">{pos:.0f}%</td>'
            f'</tr>'
        )
    parts.append('</tbody></table>')
    return "\n".join(parts)
