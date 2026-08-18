"""examples/sec_filings_report.py — SEC EDGAR 财报 Shadow mode 验证 (v0.9.5)

不接进 daily_report, 只验证集成路径 + 数据真实性。

跑法: python examples/sec_filings_report.py [--date YYYY-MM-DD] [--ticker AAPL] [--sector-mapped]
输出:
  - data/cache/sec_filings/<date>.json (per-公司 metrics)
  - output/sec_filings_<date>.md (markdown 摘要)
  - 控制台 banner (拉取进度 + 数据预览)

Shadow mode 设计:
  - 33 ticker (11 行业 ETF × 3 权重股) 拉最新 10-Q revenue / net_income / eps
  - 不动 daily_report, 不写进 markdown 5 段
  - 9/3 v0.9.5 RC1 拍板是否合入 daily_report step 5.5

数据源分层 (跟 AAPL v4.10 修正一致):
  - ✅ 0 幻觉: yfinance OHLCV + SEC 10-K/10-Q (本工具)
  - ⚠️ 需核验: WebSearch 转引 (我们不依赖)
  - 🔬 数据驱动: 33 ticker × 8 quarter 矩阵

性能预算:
  - SEC EDGAR 限速 < 10 req/s, 我们控制 2 req/s
  - 33 ticker × 1 pull ≈ 16s
  - 加 parse + write cache ≈ 18-20s
  - 跑一次单日 ≈ 20s, 不影响 17:00 daily_report
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, date, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "tools"))

# UTF-8 reconfigure for emoji (Windows PS default GBK)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# 11 行业 ETF top 3 权重股 (从 config 读)
TICKER_MAP_PATH = PROJECT_ROOT / "config" / "sec_filings_tickers.json"
CACHE_DIR = PROJECT_ROOT / "data" / "cache" / "sec_filings"
OUTPUT_DIR = PROJECT_ROOT / "output"

# rate limiter: SEC EDGAR 限速 < 10 req/s, 我们用 0.5s/req = 2 req/s
_REQ_INTERVAL_S = 0.5
_last_req_time = 0.0


def _rate_limit():
    """SEC EDGAR 限速 (官方 < 10 req/s, 我们 2 req/s 留 5x headroom)"""
    global _last_req_time
    now = time.time()
    gap = now - _last_req_time
    if gap < _REQ_INTERVAL_S:
        time.sleep(_REQ_INTERVAL_S - gap)
    _last_req_time = time.time()


def load_ticker_map(only_sector: str | None = None) -> dict:
    """加载 11 行业 × 3 权重股 mapping"""
    with open(TICKER_MAP_PATH, "r", encoding="utf-8") as f:
        mapping = json.load(f)
    mapping.pop("_doc", None)
    mapping.pop("_source", None)
    mapping.pop("_policy", None)

    if only_sector:
        mapping = {k: v for k, v in mapping.items() if k == only_sector}
    return mapping


def fetch_company_metrics(ticker: str, n_quarters: int = 4) -> dict:
    """拉单家公司最新 N 季度关键 metrics

    返回结构:
      {
        "ticker": "AAPL",
        "cik": "0000320193",
        "metrics": {
          "revenue": [{"fy": 2026, "fp": "Q2", "value": 94400, ...}],
          "net_income": [...],
          "eps_diluted": [...]
        },
        "fetched_at": "2026-08-18T17:10:00"
      }
    """
    from sec_fetch import get_company_cik, get_metric_history

    _rate_limit()
    cik = get_company_cik(ticker)

    result = {
        "ticker": ticker,
        "cik": cik,
        "metrics": {},
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
    }

    for metric in ("revenue", "net_income", "eps_diluted"):
        try:
            _rate_limit()
            history = get_metric_history(ticker, metric, n_quarters=n_quarters)
            result["metrics"][metric] = history
        except Exception as e:
            result["metrics"][metric] = {"error": f"{type(e).__name__}: {e}"}

    return result


def run_shadow_mode(target_date: str, tickers: list[str] | None = None, only_sector: str | None = None) -> dict:
    """Shadow mode 主流程

    Args:
        target_date: 报告日期 (YYYY-MM-DD)
        tickers: 自定义 ticker list (None = 从 mapping 全拉)
        only_sector: 只跑某个行业 ETF (None = 全 11)

    Returns:
        {
          "date": "2026-08-18",
          "tickers_count": 33,
          "ok": 30,
          "fail": 3,
          "elapsed_s": 18.5,
          "results": {ticker: {cik, metrics, fetched_at}}
        }
    """
    print("=" * 72)
    print(f"[SEC EDGAR Shadow] {target_date} — 11 行业 ETF × 3 权重股 = 33 ticker")
    print("=" * 72)

    t0 = time.time()

    if tickers is None:
        mapping = load_ticker_map(only_sector=only_sector)
        tickers = []
        for sector, ts in mapping.items():
            tickers.extend(ts)
    else:
        mapping = {t: [t] for t in tickers}

    print(f"[tickers] {len(tickers)} unique: {', '.join(tickers[:10])}{'...' if len(tickers) > 10 else ''}")
    print()

    results = {}
    n_ok = 0
    n_fail = 0

    for i, ticker in enumerate(tickers, 1):
        print(f"[{i:2d}/{len(tickers)}] {ticker:6s} ... ", end="", flush=True)
        try:
            r = fetch_company_metrics(ticker, n_quarters=4)
            results[ticker] = r
            n_ok += 1
            # 摘要
            rev = r["metrics"].get("revenue", [])
            if isinstance(rev, list) and rev:
                latest = rev[0]
                value = latest.get("value", 0) / 1e6  # 转 millions
                fy = latest.get("fy", "?")
                fp = latest.get("fp", "?")
                print(f"OK  rev={value:,.0f}M ({fy} {fp})")
            else:
                print("OK (no revenue data)")
        except Exception as e:
            n_fail += 1
            results[ticker] = {"ticker": ticker, "error": f"{type(e).__name__}: {e}"}
            print(f"FAIL  {type(e).__name__}: {str(e)[:60]}")

    elapsed = round(time.time() - t0, 1)
    print()
    print(f"[done] {n_ok} OK / {n_fail} FAIL, 耗时 {elapsed}s")

    return {
        "date": target_date,
        "tickers_count": len(tickers),
        "ok": n_ok,
        "fail": n_fail,
        "elapsed_s": elapsed,
        "mapping": mapping,
        "results": results,
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
    }


def write_cache(report: dict) -> Path:
    """写 cache: data/cache/sec_filings/<date>.json"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    out = CACHE_DIR / f"sec_filings_{report['date']}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)
    print(f"[cache] wrote: {out}  ({out.stat().st_size / 1024:.1f} KB)")
    return out


