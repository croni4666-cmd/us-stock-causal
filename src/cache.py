"""
src/cache.py - Parquet 增量缓存

设计:
  - 目录按"层"分 (data/raw/indices, sectors, macro, commodities_futures, commodities_spot)
  - 文件名 safe (^VIX -> _VIX, GC=F -> GC_F)
  - 二次拉只取增量 (last_date + 1d 到今天)
  - 单 ticker 失败不阻塞,返回错误信息
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional

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


def is_fresh(parquet_path: Path, max_age_days: int = 1) -> bool:
    """缓存是否新鲜 (今天已拉过)"""
    if not parquet_path.exists():
        return False
    mtime = datetime.fromtimestamp(parquet_path.stat().st_mtime)
    return (datetime.now() - mtime) < timedelta(days=max_age_days)


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
    """写 parquet"""
    df.to_parquet(parquet_path, index=True)
    size_kb = parquet_path.stat().st_size / 1024
    logger.info(f"缓存写入: {parquet_path.name} ({size_kb:.1f} KB, {len(df)} rows)")


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
        force_refresh: 强制全量重拉

    Returns:
        (DataFrame, status)
        status: "full" / "incremental" / "cached" / "empty"
    """
    path = cache_path(symbol, layer, cache_root)

    # 0. v0.6.8j (P7-6): yfinance 限流检测 — 限流时跳过 fetch, 返回旧缓存
    #    防止 daily cron 静默挂掉, Phase 8 alert 推送
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
        # 无缓存 + 限流 = 拿不到数据, 返回空
        return pd.DataFrame(), "rate_limited_empty"

    # 1. 强制刷新
    if force_refresh and path.exists():
        path.unlink()
        logger.info(f"[{symbol}] force_refresh,删旧缓存")

    # 2. 缓存存在 + 新鲜 (今天拉过) → 直接返回
    if is_fresh(path, max_age_days=1) and not force_refresh:
        cached = read_cache(path)
        if cached is not None and len(cached) > 0:
            return cached, "cached"

    # 3. 缓存存在但不新鲜 → 增量更新
    cached = read_cache(path)
    if cached is not None and len(cached) > 0:
        last_date = cached.index[-1]
        # 从 last_date + 1d 拉到今天
        fetch_start = (last_date + timedelta(days=1)).strftime("%Y-%m-%d")
        # 如果 last_date 已经是今天,跳过
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
