"""src/sector_weights_live.py - sector weights live cache (v0.6.9h P7-4)

设计:
- 归因函数 attribute_index 每次都重读 config/sector_weights.json
- P7-4: 1d cache 机制, 归因优先读 cache, 过期走 pull (实际是文件 copy, 非真"实时拉")
- cache 路径: data/cache/sector_weights_live_YYYY-MM-DD.json
- 设计简化: 实际"pull" = cp config/sector_weights.json 到 cache (因为 P7-3 派生
  是月度手动维护, 没法"真"实时拉). 1d cache 主要是减少 IO + 留个 audit trail
  (哪个日期用哪份 weights)

Why P7-4:
- v0.6.9 daily cron 跑 8 天, attribution 调用数十次, 每次重读 + parse JSON
- 1d cache 1 次读 + 10+ 次 hit, 速度提升微乎其微 (< 5ms) 但语义更清晰
- 月度维护 sector_weights.json 时, cache 自动 day-rollover 拿新文件
- Audit trail: data/cache/sector_weights_live_*.json 留历史快照, 排查
  "昨天归因跟今天归因差很多" 时能查哪份 weights
"""
from __future__ import annotations
import json
import shutil
from datetime import datetime
from pathlib import Path

from src.attribution import WEIGHTS_PATH  # config/sector_weights.json 绝对路径

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = PROJECT_ROOT / "data" / "cache"


def _cache_path(date: str = None) -> Path:
    """1d cache 路径: data/cache/sector_weights_live_YYYY-MM-DD.json"""
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    return CACHE_DIR / f"sector_weights_live_{date}.json"


def pull_live_weights(date: str = None) -> dict:
    """从 config/sector_weights.json pull (实际是 cp, 因 P7-3 月度维护)

    Returns:
        {"as_of": "...", "data": {...weights dict...}}
    """
    if not WEIGHTS_PATH.exists():
        raise FileNotFoundError(f"{WEIGHTS_PATH} 不存在, 先跑 derive_sector_weights.py")
    with open(WEIGHTS_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return {
        "as_of": date or datetime.now().strftime("%Y-%m-%d"),
        "source": str(WEIGHTS_PATH.relative_to(PROJECT_ROOT)),
        "data": data,
    }


def save_live_cache(snapshot: dict, date: str = None) -> Path:
    """写 1d cache JSON"""
    path = _cache_path(date)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2, ensure_ascii=False)
    return path


def load_live_or_static(date: str = None, use_cache: bool = True) -> dict:
    """优先读 1d cache, 过期走 pull + cache

    Args:
        date: YYYY-MM-DD, None = 今天
        use_cache: True (默认) 走 cache 逻辑; False 直接 pull

    Returns:
        weights dict (跟 config/sector_weights.json 顶层结构一致)
    """
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")

    if use_cache:
        cache_path = _cache_path(date)
        if cache_path.exists():
            with open(cache_path, encoding="utf-8") as f:
                snap = json.load(f)
            return snap["data"]

    # cache miss / 过期 / use_cache=False → pull + cache
    snap = pull_live_weights(date)
    if use_cache:
        save_live_cache(snap, date)
    return snap["data"]


def clear_old_caches(keep_days: int = 7) -> list[Path]:
    """清旧 cache (保留最近 keep_days 天), 返回删除路径

    防止 data/cache 无限增长
    """
    if not CACHE_DIR.exists():
        return []
    deleted = []
    today = datetime.now().date()
    for p in CACHE_DIR.glob("sector_weights_live_*.json"):
        try:
            # filename: sector_weights_live_YYYY-MM-DD.json
            date_str = p.stem.replace("sector_weights_live_", "")
            d = datetime.strptime(date_str, "%Y-%m-%d").date()
            age_days = (today - d).days
            if age_days > keep_days:
                p.unlink()
                deleted.append(p)
        except ValueError:
            # 异常 filename (不是日期格式), 跳过
            continue
    return deleted
