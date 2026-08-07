"""src/retry.py — 统一 retry 抽象 (v0.6.9m, P8-5)

P8-5 错误恢复 (v1.0 路线图 must-have):
- 统一 tenacity-based retry 装饰器
- 指数退避: 1s / 2s / 4s (3 重, 跟 data.fetch 旧手写一致)
- 优雅降级: 3 重全 fail 抛 RetryError, 上层 catch 后用 cache / 降级
- 集成到 daily_report: step_fetch + step_check_alerts
- retry 次数 + 失败 reason 写到 data/cache/retry_log.json (audit trail)

设计:
- @retry_yfinance: 给 yfinance fetch 用 (3 重, 指数退避)
- @retry_gdelt: 给 GDELT 用 (3 重, 限流额外 wait)
- @retry_io: 给 parquet I/O 临时错用 (3 重, 短退避 0.5s/1s/2s)
- 不要给纯计算函数 (OLS, SCM fit) 加 retry — 失败 = 算错, 重试也错
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Callable, Optional

from tenacity import (
    RetryError,
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    wait_fixed,
    before_sleep_log,
)

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RETRY_LOG = PROJECT_ROOT / "data" / "cache" / "retry_log.json"


# ===== 核心 retry 装饰器 =====

def retry_yfinance(
    max_attempts: int = 3,
    multiplier: float = 1.0,
    min_wait: float = 1.0,
    max_wait: float = 4.0,
):
    """yfinance 拉数据 retry 装饰器
    - 3 重 (默认)
    - 指数退避 1s / 2s / 4s (multiplier=1, min=1, max=4)
    - 捕获所有 Exception (除 KeyboardInterrupt)
    - 重试用尽抛 RuntimeError (跟旧手写循环一致, 便于上层 catch)
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            retryer = Retrying(
                stop=stop_after_attempt(max_attempts),
                wait=wait_exponential(multiplier=multiplier, min=min_wait, max=max_wait),
                retry=retry_if_exception_type(Exception),
                reraise=False,  # 用 RetryError 包, 我们统一转 RuntimeError
            )
            try:
                return retryer(func, *args, **kwargs)
            except RetryError as e:
                # tenacity 9.x: 内部 last_attempt.exception() 拿原 exception
                last_exc = getattr(e, "last_attempt", None)
                err_msg = str(last_exc.exception()) if last_exc else str(e)
                _log_retry(func.__name__, args, kwargs, "exhausted", err_msg)
                raise RuntimeError(f"{func.__name__}: {max_attempts} 重试全失败: {err_msg}") from e
        return wrapper
    return decorator


def retry_gdelt(
    max_attempts: int = 3,
    multiplier: float = 1.0,
    min_wait: float = 5.0,
    max_wait: float = 20.0,
):
    """GDELT 拉数据 retry 装饰器
    - 3 重 (默认)
    - 指数退避 5s / 10s / 20s (GDELT 限流友好)
    - 配合 GDELT 1h cache 避免频繁拉
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            retryer = Retrying(
                stop=stop_after_attempt(max_attempts),
                wait=wait_exponential(multiplier=multiplier, min=min_wait, max=max_wait),
                retry=retry_if_exception_type(Exception),
                reraise=False,
            )
            try:
                return retryer(func, *args, **kwargs)
            except RetryError as e:
                last_exc = getattr(e, "last_attempt", None)
                err_msg = str(last_exc.exception()) if last_exc else str(e)
                _log_retry(func.__name__, args, kwargs, "exhausted", err_msg)
                raise RuntimeError(f"{func.__name__}: {max_attempts} 重试全失败: {err_msg}") from e
        return wrapper
    return decorator


def retry_io(
    max_attempts: int = 3,
    min_wait: float = 0.5,
    max_wait: float = 2.0,
):
    """I/O retry 装饰器 (parquet 临时错, 网络瞬断)
    - 3 重
    - 短退避 0.5s / 1s / 2s
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            retryer = Retrying(
                stop=stop_after_attempt(max_attempts),
                wait=wait_exponential(multiplier=1.0, min=min_wait, max=max_wait),
                retry=retry_if_exception_type((IOError, OSError)),
                reraise=False,
            )
            try:
                return retryer(func, *args, **kwargs)
            except RetryError as e:
                last_exc = getattr(e, "last_attempt", None)
                err_msg = str(last_exc.exception()) if last_exc else str(e)
                _log_retry(func.__name__, args, kwargs, "exhausted", err_msg)
                raise RuntimeError(f"{func.__name__}: {max_attempts} 重试全失败: {err_msg}") from e
        return wrapper
    return decorator


# ===== Audit log =====

def _log_retry(func_name: str, args: tuple, kwargs: dict, status: str, err_msg: str) -> None:
    """写 retry log 到 data/cache/retry_log.json (append)
    - 用途: 排查 daily cron 偶尔 fail 时, 看是不是 retry 用尽
    - 不抛异常 (log 写失败不影响主流程)
    """
    try:
        RETRY_LOG.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "func": func_name,
            "args_preview": _args_preview(args),
            "status": status,
            "error": err_msg[:200],  # 截断避免 log 过大
        }
        # append 模式 (一行一个 JSON object)
        with open(RETRY_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as log_err:
        logger.warning(f"[retry] 写 retry log 失败: {log_err}")


def _args_preview(args: tuple) -> str:
    """截断 args preview, 避免 log 过大 (e.g. 大 DataFrame)"""
    if not args:
        return ""
    first = str(args[0])[:50] if args else ""
    return f"({first}, ...) n_args={len(args)}"


def read_retry_log(limit: int = 20) -> list[dict]:
    """读 retry log (debug / test 用)
    Returns: 最新 limit 条 entry (倒序)
    """
    if not RETRY_LOG.exists():
        return []
    try:
        with open(RETRY_LOG, "r", encoding="utf-8") as f:
            lines = f.readlines()
        entries = []
        for line in lines[-limit:]:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return list(reversed(entries))
    except Exception as e:
        logger.warning(f"[retry] 读 retry log 失败: {e}")
        return []


def clear_retry_log() -> int:
    """清 retry log (tests 用)
    Returns: 删除的行数
    """
    if not RETRY_LOG.exists():
        return 0
    lines = RETRY_LOG.read_text(encoding="utf-8").splitlines()
    RETRY_LOG.unlink()
    return len(lines)


# ===== Health check =====

def retry_health_check() -> dict:
    """retry 机制健康检查 (daily_report 启动时可调)
    Returns: { "log_path": ..., "log_size_kb": ..., "recent_fail_count": int }
    """
    if not RETRY_LOG.exists():
        return {"log_path": str(RETRY_LOG), "log_size_kb": 0.0, "recent_fail_count": 0}
    size_kb = RETRY_LOG.stat().st_size / 1024
    # 看最近 100 条有几个 exhausted
    recent = read_retry_log(limit=100)
    fail_count = sum(1 for e in recent if e.get("status") == "exhausted")
    return {
        "log_path": str(RETRY_LOG),
        "log_size_kb": round(size_kb, 2),
        "recent_fail_count": fail_count,
    }
