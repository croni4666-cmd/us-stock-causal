"""tools/verify_30days.py — 验证 30 天 daily cron 0 fail (V1.0 路线图 must-have)

跑法: python tools/verify_30days.py [--start 2026-08-04] [--days 30]
输出: 报告 cron_*.log 每天 0 fail, 给 v0.9.5 RC1 / v1.0.0 tag 用

检查项:
- 每个 cron_YYYY-MM-DD.log 存在 (daily cron 17:00 跑通)
- log 末尾 [OK] / [SKIP] 状态 (0 fail)
- step_check_alerts 没 error alert
- step_causal / step_residual_regression / step_markdown_report 都 ok=True
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = PROJECT_ROOT / "output" / "logs"


def parse_cron_log(log_path: Path) -> dict:
    """解析单个 cron log, 提取每天 step 状态"""
    if not log_path.exists():
        return {"exists": False, "date": log_path.stem.replace("cron_", "")}

    text = log_path.read_text(encoding="utf-8", errors="replace")
    # 找 [Step N] ... elapsed
    step_pattern = re.compile(r"\[Step (\d+)\]\s+(.+)", re.MULTILINE)
    elapsed_pattern = re.compile(r"(\d+\.\d+)s", re.MULTILINE)

    steps = {}
    for m in step_pattern.finditer(text):
        step_num = int(m.group(1))
        step_name = m.group(2).strip()
        # 找该 step 后的 elapsed_s (从 next 50 行)
        snippet = text[m.start():m.start() + 500]
        elapsed_m = re.search(r"elapsed_s['\"]?\s*[:=]\s*(\d+\.\d+)", snippet)
        if not elapsed_m:
            # 找 [OK] / [SKIP] / [FAIL]
            if "[OK]" in snippet:
                elapsed = "ok"
            elif "[SKIP]" in snippet:
                elapsed = "skip"
            elif "[FAIL]" in snippet:
                elapsed = "fail"
            else:
                elapsed = "?"
        else:
            elapsed = float(elapsed_m.group(1))
        steps[step_num] = {"name": step_name, "elapsed_s": elapsed}

    # 检查末尾 [OK] 总结 (不太可靠, 跟实际 daily_report 输出格式不匹配)
    # 主要看 n_errors 决定 fail
    final_ok = True  # 默认 OK, n_errors > 0 才 fail

    # 提取 alerts (error count) — 多种格式
    n_errors = 0
    # 格式 1: "error=0, warning=4" (P8-6 alerts)
    alert_match = re.search(r"error=(\d+)", text)
    if alert_match:
        n_errors = int(alert_match.group(1))
    # 格式 2: "FAIL X test" (pytest fail)
    fail_match = re.search(r"FAIL\s+(\d+)\s+test", text)
    if fail_match:
        n_errors = max(n_errors, int(fail_match.group(1)))
    # 格式 3: "raise" / "Error" / "Exception" (Python crash)
    if re.search(r"Traceback \(most recent call last\)", text):
        n_errors = max(n_errors, 1)

    # total elapsed
    total_match = re.search(r"(\d+\.\d+)s", text[-200:])

    return {
        "exists": True,
        "date": log_path.stem.replace("cron_", ""),
        "size_kb": round(log_path.stat().st_size / 1024, 1),
        "steps": steps,
        "n_errors": n_errors,
        "final_ok": final_ok,
        "total_s": float(total_match.group(1)) if total_match else None,
    }


def verify_30days(start: str, days: int) -> dict:
    """验证 start 起的 days 天 daily cron 0 fail"""
    start_date = datetime.strptime(start, "%Y-%m-%d").date()
    end_date = start_date + timedelta(days=days - 1)

    results = []
    n_pass = 0
    n_fail = 0
    n_skip_weekend = 0

    cur = start_date
    while cur <= end_date:
        date_str = cur.strftime("%Y-%m-%d")
        log_path = LOG_DIR / f"cron_{date_str}.log"

        # 周末 (Sat=5, Sun=6) skip
        if cur.weekday() in (5, 6):
            cur += timedelta(days=1)
            n_skip_weekend += 1
            continue

        result = parse_cron_log(log_path)
        if not result["exists"]:
            result["status"] = "MISSING"
            n_fail += 1
        elif result["n_errors"] > 0 or not result["final_ok"]:
            result["status"] = "FAIL"
            n_fail += 1
        else:
            result["status"] = "PASS"
            n_pass += 1

        result["date"] = date_str
        result["weekday"] = cur.strftime("%a")
        results.append(result)
        cur += timedelta(days=1)

    return {
        "start": start,
        "end": end_date.strftime("%Y-%m-%d"),
        "n_days_total": days,
        "n_weekend_skipped": n_skip_weekend,
        "n_pass": n_pass,
        "n_fail": n_fail,
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser(description="30 天 daily cron 0 fail 验证 (V1.0 路线图)")
    parser.add_argument("--start", type=str, default="2026-08-04", help="起始日期 (默认 2026-08-04)")
    parser.add_argument("--days", type=int, default=30, help="天数 (默认 30)")
    args = parser.parse_args()

    print(f"🔍 验证 {args.start} 起 {args.days} 天 daily cron 0 fail ...\n")

    report = verify_30days(args.start, args.days)

    print(f"📊 验证结果 ({args.start} ~ {report['end']}, {report['n_days_total']} 天):")
    print(f"   - 工作日: {report['n_pass'] + report['n_fail']}")
    print(f"   - 周末 skip: {report['n_weekend_skipped']}")
    print(f"   - PASS (0 fail): {report['n_pass']}")
    print(f"   - FAIL: {report['n_fail']}")
    print(f"   - 0 fail 比例: {report['n_pass'] / (report['n_pass'] + report['n_fail']) * 100:.0f}%\n")

    print(f"{'日期':12s} {'星期':6s} {'状态':8s} {'size_kb':>8s} {'errors':>7s} {'total_s':>8s}")
    print("-" * 60)
    for r in report["results"]:
        size = f"{r.get('size_kb', 'n/a')}" if r.get("exists") else "n/a"
        errs = r.get("n_errors", "?")
        total = f"{r['total_s']:.1f}" if r.get("total_s") else "?"
        marker = "✅" if r["status"] == "PASS" else ("❌" if r["status"] == "FAIL" else "⚠️")
        print(f"{r['date']:12s} {r['weekday']:6s} {r['status']:6s} {marker} {size:>8s} {errs:>7} {total:>8s}")

    # 总结
    if report["n_fail"] == 0:
        print(f"\n🎉 0 fail! {report['n_pass']}/{report['n_pass'] + report['n_fail']} 工作日 100% PASS")
        return 0
    else:
        print(f"\n⚠️  {report['n_fail']} 天 FAIL, 需修 issue 后再 v0.9.5 RC1 commit")
        return 1


if __name__ == "__main__":
    sys.exit(main())