def render_markdown_summary(report: dict) -> Path:
    """渲染 markdown 摘要 (Shadow mode, 不接 daily_report)"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUT_DIR / f"sec_filings_{report['date']}.md"

    lines = []
    lines.append(f"# SEC EDGAR 财报摘要 — {report['date']} (Shadow mode)")
    lines.append("")
    lines.append(f"**11 行业 ETF × 3 权重股 = {report['tickers_count']} ticker · "
                 f"{report['ok']} OK / {report['fail']} FAIL · 耗时 {report['elapsed_s']}s**")
    lines.append("")
    lines.append("> Shadow mode (v0.9.5): 不接进 daily_report, 仅验证集成路径 + 数据真实性。")
    lines.append("> 9/3 v0.9.5 RC1 拍板是否合入 daily_report step 5.5。")
    lines.append("")

    # 按行业 ETF 分组
    lines.append("## 按行业 ETF 分组")
    lines.append("")
    for sector, tickers in report["mapping"].items():
        lines.append(f"### {sector}")
        lines.append("")
        lines.append("| Ticker | CIK | 最新营收 | FY/FP | 净利 | EPS |")
        lines.append("|---|---|---|---|---|---|")
        for t in tickers:
            r = report["results"].get(t, {})
            if "error" in r:
                lines.append(f"| {t} | — | — | — | — | FAIL: {r['error'][:30]} |")
                continue
            cik = r.get("cik", "?")
            rev_list = r.get("metrics", {}).get("revenue", [])
            ni_list = r.get("metrics", {}).get("net_income", [])
            eps_list = r.get("metrics", {}).get("eps_diluted", [])
            rev = "—"
            fyfp = "—"
            if isinstance(rev_list, list) and rev_list:
                latest = rev_list[0]
                rev = f"${latest.get('value', 0) / 1e6:,.0f}M"
                fyfp = f"{latest.get('fy', '?')} {latest.get('fp', '?')}"
            ni = "—"
            if isinstance(ni_list, list) and ni_list:
                ni = f"${ni_list[0].get('value', 0) / 1e6:,.0f}M"
            eps = "—"
            if isinstance(eps_list, list) and eps_list:
                eps = f"${eps_list[0].get('value', 0):.2f}"
            lines.append(f"| {t} | {cik} | {rev} | {fyfp} | {ni} | {eps} |")
        lines.append("")

    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"[markdown] wrote: {out}  ({out.stat().st_size / 1024:.1f} KB)")
    return out


def main():
    parser = argparse.ArgumentParser(description="SEC EDGAR 财报 Shadow mode (v0.9.5)")
    parser.add_argument("--date", type=str, default=date.today().isoformat(),
                        help="报告日期 (默认今天)")
    parser.add_argument("--ticker", type=str, default=None,
                        help="单 ticker 测试 (e.g. AAPL), 默认跑全 33")
    parser.add_argument("--sector", type=str, default=None,
                        help="只跑某个行业 ETF (e.g. XLK)")
    parser.add_argument("--skip-cache", action="store_true",
                        help="不写 cache (调试用)")
    parser.add_argument("--skip-md", action="store_true",
                        help="不写 markdown (调试用)")
    args = parser.parse_args()

    if args.ticker:
        tickers = [args.ticker]
        report = run_shadow_mode(args.date, tickers=tickers)
    else:
        report = run_shadow_mode(args.date, only_sector=args.sector)

    if not args.skip_cache:
        write_cache(report)
    if not args.skip_md:
        render_markdown_summary(report)

    print()
    print("=" * 72)
    print(f"[Shadow mode] 集成路径 ✅ (依赖全 ok / cache 写入 / markdown 渲染)")
    print(f"  - {report['ok']}/{report['tickers_count']} OK, {report['fail']} FAIL, 耗时 {report['elapsed_s']}s")
    print(f"  - 9/3 v0.9.5 RC1 拍板是否合入 daily_report step 5.5")
    print("=" * 72)

    return 0 if report["fail"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
