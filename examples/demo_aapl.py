"""
examples/demo_aapl.py - AAPL 端到端 demo (Phase 0 gate)

Phase 0 验证 (ROADMAP P0-4 Stop 条件):
  1. OpenBB 能拉 AAPL 1 年 OHLCV (via Clash proxy)
  2. 计算 SMA(20/50/200)
  3. mplfinance 画 K 线 + 均线
  4. 保存 parquet 给 Phase 1 用
  5. 终端打印最新收盘 + 3 个 SMA 值

跑: python examples/demo_aapl.py
输出:
  data/raw/AAPL.parquet
  output/AAPL_demo.png
"""
from __future__ import annotations

# 关键: proxy 必须在 openbb / requests 之前 import
import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src import proxy  # noqa: F401  (副作用: import 时设 HTTP_PROXY)

import io
import matplotlib
matplotlib.use("Agg")  # non-interactive backend, 写文件用
import matplotlib.pyplot as plt
import pandas as pd
from datetime import datetime
from openbb import obb
import mplfinance as mpf


OUTPUT_DIR = PROJECT_ROOT / "output"
DATA_RAW_DIR = PROJECT_ROOT / "data" / "raw"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
DATA_RAW_DIR.mkdir(parents=True, exist_ok=True)


def fetch_aapl(start: str = "2025-01-01", end: str | None = None) -> pd.DataFrame:
    """用 OpenBB Platform SDK 拉 AAPL 历史数据"""
    if end is None:
        end = datetime.now().strftime("%Y-%m-%d")

    print(f"[fetch] 拉 AAPL {start} -> {end} (provider=yfinance)...")
    result = obb.equity.price.historical(
        symbol="AAPL",
        start_date=start,
        end_date=end,
        provider="yfinance",
    )
    df = result.to_dataframe()
    # OpenBB 返回的 index 是普通 Index(值是 datetime.date),
    # 显式转 DatetimeIndex 让 mplfinance 认
    df.index = pd.DatetimeIndex(df.index)
    df.index.name = "date"
    print(f"[fetch] 拿到 {len(df)} 行, {df.index[0].date()} -> {df.index[-1].date()}")
    return df


def add_sma(df: pd.DataFrame, windows: list[int] | None = None) -> pd.DataFrame:
    """加 SMA 指标"""
    if windows is None:
        windows = [20, 50, 200]
    for w in windows:
        df[f"SMA_{w}"] = df["close"].rolling(window=w).mean()
    return df


def save_parquet(df: pd.DataFrame, path: Path) -> None:
    """保存 parquet 缓存"""
    df.to_parquet(path, index=True)
    size_kb = path.stat().st_size / 1024
    print(f"[save] parquet 缓存: {path} ({size_kb:.1f} KB, {len(df)} rows)")


def plot_candles(df: pd.DataFrame, ticker: str, path: Path) -> None:
    """用 mplfinance 画 K 线 + SMA"""
    # mplfinance 要求列名首字母大写
    df_plot = df.rename(columns={
        "open": "Open", "high": "High", "low": "Low",
        "close": "Close", "volume": "Volume",
    })

    sma_plots = []
    sma_colors = {20: "tab:blue", 50: "tab:orange", 200: "tab:red"}
    for w in [20, 50, 200]:
        col = f"SMA_{w}"
        if col in df_plot.columns:
            sma_plots.append(mpf.make_addplot(
                df_plot[col], width=0.7, color=sma_colors[w], label=f"SMA{w}",
            ))

    fig, axes = mpf.plot(
        df_plot,
        type="candle",
        style="charles",
        title=f"{ticker} -- Daily OHLCV + SMA(20/50/200)",
        ylabel="Price ($)",
        ylabel_lower="Volume",
        volume=True,
        addplot=sma_plots,
        figsize=(14, 8),
        returnfig=True,
    )
    fig.savefig(path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    size_kb = path.stat().st_size / 1024
    print(f"[plot] K 线图: {path} ({size_kb:.1f} KB)")


def main() -> int:
    print("=" * 64)
    print(f"us-stock-causal v0.1.0 -- AAPL demo (Phase 0 gate)")
    print(f"Run time: {datetime.now().isoformat()}")
    print(f"Proxy active: {proxy.is_proxied()}")
    print("=" * 64)

    # 1. 拉数据
    df = fetch_aapl(start="2025-01-01")

    # 2. 加指标
    df = add_sma(df)
    n_with_sma = df.dropna(subset=["SMA_20", "SMA_50", "SMA_200"]).shape[0]
    print(f"[indicators] SMA20/50/200 added ({n_with_sma} rows after warmup)")

    # 3. 保存 parquet
    cache_path = DATA_RAW_DIR / "AAPL.parquet"
    save_parquet(df, cache_path)

    # 4. 画 K 线
    chart_path = OUTPUT_DIR / "AAPL_demo.png"
    plot_candles(df, "AAPL", chart_path)

    # 5. 总结
    last = df.iloc[-1]
    last_date = df.index[-1]
    print("\n" + "=" * 64)
    print(f"AAPL 最新数据 (Phase 0 gate 输出):")
    print(f"  日期:    {last_date}")
    print(f"  收盘:    ${last['close']:.2f}")
    print(f"  SMA20:   ${last.get('SMA_20', 0):.2f}")
    print(f"  SMA50:   ${last.get('SMA_50', 0):.2f}")
    print(f"  SMA200:  ${last.get('SMA_200', 0):.2f}")
    if pd.notna(last.get("SMA_200")):
        position = "above" if last["close"] > last["SMA_200"] else "below"
        print(f"  vs SMA200: 收盘 {position} 200日均线")
    print("=" * 64)
    print(f"\n[done] Phase 0 gate 通过")
    print(f"  parquet: {cache_path}")
    print(f"  chart:   {chart_path}")
    print(f"\n下一步: Phase 1 - 扩展到 18 个 ticker (5 标的 + 10 行业 ETF + 3 宏观)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
