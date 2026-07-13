"""
src/patterns.py - 历史模式匹配

Phase 2.2 (P2-5) 模式匹配 (简化版,不用 DTW):

  1. 拿当前 20 天日收益率 pattern
  2. 在历史 2y 数据里, 找最相似的 20 天 windows (Pearson 相关)
  3. 看这些 windows 之后 5/20 天的实际收益
  4. 聚合: 平均收益, 胜率, 最大涨/跌

**为什么用相关而不是 DTW**:
  - DTW (Dynamic Time Warping) 复杂度 O(N²) 对齐时间序列
  - Pearson 相关只看"形状",对微小价格水平漂移不敏感
  - 量化研究里,简单相关 90% 情况下和 DTW 差不多,但快 100 倍
  - 真正的"模式" = 形状 (up/down sequence),不是价格水平

**因果意义**:
  - "现在 QQQ 的 20 天形态像 2024-08-15 那段时间" → 看那之后 5 天怎么走
  - 不预测"会重复",而是给"统计上历史上类似形态后续如何"
  - 用户自己判断:这个统计跟当前宏观/政策环境合不合
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from loguru import logger

from src.thresholds import load_prices, safe_name

INDEX_SYMBOLS = {"DIA", "QQQ", "RSP", "QQQE"}
SECTOR_SYMBOLS = {"XLK", "XLF", "XLE", "XLY", "XLP", "XLV", "XLI", "XLU", "XLB", "XLRE", "XLC"}


def find_similar_patterns(
    symbol: str,
    pattern_length: int = 20,
    n_matches: int = 10,
    forecast_horizon: int = 5,
    end_date: Optional[str] = None,
) -> dict:
    """
    找历史最相似的 N 个 pattern windows,看后续收益分布

    Args:
        symbol: ticker (index / sector / etc.)
        pattern_length: pattern 长度 (默认 20 = 1 个月)
        n_matches: 返回 top N 个最相似
        forecast_horizon: 后续看 N 天
        end_date: 'YYYY-MM-DD', None = 最新可用日

    Returns:
        {
            'symbol': 'QQQ',
            'pattern_end': '2026-07-10',
            'pattern_length': 20,
            'n_matches': 10,
            'avg_forward_return': 0.012,  # 平均 5d 收益
            'median_forward_return': 0.008,
            'win_rate': 0.7,             # 5d 后上涨概率
            'max_forward': 0.045,
            'min_forward': -0.022,
            'top_matches': [{...}, ...]  # 每个 match 的详情
        }
    """
    if symbol in INDEX_SYMBOLS:
        layer = "indices"
    elif symbol in SECTOR_SYMBOLS:
        layer = "sectors"
    else:
        layer = "macro"

    df = load_prices(symbol, layer)
    rets = df["close"].pct_change().dropna()

    if end_date:
        rets = rets.loc[:end_date]

    if len(rets) < pattern_length + forecast_horizon + 30:
        raise ValueError(
            f"{symbol} 数据太短 ({len(rets)} days),"
            f"需要 ≥ {pattern_length + forecast_horizon + 30}"
        )

    # 当前 pattern (最后 pattern_length 天)
    current = rets.iloc[-pattern_length:].values
    current_mean = current.mean()
    current_std = current.std() + 1e-9
    current_norm = (current - current_mean) / current_std

    # 滑动窗口匹配
    n = len(rets)
    candidates = []
    for s in range(0, n - pattern_length - forecast_horizon):
        # 跳过包含当前 pattern 的窗口
        if s >= n - pattern_length:
            continue
        window = rets.iloc[s:s+pattern_length].values
        w_mean = window.mean()
        w_std = window.std() + 1e-9
        w_norm = (window - w_mean) / w_std
        # Pearson 相关
        corr = float(np.corrcoef(current_norm, w_norm)[0, 1])
        if np.isnan(corr):
            continue
        # 后续 forecast_horizon 天收益
        forward = rets.iloc[s+pattern_length:s+pattern_length+forecast_horizon].values
        if len(forward) < forecast_horizon:
            continue
        forward_cum = float((1 + pd.Series(forward)).prod() - 1)
        candidates.append({
            "start_date": str(rets.index[s].date()),
            "end_date": str(rets.index[s+pattern_length-1].date()),
            "correlation": round(corr, 4),
            "forward_return": round(forward_cum * 100, 3),
        })

    # 按相关排序
    candidates.sort(key=lambda x: -x["correlation"])
    top = candidates[:n_matches]

    if not top:
        raise ValueError(f"{symbol} 找不到任何 pattern (数据可能太短)")

    forward_returns = [c["forward_return"] for c in top]
    n_win = sum(1 for r in forward_returns if r > 0)

    return {
        "symbol": symbol,
        "pattern_end": str(rets.index[-1].date()),
        "pattern_length": pattern_length,
        "forecast_horizon": forecast_horizon,
        "n_matches": len(top),
        "avg_forward_return": round(float(np.mean(forward_returns)), 3),
        "median_forward_return": round(float(np.median(forward_returns)), 3),
        "win_rate": round(n_win / len(forward_returns), 3),
        "max_forward": round(max(forward_returns), 3),
        "min_forward": round(min(forward_returns), 3),
        "top_matches": top,
    }


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    for sym in ["DIA", "QQQ", "RSP", "QQQE"]:
        print(f"\n=== {sym} 20d pattern match (top 5, 5d forward) ===")
        r = find_similar_patterns(sym, pattern_length=20, n_matches=5, forecast_horizon=5)
        print(f"  current pattern ends: {r['pattern_end']}")
        print(f"  5d forward: avg {r['avg_forward_return']:+.2f}% / "
              f"median {r['median_forward_return']:+.2f}% / "
              f"win rate {r['win_rate']:.0%} / "
              f"max {r['max_forward']:+.2f}% / min {r['min_forward']:+.2f}%")
        for i, m in enumerate(r["top_matches"], 1):
            print(f"    #{i} {m['start_date']} ~ {m['end_date']}  corr={m['correlation']:+.3f}  "
                  f"5d fwd {m['forward_return']:+.2f}%")
