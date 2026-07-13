"""
src/data.py - yfinance 统一封装

v0.2.0 设计变更:
  - 原本想用 OpenBB Platform SDK 统一入口,但 `obb.commodity.price.historical` 不存在
    (commodity 路由只有 `spot`,没有 `historical`)
  - 改用 yfinance 直接拉(OpenBB equity 内部也是 yfinance)
  - 优点: 一个后端,简单可靠,支持所有 =F / =X / 指数 / 行业 / 国债 ticker
  - 缺点: 少 OpenBB 抽象层,但 v0.2.0 不需要

Phase 2+ 可加的 provider:
  - alpha_vantage (需要 key,免费 25 req/day)
  - polygon (需要 key,免费 5 req/min)
  - Stooq (被 Cloudflare 挡,不可用)
"""
from __future__ import annotations

import time
from datetime import datetime
from typing import Optional

import pandas as pd
import yfinance as yf
from loguru import logger

# proxy 必须在 yfinance 之前 import (yfinance 用 requests,会读 env var)
from src import proxy  # noqa: F401


# yfinance 的 ticker 别名映射 (OpenBB/yahoo 名字差异)
TICKER_ALIAS = {
    "DXY": "DX-Y.NYB",        # Yahoo 用 DX-Y.NYB 才是美元指数
    "DXY.PROXY": "UUP",       # 备选: UUP ETF
}


def _normalize(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """统一 DataFrame 格式"""
    if df is None or df.empty:
        raise RuntimeError(f"{symbol}: yfinance 返回空数据")

    # yfinance 返回的列名首字母大写,统一转小写
    df.columns = [c.lower() for c in df.columns]

    # 时区处理: yfinance 返回 tz-aware,去 tz
    if df.index.tzinfo is not None:
        df.index = df.index.tz_localize(None)

    # 确保 index 是 DatetimeIndex 且叫 date
    df.index = pd.DatetimeIndex(df.index)
    df.index.name = "date"

    # 排序 + 去重
    df = df.sort_index()
    df = df[~df.index.duplicated(keep="last")]

    return df


def _resolve_ticker(symbol: str) -> str:
    """应用 ticker 别名"""
    return TICKER_ALIAS.get(symbol, symbol)


def fetch(
    symbol: str,
    start: str,
    end: Optional[str] = None,
    auto_adjust: bool = False,
) -> pd.DataFrame:
    """
    统一入口: 拉任意 ticker 的 OHLCV (yfinance 后端)

    Args:
        symbol: DIA / QQQ / GC=F / ^VIX / ^TNX / DXY (会自动转 DX-Y.NYB) ...
        start:  YYYY-MM-DD
        end:    YYYY-MM-DD, None = 今天
        auto_adjust: 是否用复权后价格 (False 保留 Adj Close)

    Returns:
        DataFrame with lowercase columns: open/high/low/close/volume (and adj_close if available)
    """
    if end is None:
        end = datetime.now().strftime("%Y-%m-%d")

    actual_symbol = _resolve_ticker(symbol)
    logger.info(f"[fetch] {symbol} -> {actual_symbol}: {start} -> {end}")

    last_err = None
    for attempt in range(3):
        try:
            stock = yf.Ticker(actual_symbol)
            df = stock.history(
                start=start,
                end=end,
                interval="1d",
                auto_adjust=auto_adjust,
            )
            if df.empty:
                raise RuntimeError(f"yfinance 返回空 (可能 delisted 或 ticker 错)")
            return _normalize(df, symbol)
        except Exception as e:
            last_err = e
            wait = 2 ** attempt
            logger.warning(f"[{symbol}] yfinance 失败 (attempt {attempt+1}/3): {e}. {wait}s 后重试")
            time.sleep(wait)

    raise RuntimeError(f"{symbol}: 3 次重试都失败: {last_err}")


if __name__ == "__main__":
    # 自测: 4 类各 1 个
    samples = [
        ("DIA", "equity / index"),
        ("XLK", "equity / sector"),
        ("^VIX", "equity / macro"),
        ("GC=F", "yfinance direct / futures"),
        ("DX-Y.NYB", "yfinance direct / DXY"),
    ]
    for sym, kind in samples:
        try:
            t0 = time.time()
            df = fetch(sym, "2025-01-01")
            print(f"  ✅ {sym:8s} ({kind:25s}): {len(df):>4d} rows, "
                  f"{df.index[0].date()} -> {df.index[-1].date()}, {time.time()-t0:.1f}s")
        except Exception as e:
            print(f"  ❌ {sym:8s} ({kind:25s}): {type(e).__name__}: {e}")
