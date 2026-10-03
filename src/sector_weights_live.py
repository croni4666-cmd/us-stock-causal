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
import re
import shutil
from datetime import datetime
from pathlib import Path
from loguru import logger

from src.attribution import WEIGHTS_PATH  # config/sector_weights.json 绝对路径

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = PROJECT_ROOT / "data" / "cache"


def _cache_path(date: str = None) -> Path:
    """1d cache 路径: data/cache/sector_weights_live_YYYY-MM-DD.json"""
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    return CACHE_DIR / f"sector_weights_live_{date}.json"


def pull_live_weights(date: str = None) -> dict:
    """从 config/sector_weights.json pull (实际是 cp, 因 P7-3 月度维护).

    Returns:
        {"as_of": "<real_effective_date>", "source": "...", "data": {...weights dict...}}
    """
    if not WEIGHTS_PATH.exists():
        raise FileNotFoundError(f"{WEIGHTS_PATH} 不存在, 先跑 derive_sector_weights.py")
    with open(WEIGHTS_PATH, encoding="utf-8") as f:
        data = json.load(f)

    # 真实有效日期由配置文件的 _meta.as_of 决定, 不能虚标为过去的请求日期
    effective_as_of = data.get("_meta", {}).get("as_of")
    if not effective_as_of:
        effective_as_of = date or datetime.now().strftime("%Y-%m-%d")

    return {
        "as_of": effective_as_of,
        "source": str(WEIGHTS_PATH.relative_to(PROJECT_ROOT)),
        "data": data,
    }


def save_live_cache(snapshot: dict, date: str = None) -> Path | None:
    """写 1d cache JSON.

    安全保护: 若请求日期早于快照的实际生效日期 (date < snapshot["as_of"]),
    禁止将未来数据伪造成历史日期的快照落盘, 避免污染历史数据.
    """
    snap_as_of = snapshot.get("as_of", "")
    if date and snap_as_of and date < snap_as_of:
        logger.warning(
            f"[weights] 拒绝写入伪历史快照: 请求日期 {date} < 快照实际生效日期 {snap_as_of}"
        )
        return None

    target_date = date or snap_as_of or datetime.now().strftime("%Y-%m-%d")
    path = _cache_path(target_date)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2, ensure_ascii=False)
    return path


def _discover_all_weight_versions() -> list[tuple[str, dict]]:
    """收集所有可用的权重版本 (按生效日期 effective_date 排序).

    Returns:
        List of (effective_date, weights_dict)
    """
    versions: list[tuple[str, dict]] = []

    # 1. 主配置文件
    if WEIGHTS_PATH.exists():
        try:
            with open(WEIGHTS_PATH, encoding="utf-8") as f:
                cfg_data = json.load(f)
            eff_date = cfg_data.get("_meta", {}).get("as_of", "")
            if eff_date:
                versions.append((eff_date, cfg_data))
        except Exception as e:
            logger.warning(f"[weights] 读取 {WEIGHTS_PATH} 失败: {e}")

    # 2. 缓存目录中真实历史快照
    if CACHE_DIR.exists():
        for p in CACHE_DIR.glob("sector_weights_live_*.json"):
            m = re.search(r"sector_weights_live_(\d{4}-\d{2}-\d{2})\.json$", p.name)
            if not m:
                continue
            file_date = m.group(1)
            try:
                with open(p, encoding="utf-8") as f:
                    snap = json.load(f)
                data = snap.get("data", snap)
                snap_meta_as_of = data.get("_meta", {}).get("as_of") or snap.get("as_of") or file_date
                # 仅当快照真实生效日期 <= 文件日期时, 证明该快照是合法的历史记录 (非未来伪装文件)
                if snap_meta_as_of <= file_date:
                    versions.append((file_date, data))
            except Exception:
                continue

    # 按有效日期从早到晚排序
    versions.sort(key=lambda x: x[0])
    return versions


def load_live_or_static(
    date: str = None,
    use_cache: bool = True,
    allow_future_fallback: bool = True,
) -> dict:
    """加载指定日期的有效权重.

    规则:
    1. 寻找 effective_date <= date 的最近权重版本.
    2. 若找不到任何有效版本 (请求日早于所有可用版本的起始日):
       - 禁止悄悄直接返回未来配置!
       - 若 allow_future_fallback=True: 返回带有明确 `_meta.is_historical_fallback=True`
         及原始生效日期警告的近似版本, 绝不在磁盘生成伪历史缓存文件.
       - 若 allow_future_fallback=False: 抛出 FileNotFoundError.
    """
    req_date = date or datetime.now().strftime("%Y-%m-%d")

    # 如果启用了 cache 并且存在当天的确切 cache 文件
    if use_cache:
        exact_cache = _cache_path(req_date)
        if exact_cache.exists():
            try:
                with open(exact_cache, encoding="utf-8") as f:
                    snap = json.load(f)
                snap_data = snap.get("data", snap)
                snap_eff = snap_data.get("_meta", {}).get("as_of") or snap.get("as_of")
                if snap_eff and snap_eff <= req_date:
                    return copy.deepcopy(snap_data)
            except Exception:
                pass

    versions = _discover_all_weight_versions()

    # 筛选 effective_date <= req_date 的版本
    valid_candidates = [v for v in versions if v[0] <= req_date]

    if valid_candidates:
        # 取有效日期最近的版本
        latest_valid_date, latest_valid_data = max(valid_candidates, key=lambda x: x[0])
        # 如果当天命中且需要写 cache (例如当前日期拉取)
        if use_cache and req_date == latest_valid_date:
            cache_path = _cache_path(req_date)
            if not cache_path.exists():
                save_live_cache({
                    "as_of": latest_valid_date,
                    "source": str(WEIGHTS_PATH.relative_to(PROJECT_ROOT)) if WEIGHTS_PATH.exists() else "discovered",
                    "data": latest_valid_data,
                }, req_date)
        return copy.deepcopy(latest_valid_data)

    # 没有找到 effective_date <= req_date 的版本
    if not allow_future_fallback:
        raise FileNotFoundError(
            f"历史行业权重不可用: 请求日期 {req_date} 早于所有已知版本生效日期"
        )

    # Fallback 模式: 使用最早可用版本作为近似, 但显式标记元数据, 绝不伪装为该日期的真实权重
    if not versions:
        snap = pull_live_weights(req_date)
        return copy.deepcopy(snap["data"])

    earliest_date, earliest_data = min(versions, key=lambda x: x[0])
    fallback_data = copy.deepcopy(earliest_data)
    fallback_data.setdefault("_meta", {})
    fallback_data["_meta"]["is_historical_fallback"] = True
    fallback_data["_meta"]["requested_as_of"] = req_date
    fallback_data["_meta"]["effective_date"] = earliest_date
    fallback_data["_meta"]["warning"] = (
        f"历史权重在 {req_date} 不可用 (最早可用版本为 {earliest_date}); "
        f"当前返回未来权重作为近似参考，历史归因可能存在前瞻偏差。"
    )
    logger.warning(fallback_data["_meta"]["warning"])
    return fallback_data


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
