"""
src/kline.py - K 线图生成 (Phase 3.1 P3-2 + Phase 6.6 P6-6 + v0.6.1 bug fix + v0.6.2 quality boost)

设计:
  - 1y daily K 线 (默认 252 交易日;gold_chart 改 500d 让 SMA200 有足够数据)
  - 5 SMA (v0.6.1 修复: ax.plot 滑动平均曲线,不是 hlines 单值) + R1/S1:
    * 200 SMA (长期趋势) — **红色实线粗**(核心,user 强调醒目)
    * 100 SMA (中周期) — 紫色实线
    * 150 SMA (中周期 / Gann 半年) — 青色实线
    * 50 SMA (中期) — 橙色点线
    * 20 SMA (短期) — 浅灰细线
    * R1 (短期阻力) — 红色虚线 (hlines,pivot 是常数)
    * S1 (短期支撑) — 绿色虚线 (hlines,pivot 是常数)
  - 4 subplot 2×2 网格: DIA / QQQ / RSP / QQQE (plot_4_indices)

v0.6.0 bug: 用 ax.hlines 画 SMA → 1 根水平线,不是真滑动平均
v0.6.1 fix: 改用 ax.plot 画 close.rolling(w).mean() 时间序列
v0.6.2 quality boost:
  - DPI 200 → 300 (PNG 清晰度)
  - 加 SVG 输出选项 (矢量,任意缩放清晰,文件小)
  - 加 anti-aliasing rcParams (text/lines 边缘更平滑)
  - pil_kwargs={'optimize': True} (PNG 压缩无质量损失)

为什么不用 mplfinance:
  mplfinance 自己管理 figure,无法直接放 2x2 subplot。
  改用 matplotlib 手画蜡烛 + plot,代码多 ~50 行但完全可控。

输出: output/kline_<date>.{png,svg} (PNG 200-400KB@300dpi, SVG 20-60KB)
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

import numpy as np
import pandas as pd
import matplotlib as mpl
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from loguru import logger

from src.thresholds import get_thresholds, load_prices
from matplotlib.ticker import MaxNLocator, FuncFormatter


# v0.6.2: 强制开 anti-aliasing (栅格化输出的边缘更平滑)
# 默认 text.antialiased=True 但 lines.antialiased 偶发被覆盖
mpl.rcParams['lines.antialiased'] = True
mpl.rcParams['text.antialiased'] = True
mpl.rcParams['patch.antialiased'] = True


def _set_ylim_52w_padding(ax: plt.Axes, df_visible: pd.DataFrame, padding: float = 0.20) -> None:
    """v0.6.8h: 设置 ylim 为 52w high+20% / 52w low-20% (User 建议)

    User 反馈: 默认 ylim 范围太大 (黄金图 2000-5800), 价格离 y 轴太远。
    fix: 用 visible window 的 52w (252 trading days) high/low, 各 padding 20%。

    Tick: MaxNLocator nbins=8 steps=[1,2,5,10] 自动选 1/2/5 × 10^n, 6-10 个 ticks 视觉舒服。
    """
    if len(df_visible) < 2:
        return
    window = min(len(df_visible), 252)
    high_52w = float(df_visible["high"].iloc[-window:].max())
    low_52w = float(df_visible["low"].iloc[-window:].min())
    if high_52w <= 0 or low_52w <= 0 or high_52w <= low_52w:
        return  # 数据异常, 不动 ylim
    ymin = low_52w * (1 - padding)
    ymax = high_52w * (1 + padding)
    ax.set_ylim(ymin, ymax)
    # 合理 ticks
    ax.yaxis.set_major_locator(MaxNLocator(nbins=8, steps=[1, 2, 5, 10]))
    # 整数价格格式 (跟 finance 显示习惯一致, 不显示 1.234e3)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{x:,.0f}"))

# v0.6.2: 默认 DPI 200 → 300 (PNG 像素密度提升 2.25x)
DEFAULT_DPI = 300


# 颜色 (Plotly 风格,跟 5 段报告配色一致)
COLOR_UP = "#26a69a"     # 涨绿
COLOR_DOWN = "#ef5350"   # 跌红
# v0.6.0 (P6-6): 200 SMA 改成红色醒目,user 强调 "200 日均线做成红色醒目"
COLOR_SMA200 = "#d32f2f" # 200 SMA 红 (粗实线) — 长期趋势核心
COLOR_SMA150 = "#0097a7" # 150 SMA 青 (实线) — Gann 半年线
COLOR_SMA100 = "#7b1fa2" # 100 SMA 紫 (实线) — 中周期
COLOR_SMA50 = "#f57c00"  # 50 SMA 橙 (点线) — 中期
COLOR_SMA20 = "#9e9e9e"  # 20 SMA 灰 (细线) — 短期
COLOR_R1 = "#d32f2f"     # 阻力红虚线
COLOR_S1 = "#388e3c"     # 支撑绿虚线

# v0.6.4 (P6-1) 事件线颜色: FOMC 红 / CPI 蓝 / NFP 绿 / 其他灰
COLOR_EVENT_FOMC = "#d32f2f"   # FOMC 红 (跟 200 SMA 同色, 区分靠线型)
COLOR_EVENT_CPI = "#1976d2"    # CPI 蓝
COLOR_EVENT_NFP = "#388e3c"    # NFP 绿 (跟 S1 同色)
COLOR_EVENT_OTHER = "#757575"  # PCE/PPI 等灰

EVENT_COLOR_MAP = {
    "FOMC": COLOR_EVENT_FOMC,
    "CPI": COLOR_EVENT_CPI,
    "NFP": COLOR_EVENT_NFP,
}


def _draw_events(ax: plt.Axes, df: pd.DataFrame, events: Optional[list] = None) -> int:
    """v0.6.4 (P6-1): 在 K 线上叠加 CPI/FOMC 事件垂直线

    events: list[MacroEvent] from src.events
    如果 events=None, 自动 load_calendar() 过滤
    返回画的线条数 (测试用)
    """
    from src.events import load_calendar, MacroEvent  # 避免循环 import
    if events is None:
        events = load_calendar()
    if not events:
        return 0

    first_date = df.index[0]
    last_date = df.index[-1]
    n_drawn = 0
    seen_kinds: set[str] = set()  # 避免图例重复
    for ev in events:
        # 事件日期转 Timestamp, 检查是否在图表范围内
        ev_ts = pd.Timestamp(ev.date)
        if ev_ts < first_date or ev_ts > last_date:
            continue
        color = EVENT_COLOR_MAP.get(ev.kind, COLOR_EVENT_OTHER)
        # v0.6.4: 区分 FOMC (实线, 最关键) vs CPI (虚线) vs NFP (点线)
        linestyle_map = {"FOMC": "-", "CPI": "--", "NFP": ":"}
        ls = linestyle_map.get(ev.kind, ":")
        # 用 axvline 返回的 Line2D 加到 legend (只第一次画该 kind 时)
        line_label = f"{ev.kind} event" if ev.kind not in seen_kinds else None
        seen_kinds.add(ev.kind)
        ax.axvline(
            ev_ts, color=color, linestyle=ls, linewidth=1.2, alpha=0.7,
            zorder=2,  # 在 grid 之上, 蜡烛之下
            label=line_label,
        )
        n_drawn += 1
    return n_drawn


def _draw_candles(ax: plt.Axes, df: pd.DataFrame) -> None:
    """在 ax 上画 OHLC 蜡烛

    v0.6.6 (P6-5): 给每根 candle 设 gid 前缀 (candle-wick-YYYY-MM-DD / candle-body-...),
    后处理 _inject_ohlcv_hover 按 gid 找元素加 <title>

    注意: matplotlib 的 ax.vlines/hlines 返回 LineCollection, 不支持 gid 参数
    → 用 ax.plot 画 1 段 Line2D, 然后 set_gid() 显式设
    """
    for idx, row in df.iterrows():
        is_up = row["close"] >= row["open"]
        color = COLOR_UP if is_up else COLOR_DOWN
        date_str = idx.strftime("%Y-%m-%d")

        # Wick (high-low) — ax.plot 2 点, 显式 set_gid
        wick_line, = ax.plot(
            [idx, idx], [row["low"], row["high"]],
            color=color, linewidth=0.6, alpha=0.9,
        )
        wick_line.set_gid(f"candle-wick-{date_str}")

        # Body (open-close rectangle)
        body_height = abs(row["close"] - row["open"])
        if body_height < 0.01:
            # Doji — 极小 body,画横线
            body_line, = ax.plot(
                [idx - pd.Timedelta(hours=12), idx + pd.Timedelta(hours=12)],
                [row["close"], row["close"]],
                color=color, linewidth=0.9,
            )
            body_line.set_gid(f"candle-body-{date_str}")
        else:
            body_bottom = min(row["close"], row["open"])
            bar_container = ax.bar(
                idx,
                body_height,
                bottom=body_bottom,
                width=pd.Timedelta(hours=22),
                color=color,
                alpha=0.9,
                edgecolor=color,
                linewidth=0,
            )
            # ax.bar 返回 BarContainer, 给每个 Rectangle 设 gid
            for rect in bar_container:
                rect.set_gid(f"candle-body-{date_str}")


def _draw_thresholds(ax: plt.Axes, df: pd.DataFrame, symbol: str, show_50sma: bool = True, layer: str = "indices") -> None:
    """在 ax 上画 5 SMA (滑动平均曲线) + R1/S1 (v0.6.1 P6-6 bug fix)

    v0.6.0 错误: 用 ax.hlines 画 SMA → 画成 1 根水平线,不是真滑动平均
    v0.6.1 修: 用 ax.plot 画 close.rolling(w).mean() 时间序列

    R1/S1 仍是 hlines (pivot 是不变的常数,不是时间序列)
    """
    t = get_thresholds(symbol, layer=layer)

    smas_last = t["smas"]  # {sma_20: float, sma_50: float, ...} 最近值
    first_date = df.index[0]
    last_date = df.index[-1]

    # SMA 样式表: (color, linewidth, linestyle, alpha, zorder)
    sma_styles = [
        ("sma_200", COLOR_SMA200, 2.4, "-", 1.0, 5),  # 红粗实线,最上层
        ("sma_150", COLOR_SMA150, 1.6, "-", 0.85, 3),
        ("sma_100", COLOR_SMA100, 1.6, "-", 0.85, 3),
        ("sma_50",  COLOR_SMA50,  1.2, ":", 0.7, 2),
        ("sma_20",  COLOR_SMA20,  0.8, ":", 0.5, 1),
    ]

    close = df["close"]
    for key, color, lw, ls, alpha, zorder in sma_styles:
        last_val = smas_last.get(key)
        if last_val is None or pd.isna(last_val):
            continue
        # 跳过 50 SMA 如果 show_50sma=False
        if key == "sma_50" and not show_50sma:
            continue
        w = int(key.split("_")[1])
        sma_series = close.rolling(w).mean()
        # 滑动平均曲线 — 每天的均值,不是单值
        ax.plot(
            df.index, sma_series,
            color=color, linewidth=lw, linestyle=ls, alpha=alpha,
            label=f"{w} SMA ${last_val:.2f}",
            zorder=zorder,
        )

    # R1 / S1 仍是 hlines (pivot 是常数)
    r1 = t["pivots"]["r1"]
    s1 = t["pivots"]["s1"]
    ax.hlines(
        r1, first_date, last_date,
        colors=COLOR_R1, linestyles="--", linewidth=1.2,
        label=f"R1 ${r1:.2f}",
    )
    ax.hlines(
        s1, first_date, last_date,
        colors=COLOR_S1, linestyles="--", linewidth=1.2,
        label=f"S1 ${s1:.2f}",
    )


def plot_single(
    symbol: str,
    ax: plt.Axes,
    layer: str = "indices",
    lookback_days: int = 252,
    show_50sma: bool = True,
    compact_title: bool = False,
) -> plt.Axes:
    """Plot single symbol K-line on given axes

    compact_title (v0.6.3): 4-subplot 时用紧凑模式, 只显示 SMA200 + 52w

    v0.6.8g (P6-7): SMA 连续性 fix — 不要再切片 df (df = df.iloc[-lookback_days:])。
    原因: 200 SMA 滚动 200 天, 切片 1y 后前 200 天没值, 200 SMA 要到 2026-02 才出现。
    fix: 用 cache 全量数据画, xlim 限定最后 lookback_days, 让 SMA 从图一开始就连续。
    要求: cache 至少 lookback_days + 200 (2y 缓存能保证 1y 图 200 SMA 全程有效)。
    """
    df = load_prices(symbol, layer)

    # v0.6.8g: 不再切片! 画全量数据, xlim 限定显示窗口
    # 这样 200 SMA 滚动 200 天有 warmup, 1y 图全程有效
    if len(df) < lookback_days:
        # cache 不足, fallback 老逻辑 (宁可部分 SMA 缺, 不报错)
        df = df.copy()
    else:
        df = df.copy()
        # 设置 xlim 到最后 lookback_days 窗口
        visible_start = df.index[-lookback_days]
        ax.set_xlim(visible_start, df.index[-1])

    # 蜡烛
    _draw_candles(ax, df)
    # 阈值线
    _draw_thresholds(ax, df, symbol, show_50sma=show_50sma, layer=layer)
    # v0.6.4 (P6-1) 事件线: FOMC / CPI / NFP 垂直线
    _draw_events(ax, df)
    # v0.6.8h (P6-7.5): ylim 用 52w high/low ±20% (User 反馈默认 ylim 离价格太远)
    if len(df) >= 2:
        _set_ylim_52w_padding(ax, df)

    # 标题 — 5 SMA 全显示 (v0.6.0) + 实际 lookback period (v0.6.3 fix)
    t = get_thresholds(symbol, layer=layer)
    smas = t["smas"]
    vs = t["vs_sma"]
    pos52w = t["range_52w"]["position_pct"]
    # period 字符串: 252d → 1y, 500d → 2y, 126d → 6m (v0.6.3 用 round 不用 //)
    if lookback_days >= 252:
        period = f"{round(lookback_days / 252)}y"
    elif lookback_days >= 21:
        period = f"{round(lookback_days / 21)}mo"
    else:
        period = f"{lookback_days}d"
    # 拼标题
    # - compact_title (4-subplot 模式): 只显示 close + SMA200 + 52w
    # - 全显示模式 (单 subplot): close + 5 SMA + 52w
    if compact_title:
        s200_pct = vs.get("sma_200", {}).get("pct")
        if s200_pct is not None and not pd.isna(s200_pct):
            title = f"{symbol}  {period}  |  USD {t['last_close']:.2f}  |  SMA200 {s200_pct:+.1f}%  |  52w {pos52w}%"
        else:
            title = f"{symbol}  {period}  |  USD {t['last_close']:.2f}  |  52w {pos52w}%"
        # v0.6.3 fix: matplotlib 3.11.0 + loc="left" 让 title 消失, 改默认 (center)
        ax.set_title(title, fontsize=10, fontweight="bold", pad=8)
    else:
        parts = [f"close USD {t['last_close']:.2f}"]
        for w in [20, 50, 100, 150, 200]:
            v = smas.get(f"sma_{w}")
            p = vs.get(f"sma_{w}", {}).get("pct")
            if v is not None and p is not None and not pd.isna(v):
                parts.append(f"SMA{w} {p:+.1f}%")
        parts.append(f"52w {pos52w}%")
        title = f"{symbol}  {period}  |  " + "  ".join(parts)
        ax.set_title(title, fontsize=10, fontweight="bold", pad=8)
    ax.set_ylabel("Price (USD)", fontsize=8)
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
        # v0.6.3: 4-subplot 用 compact_title (只显 SMA200 + 52w, 避免标题挤/截)
        plot_single(sym, ax, layer=layer, lookback_days=lookback_days, compact_title=True)

    plt.tight_layout(rect=[0, 0, 1, 0.99])

    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        savefig_multi_format(
            fig, output_path,
            formats=("png", "svg"),
            png_dpi=DEFAULT_DPI,
        )

    if show:
        plt.show()
    else:
        plt.close(fig)

    return fig


def _inject_ohlcv_hover(svg_path: Path, fig: plt.Figure) -> int:
    """
    v0.6.6 (P6-5): 给 SVG 加 <title> 标签, 浏览器 hover 显示 OHLCV

    matplotlib 的 set_gid() 设到 SVG 的 `id` 属性 (不是 `gid`), 蜡烛
    patch 在 SVG 输出里是 `<g id="candle-body-YYYY-MM-DD">...</g>`, 直接按 id 找

    Args:
        svg_path: 写完的 SVG 路径
        fig: matplotlib Figure (不直接用, 但保留接口一致)

    Returns: 注入的 <title> 数量
    """
    from lxml import etree
    import re as _re
    import matplotlib.dates as mdates

    # 解析 SVG
    parser = etree.XMLParser(remove_blank_text=False)
    tree = etree.parse(str(svg_path), parser)
    root = tree.getroot()
    ns = "{http://www.w3.org/2000/svg}"

    # 找所有 id="candle-body-YYYY-MM-DD" 的元素
    # matplotlib 把 gid="candle-body-..." 输出成 id="..." (svg id 属性, 不是 gid)
    n_injected = 0
    for el in root.iter():
        el_id = el.get("id") or ""
        if not el_id.startswith("candle-body-"):
            continue
        date_str = el_id.replace("candle-body-", "")
        # 从 ax.patches 找对应 candle (按 x 位置)
        # 简单方案: 用 ax.patches 找 gid="candle-body-{date_str}" 的
        # 但 fig 在 savefig 之后, ax 还有 patch 数据吗? — 有, fig 一直持有
        candle = None
        try:
            ax = fig.axes[0]
            for patch in ax.patches:
                if (patch.get_gid() or "") == f"candle-body-{date_str}":
                    candle = patch
                    break
        except Exception:
            pass
        if candle is None:
            continue
        body_low = float(candle.get_y())
        body_high = float(candle.get_y() + candle.get_height())
        title_text = (
            f"{date_str}  body: USD {body_low:.2f} - USD {body_high:.2f}"
        )
        title_el = etree.SubElement(el, f"{ns}title")
        title_el.text = title_text
        n_injected += 1

    if n_injected > 0:
        tree.write(str(svg_path), xml_declaration=True, encoding="utf-8")
        logger.info(f"[kline] injected {n_injected} OHLCV hover titles into {svg_path.name}")
    return n_injected


def savefig_multi_format(
    fig: plt.Figure,
    output_path: Path,
    formats: tuple[str, ...] = ("png", "svg"),
    png_dpi: int = DEFAULT_DPI,
) -> list[Path]:
    """
    v0.6.2 quality boost: 多格式输出, 兼顾清晰度 (SVG) + 兼容性 (PNG)

    PNG: DPI 300 + pil_kwargs={'optimize': True} 压缩
    SVG: 矢量, 任意缩放清晰, 文件 20-60KB
    PDF: 同矢量, 适合印刷

    写多文件: chart.png + chart.svg 同 stem
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    for fmt in formats:
        if fmt == "png":
            out = output_path.with_suffix(".png")
            fig.savefig(
                out, dpi=png_dpi, bbox_inches="tight", facecolor="white",
                pil_kwargs={"optimize": True},
            )
            written.append(out)
            logger.info(f"[kline] saved PNG@{png_dpi}dpi: {out} ({out.stat().st_size // 1024}KB)")
        elif fmt == "svg":
            out = output_path.with_suffix(".svg")
            fig.savefig(out, bbox_inches="tight", facecolor="white")
            # v0.6.6 (P6-5): post-process SVG 加 <title> 标签, 浏览器 hover 显示 OHLCV
            try:
                _inject_ohlcv_hover(out, fig)
            except Exception as e:
                logger.warning(f"[kline] hover inject failed (non-fatal): {e}")
            written.append(out)
            logger.info(f"[kline] saved SVG (vector): {out} ({out.stat().st_size // 1024}KB)")
        elif fmt == "pdf":
            out = output_path.with_suffix(".pdf")
            fig.savefig(out, bbox_inches="tight", facecolor="white")
            written.append(out)
            logger.info(f"[kline] saved PDF (vector): {out} ({out.stat().st_size // 1024}KB)")
        else:
            logger.warning(f"[kline] unknown format: {fmt}, skipped")

    return written


if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    plot_4_indices(show=True)
