"""
src/macro.py - 宏观情绪 顶部多档 (Phase 3.2 P3-3 + Phase 6 P6-4 v0.6.8)

设计:
  - 顶部 1 行 (v0.4.1 P3-3) → 顶部 3 行 (v0.6.8 P6-4): 1d / 5d / 20d 累计
  - 30 秒读完的整体市场情绪
  - 跟 5 段报告 + K 线组合 = 30s/5min/15min 三档阅读

P6-4 升级动机:
  - P6-3 多窗口归因 (v0.6.7) 显示 5d 残差根因是 sector weight 短期漂移
  - 顶部也跟 5 段报告对齐: 5 段默认 5d, 顶部 1d/5d/20d 3 档
  - 不挤 5 段 (5 段默认 5d 不变), 顶部扩成 3 行
  - 1d 看每日, 5d 看短期, 20d 看中期趋势

数据来源: src.cache / data/raw/macro/<safe_name>.parquet
计算: 简单 % change / bp change, 不做平滑
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


def macro_snapshot(
    macro_tickers: Optional[list[tuple[str, str, str]]] = None,
    lookback_days: int = 1,
) -> str:
    """
    顶部情绪 1 行: VIX / 10Y / DXY (v0.6.8 P6-4: 支持 lookback_days)

    例子输出 (lookback_days=1):
      VIX 14.32 (-2.10%) | 10Y 4.25% (-1bp) | DXY 104.50 (+0.30%)

    Args:
        macro_tickers: 3 元组 (ticker, label, kind) 列表
        lookback_days: 1 (1 日变化) / 5 (5 日累计) / 20 (20 日累计)

    Returns:
        1 行字符串 (~80 字符)
    """
    if macro_tickers is None:
        macro_tickers = MACRO_TICKERS

    parts = []
    for ticker, label, kind in macro_tickers:
        try:
            df = load_prices(ticker, "macro")
            # need at least lookback_days+1 rows to compute change
            if len(df) < lookback_days + 1:
                parts.append(f"{label} N/A")
                continue
            curr = float(df["close"].iloc[-1])
            prev = float(df["close"].iloc[-lookback_days - 1])

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


def topline(
    macro: Optional[str] = None,
    indices: Optional[str] = None,
    horizons: tuple[int, ...] = (1, 5, 20),
) -> str:
    """
    顶部 1 行 → 顶部 N 行 (Phase 6 P6-4, v0.6.8)

    短期/中期/长期 1 眼看全。

    例子输出 (horizons=(1, 5, 20) 默认):
      **🌡️ 顶部情绪** (1d / 5d / 20d 累计, 短期/中期/长期):
      - **1d**: VIX 16.40 (+9.12%) | 10Y 4.57% (+3bp) | DXY 100.97 (+0.03%)  ||  DIA +0.30% | QQQ +0.31% | RSP +0.37% | QQQE +0.03%
      - **5d**: VIX 16.40 (-3.20%) | 10Y 4.57% (-2bp) | DXY 100.97 (-0.50%)  ||  DIA -0.40% | QQQ +1.81% | RSP -0.28% | QQQE +0.38%
      - **20d**: VIX 16.40 (+2.10%) | 10Y 4.57% (-5bp) | DXY 100.97 (+1.20%)  ||  DIA +1.50% | QQQ +4.20% | RSP +2.10% | QQQE +3.30%

    Args:
        macro: 预生成 macro 字符串 (单行模式生效, 多行模式忽略 — 必须按 horizon 重算)
        indices: 预生成 indices 字符串 (单行模式生效, 多行模式忽略)
        horizons: 时间窗元组, 默认 (1, 5, 20) 短期/中期/长期
                  传 () 或 (1,) 走单行模式 (向后兼容 v0.4.1)

    Returns:
        单行 (旧): `**🌡️ 顶部情绪**: ... \n\n**📈 4 指数 1 日**: ...`
        多行 (新, 默认): markdown bullet list 3 行

    P6-4 设计动机:
      - P6-3 多窗口归因已经显示 5d 残差根因是 sector weight 短期漂移, 不是窗口问题
      - 顶部跟 5 段报告对齐: 5 段默认 5d, 顶部 1d/5d/20d 3 档, 让用户 1 眼看短期/中期/长期
      - 不挤 5 段 (5 段默认 5d 不变), 顶部扩成 3 行
    """
    if not horizons or len(horizons) <= 1:
        # 单行模式 (向后兼容)
        h = horizons[0] if horizons else 1
        if macro is None:
            macro = macro_snapshot(lookback_days=h)
        if indices is None:
            indices = indices_1line(lookback_days=h)
        return f"**🌡️ 顶部情绪**: {macro}\n\n**📈 4 指数 {h} 日**: {indices}\n"

    # 多行模式 (P6-4 v0.6.8 新)
    lines = [f"**🌡️ 顶部情绪** ({' / '.join(f'{h}d' for h in horizons)} 累计, 短期/中期/长期):"]
    for h in horizons:
        macro_str = macro_snapshot(lookback_days=h)
        indices_str = indices_1line(lookback_days=h)
        lines.append(f"- **{h}d**: {macro_str}  ||  {indices_str}")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    print(topline())
