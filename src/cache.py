"""
src/cache.py - Parquet 增量缓存

设计:
  - 目录按"层"分 (data/raw/indices, sectors, macro, commodities_futures, commodities_spot)
  - 文件名 safe (^VIX -> _VIX, GC=F -> GC_F)
  - 二次拉只取增量 (last_date + 1d 到今天)
  - 单 ticker 失败不阻塞,返回错误信息
"""
from __future__ import annotations

import os
import time
from datetime import date, datetime, timedelta, time as dtime, timezone
from pathlib import Path
from typing import Callable, Optional

from zoneinfo import ZoneInfo
from functools import lru_cache
import pandas_market_calendars as mcal

EASTERN_TZ = ZoneInfo("America/New_York")

import pandas as pd
from loguru import logger


def safe_name(symbol: str) -> str:
    """
    ^VIX -> _VIX
    GC=F -> GC_F
    BRK.B -> BRK_B
    """
    return symbol.replace("^", "_").replace("=", "_").replace(".", "_")


def cache_path(symbol: str, layer: str, cache_root: Path) -> Path:
    """生成缓存路径: <cache_root>/<layer>/<safe_name>.parquet"""
    layer_dir = cache_root / layer
    layer_dir.mkdir(parents=True, exist_ok=True)
    return layer_dir / f"{safe_name(symbol)}.parquet"


@lru_cache(maxsize=128)
def _nyse_schedule(day: date) -> pd.DataFrame:
    return mcal.get_calendar("NYSE").schedule(
        start_date=day - timedelta(days=30), end_date=day,
    )


def get_expected_last_trading_day(ref: Optional[date | datetime | str] = None) -> date:
    """Last completed NYSE session, allowing 15 minutes after its actual close.

    Date-only values target that day's final session. Naive datetimes are NY time;
    aware datetimes are converted to NY time, including winter DST offsets.
    """
    if ref is None:
        ref = datetime.now(EASTERN_TZ)
    if isinstance(ref, str):
        ref = datetime.fromisoformat(ref) if "T" in ref or " " in ref else date.fromisoformat(ref)
    if isinstance(ref, datetime):
        instant = ref.replace(tzinfo=EASTERN_TZ) if ref.tzinfo is None else ref.astimezone(EASTERN_TZ)
        schedule = _nyse_schedule(instant.date())
        ready = schedule["market_close"] + pd.Timedelta(minutes=15)
        schedule = schedule.loc[ready <= pd.Timestamp(instant)]
    elif isinstance(ref, date):
        schedule = _nyse_schedule(ref)
    else:
        raise TypeError("ref must be a date, datetime, or ISO date/time")
    if schedule.empty:
        raise ValueError("No completed NYSE session in the requested date range")
    return schedule.index[-1].date()


def is_fresh(
    parquet_path: Path,
    max_age_days: int = 1,
    as_of: Optional[date | datetime | str] = None,
) -> bool:
    """缓存是否新鲜: 同时检查文件 mtime 与 parquet 内最新交易数据日期与预期交易日差距."""
    if not parquet_path.exists():
        return False
    mtime = datetime.fromtimestamp(parquet_path.stat().st_mtime)
    if (datetime.now() - mtime) >= timedelta(days=max_age_days):
        return False
    # 检查实际数据最新日期
    try:
        df = read_cache(parquet_path)
        if df is None or len(df) == 0:
            return False
        last_dt = pd.to_datetime(df.index[-1]).date()
        expected = get_expected_last_trading_day(as_of)
        # 如果最新数据早于预期的已完成交易日，说明缺少必要交易日数据，需要更新
        if last_dt < expected:
            return False
    except Exception:
        return False
    return True


def read_cache(parquet_path: Path) -> Optional[pd.DataFrame]:
    """读 parquet 缓存,失败返回 None"""
    if not parquet_path.exists():
        return None
    try:
        return pd.read_parquet(parquet_path)
    except Exception as e:
        logger.warning(f"缓存读取失败 {parquet_path}: {e}")
        return None


