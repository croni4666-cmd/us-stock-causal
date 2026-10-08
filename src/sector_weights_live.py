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
import copy
import json
import threading
from functools import wraps
from uuid import uuid4
from datetime import datetime
from pathlib import Path
from loguru import logger
from src.attribution import WEIGHTS_PATH

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = PROJECT_ROOT / "data" / "cache"
_WEIGHT_LOCK = threading.RLock()


def _locked(function):
    @wraps(function)
    def locked(*args, **kwargs):
        with _WEIGHT_LOCK:
            return function(*args, **kwargs)
    return locked


def _cache_path(date: str = None) -> Path:
    return CACHE_DIR / f"sector_weights_live_{date or datetime.now().strftime('%Y-%m-%d')}.json"


def pull_live_weights(date: str = None) -> dict:
    """Read configuration using its actual effective date, never the request date."""
    with WEIGHTS_PATH.open(encoding="utf-8") as f:
        data = json.load(f)
    effective = data.get("_meta", {}).get("as_of")
    if not effective:
        raise ValueError("行业权重缺少真实生效日期 _meta.as_of")
    return {"as_of": effective, "source": str(WEIGHTS_PATH), "data": data}


def _snapshot_version(snapshot: dict):
    data = snapshot.get("data", snapshot)
    effective = data.get("_meta", {}).get("as_of") or snapshot.get("as_of")
    # Reject accidentally double-wrapped snapshots rather than returning an envelope.
    if not effective or not any(k in data for k in ("DIA", "QQQ", "RSP", "QQQE", "SPY")):
        return None
    datetime.strptime(effective, "%Y-%m-%d")
    return effective, data


@_locked
def save_live_cache(snapshot: dict, date: str = None) -> Path | None:
    version = _snapshot_version(snapshot)
    if version is None:
        raise ValueError("无效行业权重快照")
    effective, data = version
    target_date = date or effective
    if target_date < effective:
        logger.warning(f"[weights] 拒绝未来权重快照: {target_date} < {effective}")
        return None
    path = _cache_path(target_date)
    path.parent.mkdir(parents=True, exist_ok=True)
    canonical = {**snapshot, "as_of": effective, "data": data}
    if path.exists():
        try:
            if json.loads(path.read_text(encoding="utf-8")) == canonical:
                return path
        except (OSError, ValueError):
            pass
    temp = path.with_name(f"{path.name}.{uuid4().hex}.tmp")
    temp.write_text(json.dumps(canonical, indent=2, ensure_ascii=False), encoding="utf-8")
    temp.replace(path)
    return path


@_locked
def _discover_all_weight_versions() -> list[tuple[str, dict]]:
    versions = []
    if WEIGHTS_PATH.exists():
        with WEIGHTS_PATH.open(encoding="utf-8") as f:
            version = _snapshot_version(json.load(f))
        if version:
            versions.append(version)
    for path in sorted(CACHE_DIR.glob("sector_weights_live_*.json")):
        try:
            version = _snapshot_version(json.loads(path.read_text(encoding="utf-8")))
            if version:
                versions.append(version)
        except (ValueError, OSError, TypeError):
            logger.warning(f"[weights] 忽略无效快照: {path.name}")
    return sorted(versions, key=lambda v: v[0])


@_locked
def load_live_or_static(date: str = None, use_cache: bool = True,
                        allow_future_fallback: bool = False) -> dict:
    """Select the newest effective version at or before the requested day.

    Future weights are available only through explicit approximate-mode opt-in.
    Reading without cache still enforces the same historical date boundary.
    """
    requested = date or datetime.now().strftime("%Y-%m-%d")
    datetime.strptime(requested, "%Y-%m-%d")
    versions = _discover_all_weight_versions()
    valid = [v for v in versions if v[0] <= requested]
    if valid:
        effective, data = max(valid, key=lambda v: v[0])
        if use_cache:
            save_live_cache({"as_of": effective, "data": data}, requested)
        return copy.deepcopy(data)
    if not versions or not allow_future_fallback:
        raise FileNotFoundError(f"历史行业权重不可用: {requested} 没有已生效版本")
    effective, data = min(versions, key=lambda v: v[0])
    result = copy.deepcopy(data)
    result.setdefault("_meta", {}).update(
        is_historical_fallback=True, requested_as_of=requested, effective_date=effective,
        warning=f"历史权重不可用: 使用 {effective} 未来权重近似 {requested}，存在前瞻偏差",
    )
    return result


@_locked
def clear_old_caches(keep_days: int = 7) -> list[Path]:
    """Prune duplicate daily caches, retaining one snapshot per effective version."""
    today = datetime.now().date()
    candidates = []
    newest = {}
    for path in sorted(CACHE_DIR.glob("sector_weights_live_*.json")):
        try:
            file_date = datetime.strptime(path.stem.removeprefix("sector_weights_live_"), "%Y-%m-%d").date()
            version = _snapshot_version(json.loads(path.read_text(encoding="utf-8")))
            if version:
                effective = version[0]
                candidates.append((path, file_date, effective))
                newest[effective] = path
        except (ValueError, OSError, TypeError):
            continue
    deleted = []
    for path, file_date, effective in candidates:
        if (today - file_date).days > keep_days and path != newest[effective]:
            path.unlink()
            deleted.append(path)
    return deleted
