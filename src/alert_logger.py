"""src/alert_logger.py - 本地 alert log (Phase 8 P8-6, v0.6.8n)

职责:
- 写 data/cache/alerts/alerts_<date>.json (累积, 同日 run 覆盖)
- 终端 stdout 显眼 [ALERT] (替代飞书 card, 飞书 2026-07-26 archived)
- dedup by alert.id (同日同 alert 只留 first_seen)

设计 (来自 ROADMAP.md Phase 8 段):
- alert = {id, type, severity, subject, message, details, timestamp, first_seen}
- severity: info / warning / error
- type: stale / residual / vix_spike / ticker_fail / parquet_corrupt
"""
from __future__ import annotations
import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]

try:
    sys_path = PROJECT_ROOT
    import sys
    if str(sys_path) not in sys.path:
        sys.path.insert(0, str(sys_path))
except Exception:
    pass

ALERT_DIR = PROJECT_ROOT / "data" / "cache" / "alerts"

# 合法 severity / type (给 healthcheck runner 校验用)
SEVERITIES = ["info", "warning", "error"]
TYPES = ["stale", "residual", "vix_spike", "ticker_fail", "parquet_corrupt"]


def _alert_id(alert_type: str, subject: str, message: str) -> str:
    """生成稳定 alert ID (同 type+subject+message = 同 id, 用于 dedup)"""
    h = hashlib.md5(f"{alert_type}|{subject}|{message}".encode("utf-8")).hexdigest()[:8]
    return f"{alert_type}_{h}"


def _alert_file(date_str: str) -> Path:
    return ALERT_DIR / f"alerts_{date_str}.json"


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def make_alert(
    alert_type: str,
    subject: str,
    message: str,
    severity: str = "warning",
    details: Optional[dict] = None,
) -> dict:
    """构造一个 alert dict (caller 不直接写, 走这个保证 schema 完整)"""
    if alert_type not in TYPES:
        raise ValueError(f"alert_type {alert_type!r} not in {TYPES}")
    if severity not in SEVERITIES:
        raise ValueError(f"severity {severity!r} not in {SEVERITIES}")
    now = _now_iso()
    return {
        "id": _alert_id(alert_type, subject, message),
        "type": alert_type,
        "severity": severity,
        "subject": subject,
        "message": message,
        "details": details or {},
        "timestamp": now,
        "first_seen": now,
    }


def write_alerts(date_str: str, alerts: list[dict]) -> Path:
    """写当日 alerts (overwrite, 但合并已有 alerts 的 first_seen)

    Args:
        date_str: YYYY-MM-DD
        alerts: list of alert dicts (from make_alert)

    Returns:
        Path to alerts_<date>.json
    """
    ALERT_DIR.mkdir(parents=True, exist_ok=True)
    f = _alert_file(date_str)

    # 合并已有 first_seen (dedup)
    existing = read_alerts(date_str)
    by_id = {a["id"]: a for a in existing}
    for a in alerts:
        if a["id"] in by_id:
            # 保留 first_seen, 更新 timestamp
            a["first_seen"] = by_id[a["id"]]["first_seen"]
        by_id[a["id"]] = a
    merged = list(by_id.values())

    # status
    has_error = any(a["severity"] == "error" for a in merged)
    has_warning = any(a["severity"] == "warning" for a in merged)
    status = "errors" if has_error else ("warnings" if has_warning else "ok")

    # summary
    summary = {t: sum(1 for a in merged if a["type"] == t) for t in TYPES}

    payload = {
        "as_of": date_str,
        "status": status,
        "summary": summary,
        "alerts": merged,
    }
    f.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return f


def read_alerts(date_str: str) -> list[dict]:
    """读当日 alerts (没文件返 [])"""
    f = _alert_file(date_str)
    if not f.exists():
        return []
    try:
        payload = json.loads(f.read_text(encoding="utf-8"))
        return payload.get("alerts", [])
    except (json.JSONDecodeError, OSError):
        return []


def clear_alerts(date_str: str) -> bool:
    """清空当日 alerts (给 admin 手动 reset 用)"""
    f = _alert_file(date_str)
    if f.exists():
        f.unlink()
        return True
    return False


# ANSI 颜色 (Windows Terminal / 现代 terminal 支持, 老 cmd 不支持但也无害)
_RED = "\033[91m"
_YELLOW = "\033[93m"
_CYAN = "\033[96m"
_RESET = "\033[0m"


def render_terminal(alerts: list[dict], use_color: bool = True) -> str:
    """把 alerts 渲染成终端显眼输出 (无 alert 返空字符串)

    格式:
        [ALERT] [error] parquet_corrupt: data/raw/AAPL.parquet - cannot read
                  details: {"file": "...", "error": "..."}
    """
    if not alerts:
        return ""
    lines = []
    for a in alerts:
        sev = a.get("severity", "warning")
        if use_color:
            if sev == "error":
                color = _RED
            elif sev == "warning":
                color = _YELLOW
            else:
                color = _CYAN
            tag = f"{color}[{sev.upper():7s}]{_RESET}"
        else:
            tag = f"[{sev.upper():7s}]"
        line = f"[ALERT] {tag} {a.get('type','?'):15s} | {a.get('subject','?'):50s} | {a.get('message','')}"
        lines.append(line)
    return "\n".join(lines)


def print_alerts(alerts: list[dict], use_color: bool = True) -> None:
    """print + 包含摘要 (给 daily_report.py 调, 直接打终端)"""
    out = render_terminal(alerts, use_color=use_color)
    if out:
        print(out)
        n_error = sum(1 for a in alerts if a.get("severity") == "error")
        n_warn = sum(1 for a in alerts if a.get("severity") == "warning")
        n_info = sum(1 for a in alerts if a.get("severity") == "info")
        print(f"[ALERT] 总计: {len(alerts)} 个 (error={n_error}, warning={n_warn}, info={n_info})")


__all__ = [
    "ALERT_DIR",
    "SEVERITIES",
    "TYPES",
    "make_alert",
    "write_alerts",
    "read_alerts",
    "clear_alerts",
    "render_terminal",
    "print_alerts",
]