def write_cache(df: pd.DataFrame, parquet_path: Path) -> None:
    """原子写 parquet (写入临时文件并校验后原子替换，防止中断破坏文件)."""
    if df is None or len(df) == 0:
        logger.warning(f"跳过写入空缓存: {parquet_path.name}")
        return
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = parquet_path.with_suffix(f".tmp_{os.getpid()}_{int(time.time()*1000)%100000}.parquet")
    try:
        df.to_parquet(tmp_path, index=True)
        # 校验可读
        pd.read_parquet(tmp_path)
        os.replace(tmp_path, parquet_path)
        size_kb = parquet_path.stat().st_size / 1024
        logger.info(f"缓存写入: {parquet_path.name} ({size_kb:.1f} KB, {len(df)} rows)")
    except Exception as e:
        if tmp_path.exists():
            tmp_path.unlink()
        logger.error(f"原子写入缓存失败 {parquet_path}: {e}")
        raise


def update_or_fetch(
    symbol: str,
    layer: str,
    fetcher: Callable[..., pd.DataFrame],
    cache_root: Path,
    start: str = "2025-01-01",
    end: Optional[str] = None,
    force_refresh: bool = False,
) -> tuple[pd.DataFrame, str]:
    """
    主入口:有缓存就增量更新,没缓存就全量拉。

    Args:
        symbol: ticker
        layer: "indices" / "sectors" / "macro" / "commodities_futures" / "commodities_spot"
        fetcher: e.g. data.fetch_equity 或 data.fetch_commodity
        cache_root: e.g. PROJECT_ROOT / "data" / "raw"
        start: 缓存为空时,从此日期开始拉
        end: None = 今天
        force_refresh: 强制全量重拉 (安全刷新: 成功才覆盖, 失败保留旧缓存)

    Returns:
        (DataFrame, status)
        status: "full" / "incremental" / "cached" / "empty" / "rate_limited" / "refresh_failed_cached"
    """
    path = cache_path(symbol, layer, cache_root)

    # 0. v0.6.8j (P7-6): yfinance 限流检测 — 限流时跳过 fetch, 返回旧缓存
    from src.yfinance_rate_limit import is_rate_limited, get_rate_limit_info
    if is_rate_limited() and not force_refresh:
        info = get_rate_limit_info()
        logger.warning(
            f"[{symbol}] yfinance 限流中 (hit={info.get('hit_count', '?')}, "
            f"expires={info.get('expires_at', '?')}). 跳过 fetch, 用 cache only."
        )
        cached = read_cache(path)
        if cached is not None and len(cached) > 0:
            return cached, "rate_limited"
        return pd.DataFrame(), "rate_limited_empty"

    # 1. 强制刷新: 先拉取新数据，成功后再原子替换旧缓存；如果失败则安全保留旧缓存降级返回
    if force_refresh:
        try:
            df = fetcher(symbol, start=start, end=end)
            if df is not None and len(df) > 0:
                write_cache(df, path)
                return df, "full"
            else:
                logger.warning(f"[{symbol}] force_refresh 拉取结果为空, 保留旧缓存")
        except Exception as e:
            logger.error(f"[{symbol}] force_refresh 拉取失败, 保留旧缓存: {e}")
        cached = read_cache(path)
        if cached is not None and len(cached) > 0:
            return cached, "refresh_failed_cached"
        return pd.DataFrame(), "empty"

    # 2. 缓存存在 + 新鲜 (今天拉过) → 直接返回
    if is_fresh(path, max_age_days=1) and not force_refresh:
        cached = read_cache(path)
        if cached is not None and len(cached) > 0:
            return cached, "cached"

    # 3. 缓存存在但不新鲜 → 增量更新
    cached = read_cache(path)
    if cached is not None and len(cached) > 0:
        last_date = cached.index[-1]
        fetch_start = (last_date + timedelta(days=1)).strftime("%Y-%m-%d")
        if pd.Timestamp(fetch_start) > pd.Timestamp.now().normalize():
            return cached, "cached"
        try:
            new_df = fetcher(symbol, start=fetch_start, end=end)
            if len(new_df) == 0:
                return cached, "cached"
            combined = pd.concat([cached, new_df])
            combined = combined[~combined.index.duplicated(keep="last")].sort_index()
            write_cache(combined, path)
            return combined, "incremental"
        except Exception as e:
            logger.warning(f"[{symbol}] 增量更新失败,返回旧缓存: {e}")
            return cached, "cached"

    # 4. 无缓存 → 全量拉
    try:
        df = fetcher(symbol, start=start, end=end)
        write_cache(df, path)
        return df, "full"
    except Exception as e:
        logger.error(f"[{symbol}] 全量拉取失败: {e}")
        return pd.DataFrame(), "empty"
