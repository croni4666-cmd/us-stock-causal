"""src/yfinance_rate_limit.py - yfinance 限流检测 + 优雅降级 (v0.6.8j P7-6)

设计:
- 捕获 yfinance.exceptions.YFRateLimitError → 写 data/cache/yfinance_rate_limit.json
- 提供 is_rate_limited() 给 cache.update_or_fetch 用: 限流时不再尝试 yfinance
- 24h cooldown 自愈, 也可以手动 clear
- Phase 8 alert 可以读 get_rate_limit_info() 推送"yfinance 限流, 用 cache only"通知

Why P7-6:
- v0.6.8b hotfix 实证 yfinance 2026 持续限流 (YFRateLimitError)
- 限流时 cache miss 拉新数据会失败 → daily cron 增量挂
- 没有限流检测的话, cron 静默挂掉, 第二天才发现没数据
- 修法: 检测限流 + 写 cache + 下次 fetch 前先 check → 跳过 → 用现有 cache
"""
from __future__ import annotations
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# yfinance 限流异常 (v0.2.0+ 都有, 旧版可能没)
try:
    from yfinance.exceptions import YFRateLimitError  # type: ignore
    _HAS_YF_RATE_LIMIT_ERROR = True
except ImportError:
    # 旧 yfinance 没有这个, 用 requests 的 429 替代
    YFRateLimitError = Exception  # type: ignore
    _HAS_YF_RATE_LIMIT_ERROR = False


# 限流状态 cache
RATE_LIMIT_CACHE = PROJECT_ROOT / "data" / "cache" / "yfinance_rate_limit.json"
DEFAULT_COOLDOWN_HOURS = 24


def record_rate_limit(symbol: str, exc: Exception, duration_hours: int = DEFAULT_COOLDOWN_HOURS) -> dict:
    """记录一次 yfinance 限流事件

    Args:
        symbol: 触发限流的 ticker
        exc: 异常对象
        duration_hours: 限流持续时间估计 (默认 24h, Yahoo 经验值)

    Returns:
        写入的 rate limit info dict
    """
    now = datetime.now()
    expires_at = now + timedelta(hours=duration_hours)

    # 读旧记录, 累加 hit_count
    existing = {}
    if RATE_LIMIT_CACHE.exists():
        try:
            with open(RATE_LIMIT_CACHE, encoding="utf-8") as f:
                existing = json.load(f)
        except (json.JSONDecodeError, OSError):
            existing = {}

    info = {
        "first_detected_at": existing.get("first_detected_at", now.isoformat()),
        "last_detected_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
        "cooldown_hours": duration_hours,
        "hit_count": existing.get("hit_count", 0) + 1,
        "last_symbol": symbol,
        "last_error": f"{type(exc).__name__}: {str(exc)[:200]}",
        "status": "active",
    }

    RATE_LIMIT_CACHE.parent.mkdir(parents=True, exist_ok=True)
    with open(RATE_LIMIT_CACHE, "w", encoding="utf-8") as f:
        json.dump(info, f, indent=2, ensure_ascii=False)

    return info


def is_rate_limited() -> bool:
    """检查当前是否在 yfinance 限流期

    Returns:
        True = 限流中 (跳过 yfinance fetch, 用 cache only)
        False = 正常
    """
    if not RATE_LIMIT_CACHE.exists():
        return False
    try:
        with open(RATE_LIMIT_CACHE, encoding="utf-8") as f:
            info = json.load(f)
    except (json.JSONDecodeError, OSError):
        return False
    if info.get("status") != "active":
        return False
    expires_at = datetime.fromisoformat(info["expires_at"])
    return datetime.now() < expires_at


def get_rate_limit_info() -> Optional[dict]:
    """读限流状态 (Phase 8 alert 用)

    Returns:
        rate limit info dict or None
    """
    if not RATE_LIMIT_CACHE.exists():
        return None
    try:
        with open(RATE_LIMIT_CACHE, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def clear_rate_limit() -> bool:
    """手动清除限流状态 (admin 工具 / 24h 后自动)

    Returns:
        True = 清了 / False = 没记录
    """
    if not RATE_LIMIT_CACHE.exists():
        return False
    RATE_LIMIT_CACHE.unlink()
    return True


def is_yf_rate_limit_error(exc: BaseException) -> bool:
    """检查 exception 是不是 yfinance 限流

    兼容老版本 yfinance (没 YFRateLimitError) 的回退:
    - requests.exceptions.HTTPError 429
    - 异常消息含 'Too Many Requests' / 'rate limit' / '429'
    """
    if _HAS_YF_RATE_LIMIT_ERROR and isinstance(exc, YFRateLimitError):
        return True
    # requests.HTTPError 429
    try:
        import requests
        if isinstance(exc, requests.exceptions.HTTPError):
            if getattr(exc.response, "status_code", None) == 429:
                return True
    except ImportError:
        pass
    # message-based 回退
    msg = str(exc).lower()
    if any(kw in msg for kw in ["too many requests", "rate limit", "429", "yfratelimit"]):
        return True
    return False


__all__ = [
    "YFRateLimitError",
    "is_yf_rate_limit_error",
    "record_rate_limit",
    "is_rate_limited",
    "get_rate_limit_info",
    "clear_rate_limit",
    "RATE_LIMIT_CACHE",
    "DEFAULT_COOLDOWN_HOURS",
]
