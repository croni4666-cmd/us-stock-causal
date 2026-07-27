"""examples/daily_report.py - 每日报告编排 (v0.6.8l P5-2 gate)

一个命令跑全 pipeline:
  1. fetch (optional, --skip-fetch 用 cache)
  2. attribution (4 指数 × 3 窗口)
  3. residual regression (P7-5 baseline 比对)
  4. markdown report (5 段制)
  5. HTML report (含 K 线图)
  6. performance dashboard (中文 Google 风格表格)
  7. alert check (P8-6 写 data/cache/alerts/alerts_<date>.json, 本脚本读)
  8. 打印终端摘要

设计原则 (P5-2 local):
- **本地化优先**: 输出写本地 `output/` + `data/cache/alerts/`, 不依赖 hosted service
- **graceful degradation**: 每步 fail 不阻塞下一步 (除非关键步骤)
- **importable**: 写函数 `run_daily_report()`, smoke test 也能跑
- **可重入**: 同一天跑多次覆盖旧 output, 不留垃圾
"""
from __future__ import annotations

import sys
import time
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 强制 UTF-8 输出 (避免 Windows GBK)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from src import proxy  # noqa: F401 (proxy setup side-effect)
from src.report import render_full_report
from src.report_html import render_html_report
from src.performance_dashboard import render_performance_table, render_performance_table_html
from src.residual_regression import capture_residuals, load_baseline, compare_to_baseline

# 4 指数 (跟 report.py 一致)
INDICES = ["DIA", "QQQ", "RSP", "QQQE"]
WINDOWS = [1, 5, 20]

# output / cache 目录
OUTPUT_DIR = PROJECT_ROOT / "output"
ALERT_DIR = PROJECT_ROOT / "data" / "cache" / "alerts"


def _step_banner(step: int, name: str):
    print()
    print("=" * 72)
    print(f"[Step {step}] {name}")
    print("=" * 72)


def step_fetch(skip: bool = False) -> dict:
    """Step 1: 拉数据 (可选)"""
    _step_banner(1, "拉数据 (fetch_all)")
    if skip:
        print("  [SKIP] --skip-fetch, 用 cache")
        return {"ok": "skip", "elapsed_s": 0}

    from examples.fetch_all import main as fetch_all_main
    t0 = time.time()
    try:
        fetch_all_main()
        return {"ok": True, "elapsed_s": round(time.time() - t0, 1)}
    except SystemExit:
        # fetch_all.py 调 sys.exit(0) on success
        return {"ok": True, "elapsed_s": round(time.time() - t0, 1)}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "elapsed_s": round(time.time() - t0, 1)}


def step_attribution() -> dict:
    """Step 2: 归因 (4 指数 × 3 窗口)"""
    _step_banner(2, "归因 (4 指数 × 3 窗口)")
    from src.attribution import attribute_all_indices
    t0 = time.time()
    results_by_window = {}
    for lb in WINDOWS:
        results = attribute_all_indices(date=None, lookback_days=lb, symbols=INDICES)
        results_by_window[lb] = results
        for r in results:
            res = r["residual_pct"]
            print(f"  {r['index']:6s} {lb:2d}d: actual={r['actual_return_pct']:+.3f}%  "
                  f"predicted={r['predicted_return_pct']:+.3f}%  residual={res:+.3f}%")
    return {"ok": True, "results": results_by_window, "elapsed_s": round(time.time() - t0, 1)}


def step_residual_regression() -> dict:
    """Step 3: 残差回归测试 (P7-5) — 跟 v0.6.8f baseline 比对"""
    _step_banner(3, "残差回归 (P7-5 baseline 比对)")
    try:
        baseline = load_baseline()
    except FileNotFoundError as e:
        print(f"  [WARN] {e}")
        return {"ok": "skip", "reason": "no baseline", "elapsed_s": 0}

    t0 = time.time()
    current = capture_residuals()
    ok, violations = compare_to_baseline(current, baseline, tolerance=1.5, abs_floor=0.05)

    if ok:
        print(f"  [OK] 12/12 残差在 baseline 1.5x 范围内")
        for idx in INDICES:
            for lb_str in [str(w) for w in WINDOWS]:
                v = current["residuals"][idx][lb_str]
                print(f"    {idx} {lb_str}d: {v:+.3f}%")
    else:
        print(f"  [FAIL] {len(violations)} 处 regression:")
        for v in violations:
            print(f"    - {v['index']} {v['window']}: "
                  f"baseline {v['baseline_pct']:+.3f}% → current {v['current_pct']:+.3f}% "
                  f"(ratio {v['regression_ratio']}x)")

    return {
        "ok": ok,
        "violations": violations if not ok else [],
        "elapsed_s": round(time.time() - t0, 1),
    }


