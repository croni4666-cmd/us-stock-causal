"""
src/macro.py - 宏观情绪 1 行 (Phase 3.2 P3-3)

设计:
  - 顶部 1 行: VIX / 10Y (^TNX) / DXY (DX-Y.NYB) 当日值 + 1 日变化
  - 30 秒读完的整体市场情绪
  - 跟 5 段报告 + K 线组合 = 30s/5min/15min 三档阅读

数据来源: src.cache / data/raw/macro/<safe_name>.parquet
计算: 简单 % change, 不做平滑
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd
from loguru import logger

from src.thresholds import load_prices, safe_name


# 顶部情绪 1 行 — 核心宏观指标 (3 个)
# 注意: symbol 用 config/tickers.yaml 里的原名 (data.fetch 时会自动 alias 到 yfinance 真实名字)
MACRO_TICKERS = [
    ("^VIX", "VIX", "panic"),                # 恐慌指数 (反向: 高 = 危险)
    ("^TNX", "10Y", "yield"),                # 10 年期美债收益率 (核心)
    ("DXY", "DXY", "dollar"),                # 美元指数 (alias -> DX-Y.NYB)
]


def _format_change_pct(curr: float, prev: float) -> str:
    """格式化 1 日变化"""
    if prev == 0 or pd.isna(prev) or pd.isna(curr):
        return "N/A"
    pct = (curr / prev - 1) * 100
    return f"{pct:+.2f}%"


def _format_bp(curr: float, prev: float) -> str:
    """格式化基点变化 (用于收益率,1 bp = 0.01%)"""
    if pd.isna(curr) or pd.isna(prev):
        return "N/A"
    bp = (curr - prev) * 100  # 收益率 1.00% = 100 bp
    return f"{bp:+.0f}bp"


def _format_value(symbol_label: str, value: float, decimals: int = 2) -> str:
    """格式化值"""
    if pd.isna(value):
        return f"{symbol_label} N/A"
    return f"{symbol_label} {value:.{decimals}f}"


def macro_snapshot(macro_tickers: Optional[list[tuple[str, str, str]]] = None) -> str:
    """
    顶部情绪 1 行: VIX / 10Y / DXY 当日

    例子输出:
      VIX 14.32 (-2.10%) | 10Y 4.25% (-1bp) | DXY 104.50 (+0.30%)

    Returns:
        1 行字符串 (~80 字符)
    """
    if macro_tickers is None:
        macro_tickers = MACRO_TICKERS

    parts = []
    for ticker, label, kind in macro_tickers:
        try:
            df = load_prices(ticker, "macro")
            if len(df) < 2:
                parts.append(f"{label} N/A")
                continue
            curr = float(df["close"].iloc[-1])
            prev = float(df["close"].iloc[-2])

            # 收益率用 bp, 其他用 %
            if kind == "yield":
                chg = _format_bp(curr, prev)
                parts.append(f"{label} {curr:.2f}% ({chg})")
            else:
                chg = _format_change_pct(curr, prev)
                decimals = 2 if kind != "dollar" else 2
                parts.append(f"{label} {curr:.{decimals}f} ({chg})")
        except FileNotFoundError:
            parts.append(f"{label} N/A")
        except Exception as e:
            logger.warning(f"[macro] {ticker} 失败: {e}")
            parts.append(f"{label} N/A")

    return " | ".join(parts)


def indices_1line(symbols: Optional[list[str]] = None, lookback_days: int = 1) -> str:
    """
    4 指数 1 日 1 行

    例子输出:
      DIA +0.10% | QQQ +0.85% | RSP -0.05% | QQQE +0.32%

    Args:
        symbols: 默认 ["DIA", "QQQ", "RSP", "QQQE"]
        lookback_days: 1 (1 日) / 5 (5 日累计)
    """
    if symbols is None:
        symbols = ["DIA", "QQQ", "RSP", "QQQE"]

    parts = []
    for sym in symbols:
        try:
            df = load_prices(sym, "indices")
            rets = df["close"].pct_change()
            if lookback_days == 1:
                chg = float(rets.iloc[-1])
                period = "1d"
            else:
                chg = float((df["close"].iloc[-1] / df["close"].iloc[-lookback_days - 1] - 1))
                period = f"{lookback_days}d"
            parts.append(f"{sym} {chg*100:+.2f}% ({period})")
        except FileNotFoundError:
            parts.append(f"{sym} N/A")
        except Exception as e:
            logger.warning(f"[indices_1line] {sym} 失败: {e}")
            parts.append(f"{sym} N/A")

    return " | ".join(parts)


def topline(macro: Optional[str] = None, indices: Optional[str] = None) -> str:
    """
    顶部 1 行: 宏观情绪 + 4 指数 1 日

    Returns:
        多行字符串 (宏观 1 行 + 指数 1 行)
    """
    if macro is None:
        macro = macro_snapshot()
    if indices is None:
        indices = indices_1line()
    return f"**🌡️ 顶部情绪**: {macro}\n\n**📈 4 指数 1 日**: {indices}\n"


if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    print(topline())
