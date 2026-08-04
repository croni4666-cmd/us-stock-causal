"""src/notify.py - Windows toast notification (v0.6.9h P8-7)

设计:
- cron 跑完有 alert 时弹窗, user 立即知道
- 无 alert 时不弹 (避免噪音)
- 静默 fallback: plyer 在某些环境 (Linux/WSL) 不可用, 自动降级到 log
- Hobbyist ceiling: 纯本地, 无 hosted service, 0 成本
"""
from __future__ import annotations
import sys
from pathlib import Path
from typing import Iterable

from loguru import logger

APP_NAME = "us-stock-causal"
DEFAULT_TIMEOUT = 10  # 秒, 0 = 不自动消失


def _format_alert_summary(alerts: list[dict], max_items: int = 3) -> str:
    """取前 N 个 alert 拼成短 summary, Windows toast 正文 ≤ 256 字符"""
    if not alerts:
        return "0 alert"
    summary_lines = [f"{len(alerts)} alert(s):"]
    for a in alerts[:max_items]:
        # 短格式: "[type] subject"
        summary_lines.append(f"- {a.get('type', '?')}: {a.get('subject', '?')}")
    if len(alerts) > max_items:
        summary_lines.append(f"  ... 详见 alert log")
    return "\n".join(summary_lines)


def notify_if_alerts(alerts: list[dict], date: str, timeout: int = DEFAULT_TIMEOUT) -> bool:
    """alerts 非空时弹 Windows toast, 返回是否成功弹

    Args:
        alerts: list of alert dicts (from src.alert_logger)
        date: YYYY-MM-DD, 写进 toast 标题
        timeout: toast 持续秒数, 0 = 不自动消失

    Returns:
        True = 弹窗成功 / False = 无 alert 或 plyer 不可用
    """
    if not alerts:
        logger.info("[notify] 无 alert, 不弹 toast")
        return False

    title = f"us-stock-causal {date}: {len(alerts)} alert"
    message = _format_alert_summary(alerts)

    try:
        from plyer import notification
        notification.notify(
            title=title,
            message=message,
            app_name=APP_NAME,
            timeout=timeout,
        )
        logger.info(f"[notify] toast 弹出: {title}")
        return True
    except Exception as e:
        # plyer 在 Windows headless / WSL / 某些 server 没 toast backend
        # 降级到 log (避免 daily cron 假死)
        logger.warning(f"[notify] plyer 不可用 ({type(e).__name__}: {e}), 降级到 log")
        logger.warning(f"[notify] {title}\n{message}")
        return False


def notify_text(title: str, message: str, timeout: int = DEFAULT_TIMEOUT) -> bool:
    """通用 toast 通知, 跟 alerts 无关

    Args:
        title: 弹窗标题
        message: 弹窗正文
        timeout: 持续秒数
    """
    try:
        from plyer import notification
        notification.notify(
            title=title,
            message=message,
            app_name=APP_NAME,
            timeout=timeout,
        )
        return True
    except Exception as e:
        logger.warning(f"[notify] plyer 不可用 ({type(e).__name__}: {e}), 降级到 log")
        logger.warning(f"[notify] {title}\n{message}")
        return False