def step_markdown_report(date_str: str) -> dict:
    """Step 4: Markdown 报告 (5 段制)"""
    _step_banner(4, "Markdown 报告 (5 段制)")
    t0 = time.time()
    try:
        OUTPUT_DIR.mkdir(exist_ok=True)
        md = render_full_report(INDICES)
        md_path = OUTPUT_DIR / f"report_{date_str}.md"
        md_path.write_text(md, encoding="utf-8")
        kb = md_path.stat().st_size / 1024
        print(f"  [OK] {md_path} ({kb:.1f} KB)")
        return {"ok": True, "path": md_path, "size_kb": round(kb, 1), "elapsed_s": round(time.time() - t0, 1)}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "elapsed_s": round(time.time() - t0, 1)}


def step_html_report(date_str: str) -> dict:
    """Step 5: HTML 报告 (含 K 线图)"""
    _step_banner(5, "HTML 报告 (含 K 线图)")
    t0 = time.time()
    try:
        from src.kline import savefig_multi_format
        OUTPUT_DIR.mkdir(exist_ok=True)

        # 找最新的 indices SVG (1y) + gold SVG
        svgs = []
        for pattern in ["indices_2y_*.svg", "gold_1y_*.svg"]:
            matches = sorted(OUTPUT_DIR.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
            if matches:
                svgs.append(matches[0])
        # 兼容旧名字
        if not svgs:
            for pattern in ["indices_*.svg", "gold_*.svg"]:
                matches = sorted(OUTPUT_DIR.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
                if matches:
                    svgs.append(matches[0])

        if not svgs:
            print(f"  [WARN] 没找到 K 线 SVG, 跳过 (先跑 `python examples/indices_chart.py` 和 `plot_gold.py`)")
            return {"ok": "skip", "reason": "no K-line SVG", "elapsed_s": round(time.time() - t0, 1)}

        # 读 markdown
        md_path = OUTPUT_DIR / f"report_{date_str}.md"
        if not md_path.exists():
            print(f"  [WARN] {md_path} 不存在, 跳过 (先跑 Step 4)")
            return {"ok": "skip", "reason": "no MD", "elapsed_s": round(time.time() - t0, 1)}

        md_content = md_path.read_text(encoding="utf-8")
        html = render_html_report(md_content, [str(s) for s in svgs], title=f"us-stock-causal 报告 {date_str}")
        html_path = OUTPUT_DIR / f"report_{date_str}.html"
        html_path.write_text(html, encoding="utf-8")
        kb = html_path.stat().st_size / 1024
        print(f"  [OK] {html_path} ({kb:.1f} KB) + {len(svgs)} SVG")
        return {"ok": True, "path": html_path, "size_kb": round(kb, 1), "elapsed_s": round(time.time() - t0, 1)}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "elapsed_s": round(time.time() - t0, 1)}


def step_performance_dashboard(date_str: str) -> dict:
    """Step 6: Performance Dashboard (中文 Google 风格)"""
    _step_banner(6, "Performance Dashboard (中文 Google 风格)")
    t0 = time.time()
    try:
        OUTPUT_DIR.mkdir(exist_ok=True)
        # HTML 表格写到 output/
        html_doc = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><title>us-stock-causal Performance Dashboard {date_str}</title>
<style>body {{ font-family: 'Microsoft YaHei', sans-serif; max-width: 1100px; margin: 20px auto; padding: 0 20px; }}
h1 {{ font-size: 18px; color: #202124; border-bottom: 2px solid #1a73e8; padding-bottom: 8px; }}
.note {{ color: #5f6368; font-size: 12px; margin: 12px 0; }}</style>
</head><body>
<h1>us-stock-causal — Performance Dashboard ({date_str})</h1>
<p class="note">数据来源: cache parquet + yfinance, 报告时点: {date_str}</p>
{render_performance_table_html()}
</body></html>"""
        out_path = OUTPUT_DIR / f"performance_table_{date_str}.html"
        out_path.write_text(html_doc, encoding="utf-8")
        kb = out_path.stat().st_size / 1024
        print(f"  [OK] {out_path} ({kb:.1f} KB)")
        return {"ok": True, "path": out_path, "size_kb": round(kb, 1), "elapsed_s": round(time.time() - t0, 1)}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "elapsed_s": round(time.time() - t0, 1)}


def step_check_alerts(date_str: str) -> dict:
    """Step 7: 跑 5 类异常检测 (P8-1~5) + 写 alert log (P8-6) + 终端显眼 stdout

    5 类 check 跑法:
      - stale: data/raw/*/ parquet LastWriteTime > 2 工作日
      - residual: 当日归因残差 vs P7-5 baseline 偏差 > 1.5x
      - vix_spike: VIX > 30 或 1 日涨幅 > 15%
      - ticker_fail: yfinance 限流中 或 parquet < 1KB
      - parquet_corrupt: pandas 读失败 或 0 行

    任何 alert 写 data/cache/alerts/alerts_<date>.json (累积, dedup by id)
    + 终端 [ALERT] 显眼输出 (替代飞书 card, 飞书 2026-07-26 archived)
    """
    from src import alert_logger
    from src.checks import stale, residual, vix_spike, ticker_fail, parquet_corrupt
    _step_banner(7, f"Alert Check (5 类异常检测 + 写 log, {date_str})")
    t0 = time.time()

    # 跑 5 check (独立 try/except, 一类 fail 不阻塞其它)
    all_alerts = []
    by_type = {}

    checks = [
        ("stale", stale.check),
        ("residual", residual.check),
        ("vix_spike", vix_spike.check),
        ("ticker_fail", ticker_fail.check),
        ("parquet_corrupt", parquet_corrupt.check),
    ]
    for name, fn in checks:
        try:
            alerts = fn(date_str)
            by_type[name] = len(alerts)
            all_alerts.extend(alerts)
        except Exception as e:
            # check 本身崩了 → 当成 1 个 error alert 写出去
            err = alert_logger.make_alert(
                alert_type=name,
                subject=f"{name}.check()",
                message=f"check 崩了: {type(e).__name__}: {e}",
                severity="error",
                details={"error": str(e), "traceback": str(e.__traceback__)[:500] if e.__traceback__ else ""},
            )
            by_type[name] = 1
            all_alerts.append(err)

    # 写 alert log (overwrite, 但合并 first_seen)
    alert_logger.write_alerts(date_str, all_alerts)

    # 终端显眼输出
    print(f"  跑完 5 check: stale={by_type.get('stale', 0)}, residual={by_type.get('residual', 0)}, "
          f"vix_spike={by_type.get('vix_spike', 0)}, ticker_fail={by_type.get('ticker_fail', 0)}, "
          f"parquet_corrupt={by_type.get('parquet_corrupt', 0)}")
    if all_alerts:
        alert_logger.print_alerts(all_alerts)
    else:
        print(f"  [OK] 无 alert, 健康 ✓")

    n_error = sum(1 for a in all_alerts if a.get("severity") == "error")
    return {
        "ok": n_error == 0,
        "alert_count": len(all_alerts),
        "error_count": n_error,
        "by_type": by_type,
        "path": alert_logger.ALERT_DIR / f"alerts_{date_str}.json",
        "elapsed_s": round(time.time() - t0, 2),
    }


def step_causal(date_str: str) -> dict:
    """Step 8: Pearl-style 因果分析 (Phase 9)

    跑 1 个 L2 干预 query (VIX→QQQ) + 1 个 L3 反事实, 不写 report 数字
    (后续可加到 markdown report 第 6 段 "因果机制")

    Pearl 3 层因果阶梯:
      - L1 关联 (P2 attribution): P(Y|X)
      - L2 干预 (本 step): P(Y|do(X)) — DoWhy + OLS
      - L3 反事实 (本 step): P(Y_x|X',Y') — econml CausalForestDML 简化近似

    DAG: config/causal_dag.yaml (7 节点: 3 macro + 4 指数, 手工)
    """
    from src import causal
    _step_banner(8, f"Causal Analysis (Pearl-style, {date_str})")
    t0 = time.time()

    results = {"ok": True, "queries": [], "elapsed_s": 0}

    try:
        cfg = causal.load_dag_config()
        data = causal.load_dag_data(cfg=cfg)

        # L2 干预 query: VIX → QQQ (经济理论: 应强负)
        vix_qqq = causal.causal_query(treatment="VIX", outcome="QQQ", data=data, cfg=cfg)
        results["queries"].append({
            "type": "L2_intervention",
            "treatment": vix_qqq.treatment,
            "outcome": vix_qqq.outcome,
            "estimate": vix_qqq.estimate,
            "p_value": vix_qqq.p_value,
            "interpretation": vix_qqq.interpretation,
        })
        direction = "↑" if vix_qqq.estimate > 0 else "↓"
        print(f"  [L2 do-calculus] VIX do(+1%) → QQQ: {direction}{abs(vix_qqq.estimate):.4f} "
              f"({abs(vix_qqq.estimate)*100:+.2f}%, p={vix_qqq.p_value:.3f}, n={vix_qqq.n_obs})")
        print(f"    反驳测试 PASS 数: {sum(1 for v in vix_qqq.refutation.values() if 'new_effect' in v)}/3")

        # L3 反事实: 用最近一天, 假设 VIX 比实际低 (恐慌小, 应该利好)
        last_date = str(data.index[-1].date())
        actual_vix = float(data.iloc[-1]["VIX"])
        cf_vix = actual_vix - 0.05
        cf = causal.counterfactual_query(
            date=last_date, treatment="VIX", outcome="QQQ",
            counterfactual_value=cf_vix, data=data, cfg=cfg,
        )
        results["queries"].append({
            "type": "L3_counterfactual",
            "date": cf.date,
            "treatment": cf.treatment,
            "outcome": cf.outcome,
            "actual_outcome": cf.actual_outcome,
            "counterfactual_outcome": cf.counterfactual_outcome,
            "delta": cf.delta,
        })
        print(f"  [L3 counterfactual] {cf.date}: 假设 VIX -5% (从 {actual_vix*100:+.2f}% 到 {cf_vix*100:+.2f}%)")
        print(f"    QQQ 实际 {cf.actual_outcome*100:+.2f}%, 反事实 {cf.counterfactual_outcome*100:+.2f}%, 差 {cf.delta*100:+.2f}%")

    except Exception as e:
        results["ok"] = False
        results["error"] = f"{type(e).__name__}: {e}"
        print(f"  [WARN] causal 失败: {results['error']}")

    results["elapsed_s"] = round(time.time() - t0, 2)
    return results


def print_summary(steps: dict, total_elapsed: float, date_str: str):
    """Step 8: 终端打印摘要"""
    print()
    print("=" * 72)
    print(f"[Summary] us-stock-causal daily report — {date_str}")
    print("=" * 72)
    for name, info in steps.items():
        status = info.get("ok")
        elapsed = info.get("elapsed_s", 0)
        if status is True:
            print(f"  [OK]    {name:25s} ({elapsed}s)")
        elif status == "skip":
            reason = info.get("reason", "")
            print(f"  [SKIP]  {name:25s} {reason}")
        else:
            err = info.get("error", "unknown")
            print(f"  [FAIL]  {name:25s} {err}")

    n_ok = sum(1 for v in steps.values() if v.get("ok") is True)
    n_skip = sum(1 for v in steps.values() if v.get("ok") == "skip")
    n_fail = sum(1 for v in steps.values() if v.get("ok") is False)

    # Alert 摘要 (P8-6) — user 看到这行就知道今天有不有异常
    alert_info = steps.get("check_alerts", {})
    n_alert = alert_info.get("alert_count", 0)
    n_alert_err = alert_info.get("error_count", 0)

    print()
    print(f"  Total: {n_ok} OK / {n_skip} SKIP / {n_fail} FAIL, 耗时 {total_elapsed:.1f}s")
    if n_alert > 0:
        # 显眼色
        _RED = "\033[91m"
        _RESET = "\033[0m"
        print(f"  {_RED}[ALERT] 今日 {n_alert} 个 alert (error {n_alert_err}个), 查看 data/cache/alerts/alerts_{date_str}.json{_RESET}")
    if n_fail > 0:
        print(f"  [WARN] {n_fail} 步失败, 详情见上")
    # 关键 alert 顶部 1 行
    alert_info = steps.get("check_alerts", {})
    if alert_info.get("alert_count", 0) > 0:
        print(f"  [ALERT] 今日 {alert_info['alert_count']} 个告警, 查看 {alert_info.get('path')}")
    print("=" * 72)


def run_daily_report(
    date_str: Optional[str] = None,
    skip_fetch: bool = False,
    skip_md: bool = False,
    skip_html: bool = False,
    skip_dashboard: bool = False,
    verbose: bool = True,
) -> dict:
    """主入口: 跑全 pipeline, 返回每步结果 dict

    Returns:
        {
            "date": "2026-07-26",
            "elapsed_s": 12.3,
            "steps": {
                "fetch": {"ok": bool|str, ...},
                "attribution": {...},
                "residual_regression": {...},
                "markdown_report": {...},
                "html_report": {...},
                "performance_dashboard": {...},
                "check_alerts": {...},
            }
        }
    """
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")

    if verbose:
        print("=" * 72)
        print(f"us-stock-causal — Daily Report  ({date_str})")
        print(f"Run time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Proxy active: {proxy.is_proxied()}")
        print("=" * 72)

    t_total = time.time()
    steps = {}

    # 1. fetch (默认跑, --skip-fetch 跳过)
    steps["fetch"] = step_fetch(skip=skip_fetch)
    if steps["fetch"]["ok"] is False and not skip_fetch:
        if verbose:
            print(f"  [WARN] fetch 失败, 后续步骤可能受影响 (用 cache)")

    # 2. attribution (关键, 失败则中断)
    steps["attribution"] = step_attribution()

    # 3. residual regression (P7-5)
    steps["residual_regression"] = step_residual_regression()

    # 4. markdown report
    if not skip_md:
        steps["markdown_report"] = step_markdown_report(date_str)
    else:
        steps["markdown_report"] = {"ok": "skip", "reason": "--skip-md", "elapsed_s": 0}

    # 5. HTML report (需要先有 MD + K-line SVG)
    if not skip_html:
        steps["html_report"] = step_html_report(date_str)
    else:
        steps["html_report"] = {"ok": "skip", "reason": "--skip-html", "elapsed_s": 0}

    # 6. performance dashboard
    if not skip_dashboard:
        steps["performance_dashboard"] = step_performance_dashboard(date_str)
    else:
        steps["performance_dashboard"] = {"ok": "skip", "reason": "--skip-dashboard", "elapsed_s": 0}

    # 7. check alerts (P8-6 写, 本脚本读)
    steps["check_alerts"] = step_check_alerts(date_str)

    # 8. causal analysis (Phase 9 Pearl-style, 不写 report 数字, 只算 + 摘要打印)
    steps["causal"] = step_causal(date_str)

    # 9. summary
    total = round(time.time() - t_total, 1)
    if verbose:
        print_summary(steps, total, date_str)
    return {"date": date_str, "elapsed_s": total, "steps": steps}


def main():
    import argparse
    parser = argparse.ArgumentParser(description="us-stock-causal daily report (P5-2 gate)")
    parser.add_argument("--date", type=str, default=None, help="报告日期 (默认今天, YYYY-MM-DD)")
    parser.add_argument("--skip-fetch", action="store_true", help="跳过 fetch, 用 cache")
    parser.add_argument("--skip-md", action="store_true", help="跳过 markdown 报告")
    parser.add_argument("--skip-html", action="store_true", help="跳过 HTML 报告")
    parser.add_argument("--skip-dashboard", action="store_true", help="跳过 performance dashboard")
    parser.add_argument("--quiet", action="store_true", help="不打印 banner 和 summary")
    args = parser.parse_args()

    result = run_daily_report(
        date_str=args.date,
        skip_fetch=args.skip_fetch,
        skip_md=args.skip_md,
        skip_html=args.skip_html,
        skip_dashboard=args.skip_dashboard,
        verbose=not args.quiet,
    )
    # exit code: 0 = 全 OK / skip, 1 = 有 fail
    n_fail = sum(1 for v in result["steps"].values() if v.get("ok") is False)
    return 1 if n_fail > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
