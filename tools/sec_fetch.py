"""
sec_fetch.py — SEC EDGAR 财报抓取 wrapper (Mavis sec-filings-fetch skill)

================================================================================
为什么有这个 skill:
- AAPL/NVDA/MP 卖方研报里, 财务数据 (Q1 FY25 营收 $60.8M) 之前是 WebSearch 转引
  (±15% 偏差), 不是真实 SEC 10-K/10-Q 数据
- SEC EDGAR 公开 API 完全免费 (efts.sec.gov + data.sec.gov + www.sec.gov)
- edgar-parser (GitHub henrysouchien, MIT) 提供 iXBRL 解析 → 标准化财务 facts
- 本 wrapper 把底层 API + 解析 + 跨公司复用封装成 6 个 high-level 函数

================================================================================
6 个核心函数 (跨公司可复用, 跟 ticker 无关):

1. get_company_cik(ticker)              — ticker → SEC CIK (10 位数字, 0000320193 = AAPL)
2. get_recent_filings(ticker, form, n)  — 拉最新 N 份 10-Q/10-K/8-K 列表
3. get_filing_financials(ticker, year, quarter) — 拉某季度的所有财务 facts (营收/净利/EPS/FCF)
4. get_filing_text(ticker, year, quarter, section) — 拉某个 section 文本 (Risk Factors / MD&A)
5. match_filings_to_quarters(ticker)    — 把 10-Q/10-K filings 跟 fiscal year + quarter 对齐
6. get_metric_history(ticker, metric, n_quarters) — 拉某 metric 历史 N 个季度数据

================================================================================
数据源分层 (跟 AAPL v4.10 数据 FAIL 修正一致):
- ✅ 0 幻觉: yfinance OHLCV + SEC 10-K/10-Q (本 skill)
- ⚠️ 需核验: WebSearch 汇总的卖方 PT / 共识 PT / 管理层指引
- 🔬 数据驱动: event_study 实证 (claude-equity-research skill)

================================================================================
跨项目复用 (跟 event_study.py / claude-equity-research 同样模式):
- 复制本文件到 {project}/tools/sec_fetch.py
- 改 3 处: 你的 ticker / 你的 fiscal year / 你的 metric 名字
- 跑 → 真实 SEC 财报数据, 不是 WebSearch 转引

================================================================================
已知局限:
- 47MB iXBRL HTML 文件下载慢 (SEC.gov 限速 ~5 req/s, 我们 <2 req/s)
- iXBRL tags 公司不统一 (us-gaap:Revenues vs us-gaap:RevenueFromContractWith...)
  → 我们用 fuzzy match (rapidfuzz) 自动对齐
- 仅 US 上市公司 (SEC 监管), 港股 / A 股需要 HKEX / SSE 单独
- 历史只到 ~2009 (iXBRL 标准化)
"""
import os
import sys
import json
import time
import logging
import requests
import pandas as pd
from datetime import datetime, date
from io import StringIO
from typing import Optional, List, Dict, Any

# === Clash proxy 探测 (跟 us-stock-causal 一致) ===
def _setup_proxy():
    """探测本地 Clash 代理端口, 跟 yfinance 同一套"""
    import socket
    for _p in [7897, 10808, 7890, 7891, 7892, 10809, 7899]:
        try:
            with socket.create_connection(("127.0.0.1", _p), timeout=0.4):
                os.environ["HTTPS_PROXY"] = f"http://127.0.0.1:{_p}"
                os.environ["HTTP_PROXY"]  = f"http://127.0.0.1:{_p}"
                return _p
        except (socket.timeout, ConnectionRefusedError, OSError):
            continue
    return None

# 必须在 import edgar_parser 前 setup proxy
_proxy_port = _setup_proxy()
if _proxy_port:
    logging.info(f"[sec_fetch] Clash proxy: 127.0.0.1:{_proxy_port}")

# Increase read timeout globally (47MB iXBRL HTML files take >45s on slow SEC.gov)
_orig_get = requests.Session.get
def _get_patched(self, *args, **kwargs):
    kwargs.setdefault('timeout', (15, 300))  # (connect, read) — 5 min read
    return _orig_get(self, *args, **kwargs)
requests.Session.get = _get_patched

logging.basicConfig(level=logging.WARNING, format='%(asctime)s [%(name)s] %(levelname)s: %(message)s')
log = logging.getLogger('sec_fetch')

# === SEC EDGAR User-Agent (官方要求, 缺这个会被 403) ===
# SEC 要求: "Sample Company Name AdminContact@samplecompany.com"
# 我们用 Mavis/MiniMax Code 通用 UA, 跟 paper-agent 风格一致
DEFAULT_UA = "Mavis Equity Research research@minimax.com"
_HEADERS = {"User-Agent": DEFAULT_UA}

# === SEC EDGAR 公共 API 端点 ===
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"

# === Cache (避免重复拉, 跨 session) ===
_CACHE_DIR = os.path.join(os.path.expanduser("~"), ".cache", "sec_fetch")
os.makedirs(_CACHE_DIR, exist_ok=True)


# ============================================================================
# 1. CIK 解析
# ============================================================================
def _load_ticker_map() -> Dict[str, str]:
    """从 SEC 拉 全部 ticker → CIK 映射 (~10K tickers, 218KB JSON)
    Cache 到本地 ~/.cache/sec_fetch/tickers.json
    """
    cache_path = os.path.join(_CACHE_DIR, "tickers.json")
    if os.path.exists(cache_path):
        age = time.time() - os.path.getmtime(cache_path)
        if age < 7 * 24 * 3600:  # 7 天
            with open(cache_path) as f:
                return json.load(f)
    log.info("拉 SEC 全部 ticker → CIK 映射 (~10K tickers, 218KB)")
    r = requests.get(COMPANY_TICKERS_URL, headers=_HEADERS, timeout=(15, 30))
    r.raise_for_status()
    raw = r.json()
    # raw 格式: {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}, ...}
    ticker_map = {v["ticker"].upper(): str(v["cik_str"]).zfill(10) for v in raw.values()}
    with open(cache_path, "w") as f:
        json.dump(ticker_map, f)
    return ticker_map


def get_company_cik(ticker: str) -> str:
    """ticker → SEC CIK (10 位数字, 0 填充)

    Args:
        ticker: e.g. "AAPL", "NVDA", "MP"

    Returns:
        10 位 CIK 字符串, e.g. "0000320193"

    Raises:
        ValueError: ticker 找不到
    """
    ticker_map = _load_ticker_map()
    cik = ticker_map.get(ticker.upper())
    if not cik:
        raise ValueError(f"ticker '{ticker}' not found in SEC database (共 {len(ticker_map)} 个 ticker)")
    return cik


# ============================================================================
# 2. Filings 列表
# ============================================================================
def get_recent_filings(ticker: str, form_type: str = "10-Q", count: int = 4) -> List[Dict[str, Any]]:
    """拉某 ticker 的最新 N 份指定 form_type filings

    Args:
        ticker: e.g. "AAPL"
        form_type: "10-Q" / "10-K" / "8-K" / "DEF 14A" / "S-1" 等
        count: 拉多少份 (默认 4)

    Returns:
        List[dict] 每份含:
          - accession: "0000320193-25-000008"
          - form: "10-Q"
          - filing_date: "2025-01-31"
          - period_of_report: "2024-12-28"
          - primary_doc: "aapl-20241228.htm"
          - url: 完整 SEC URL
    """
    cik = get_company_cik(ticker)
    r = requests.get(SUBMISSIONS_URL.format(cik=cik), headers=_HEADERS, timeout=(15, 30))
    r.raise_for_status()
    sub = r.json()

    recent = sub.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    accs  = recent.get("accessionNumber", [])
    dates = recent.get("filingDate", [])
    periods = recent.get("reportDate", [])
    primary = recent.get("primaryDocument", [])

    results = []
    for i, f in enumerate(forms):
        if f == form_type:
            acc_clean = accs[i].replace("-", "")
            results.append({
                "accession": accs[i],
                "form": f,
                "filing_date": dates[i],
                "period_of_report": periods[i],
                "primary_doc": primary[i],
                "url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_clean}/{primary[i]}",
                "cik": cik,
            })
            if len(results) >= count:
                break
    return results


# ============================================================================
# 3. 财务 facts (营收/净利/EPS/FCF 等)
# ============================================================================
# 关键 us-gaap metric 名字 (覆盖大部分卖方研报需要)
COMMON_METRICS = {
    # 营收 / 销售
    "revenue": [
        "us-gaap:Revenues",
        "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
        "us-gaap:RevenueFromContractWithCustomerIncludingAssessedTax",
        "us-gaap:SalesRevenueNet",
        "us-gaap:SalesRevenueGoodsNet",
    ],
    # 净利
    "net_income": [
        "us-gaap:NetIncomeLoss",
        "us-gaap:ProfitLoss",
    ],
    # EPS basic
    "eps_basic": [
        "us-gaap:EarningsPerShareBasic",
    ],
    # EPS diluted
    "eps_diluted": [
        "us-gaap:EarningsPerShareDiluted",
    ],
    # 经营现金流
    "operating_cash_flow": [
        "us-gaap:NetCashProvidedByUsedInOperatingActivities",
    ],
    # 自由现金流 (经营 - capex)
    "capex": [
        "us-gaap:PaymentsToAcquirePropertyPlantAndEquipment",
    ],
    # 总资产
    "total_assets": [
        "us-gaap:Assets",
    ],
    # 现金
    "cash": [
        "us-gaap:CashAndCashEquivalentsAtCarryingValue",
        "us-gaap:Cash",
    ],
    # 总负债
    "total_liabilities": [
        "us-gaap:Liabilities",
    ],
    # 股东权益
    "stockholders_equity": [
        "us-gaap:StockholdersEquity",
        "us-gaap:StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ],
    # 毛利率 (raw 营收 - 销货成本, 需自己算)
    "cost_of_revenue": [
        "us-gaap:CostOfRevenue",
        "us-gaap:CostOfGoodsAndServicesSold",
        "us-gaap:CostOfGoodsSold",
    ],
    # 研发
    "rnd": [
        "us-gaap:ResearchAndDevelopmentExpense",
    ],
    # 销售/管理
    "sga": [
        "us-gaap:SellingGeneralAndAdministrativeExpense",
        "us-gaap:SellingAndMarketingExpense",
        "us-gaap:GeneralAndAdministrativeExpense",
    ],
}


def _match_metric(facts: dict, metric_aliases: List[str]) -> Optional[Dict[str, Any]]:
    """从 companyfacts JSON 找匹配 metric, 优先用单位 USD 且最近一个 instant/duration
    facts = companyfacts['facts']['us-gaap']  (已经去掉 us-gaap: prefix)
    metric_aliases = ["us-gaap:Revenues", ...]  (带 prefix, 新 metric 优先)

    重要: 优先匹配"最近 2 年有 filing"的 metric tag (跳过完全 deprecated 的旧 tag)
    """
    # 取最新 entries 的 filed date 作为"是否新" 指标
    now = pd.Timestamp.now()
    cutoff = now - pd.DateOffset(years=2)

    best = None
    best_recent_count = 0
    best_total = 0

    for alias in metric_aliases:
        key = alias.replace("us-gaap:", "") if alias.startswith("us-gaap:") else alias
        if key not in facts:
            continue
        units = facts[key].get("units", {})
        # 优先 USD
        entries = None
        for unit_key in ["USD", "USD/shares", "shares"]:
            if unit_key in units and units[unit_key]:
                entries = units[unit_key]
                unit = unit_key
                break
        if entries is None:
            for unit_key, e_list in units.items():
                if e_list:
                    entries = e_list
                    unit = unit_key
                    break
        if not entries:
            continue

        # 数 2 年内的 entries
        recent = [e for e in entries if e.get("filed") and pd.Timestamp(e["filed"]) >= cutoff]
        # 优先: recent > 0 的 metric (避免 deprecated 的)
        # 多个 recent 时, 取 entries 数最多 (覆盖最广)
        if len(recent) > best_recent_count or (len(recent) == best_recent_count and len(entries) > best_total):
            best = {"metric": alias, "unit": unit, "entries": entries}
            best_recent_count = len(recent)
            best_total = len(entries)

    return best


def get_company_facts(ticker: str, use_cache: bool = True) -> Dict[str, Any]:
    """拉某 ticker 的所有 XBRL facts (companyfacts JSON, 包含历史所有 10-K/10-Q 数字)

    Args:
        ticker: e.g. "AAPL"
        use_cache: 是否用本地 cache (避免重复 5MB 下载)

    Returns:
        companyfacts JSON 字典
    """
    cik = get_company_cik(ticker)
    cache_path = os.path.join(_CACHE_DIR, f"facts_{cik}.json")
    if use_cache and os.path.exists(cache_path):
        age = time.time() - os.path.getmtime(cache_path)
        if age < 24 * 3600:  # 24h
            with open(cache_path) as f:
                return json.load(f)
    log.info(f"拉 {ticker} companyfacts (CIK={cik}, 5-10MB)")
    r = requests.get(COMPANY_FACTS_URL.format(cik=cik), headers=_HEADERS, timeout=(15, 120))
    r.raise_for_status()
    data = r.json()
    with open(cache_path, "w") as f:
        json.dump(data, f)
    return data


def get_metric_history(
    ticker: str,
    metric: str,
    n_quarters: int = 8,
    fiscal_year: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """拉某 metric 历史 N 个季度数据

    Args:
        ticker: e.g. "AAPL"
        metric: "revenue" / "net_income" / "eps_diluted" / "operating_cash_flow" 等
        n_quarters: 拉多少季度
        fiscal_year: 截至某财年 (默认当前 FY)

    Returns:
        List[dict] 每条含: period_end, value, unit, accession, form, fy, fp
    """
    if metric not in COMMON_METRICS:
        raise ValueError(f"metric '{metric}' 不在 COMMON_METRICS ({list(COMMON_METRICS.keys())})")

    facts = get_company_facts(ticker)
    us_gaap = facts.get("facts", {}).get("us-gaap", {})
    matched = _match_metric(us_gaap, COMMON_METRICS[metric])
    if not matched:
        return []

    # entries: list of {end, val, accn, form, fy, fp, ...}
    entries = matched["entries"]

    # 过滤: 季度数据 (10-Q / 10-K) + duration (start-end)
    quarters = []
    for e in entries:
        if e.get("form") not in ("10-Q", "10-K"):
            continue
        if "start" in e and "end" in e:
            # duration (季度/年度)
            quarters.append({
                "period_start": e["start"],
                "period_end": e["end"],
                "value": e["val"],
                "unit": matched["unit"],
                "accession": e.get("accn"),
                "form": e.get("form"),
                "fy": e.get("fy"),
                "fp": e.get("fp"),  # FY / Q1 / Q2 / Q3 / Q4
            })
        elif "end" in e and "start" not in e:
            # instant (e.g. total_assets, cash) — 跳过季度
            continue

    # 排序 + 截取
    quarters.sort(key=lambda x: x["period_end"], reverse=True)
    if fiscal_year:
        quarters = [q for q in quarters if q.get("fy") == fiscal_year]
    return quarters[:n_quarters]


# ============================================================================
# 4. Filings 文本 (Risk Factors / MD&A / Business)
# ============================================================================
def get_filing_text(
    ticker: str,
    year: int,
    quarter: int,
    section: str = "item_1a",
) -> str:
    """拉某 10-K/10-Q 某个 section 文本

    Args:
        ticker: e.g. "AAPL"
        year: fiscal year
        quarter: 1/2/3/4 (10-Q) 或 0 (10-K 全年)
        section: "item_1a" (Risk Factors) / "item_1" (Business) / "item_7" (MD&A) 等

    Returns:
        section 纯文本
    """
    # 走 edgar-parser
    try:
        from edgar_parser import parse_filing
        from edgar_parser.section_parser import extract_section
    except ImportError:
        raise ImportError("pip install edgar-parser  (本 skill 依赖)")

    parsed = parse_filing(ticker, year, quarter, full_year_mode=(quarter == 0))
    # 找 filing HTML
    filing = parsed.get("filing", {})
    if not filing:
        # 拉 raw HTML
        filings = get_recent_filings(ticker, "10-Q" if quarter else "10-K", count=10)
        # match year/quarter
        target_period = f"{year}-{['03','06','09','12'][quarter-1]}" if quarter else f"{year}-12"
        for f in filings:
            if target_period in f.get("period_of_report", ""):
                filing = f
                break
    if not filing or "url" not in filing:
        raise ValueError(f"{ticker} {year}Q{quarter} 找不到 filing")

    html = requests.get(filing["url"], headers=_HEADERS, timeout=(15, 120)).text
    # 简易 section 提取 (按 Item 标题切)
    import re
    pattern = rf'(<[^>]*>)*\s*Item\s+{section.replace("item_", "")}\.?\s*[\.\:](.*?)(?=(<[^>]*>)*\s*Item\s+\d)'
    match = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
    if not match:
        return f"[section {section} not found in {ticker} {year}Q{quarter}]"
    # strip HTML tags
    import re as _re
    text = _re.sub(r'<[^>]+>', ' ', match.group(2))
    text = _re.sub(r'\s+', ' ', text).strip()
    return text[:20000]  # 限 20K chars


# ============================================================================
# 5. Filings 跟 fiscal year/quarter 对齐
# ============================================================================
def match_filings_to_quarters(ticker: str, n_years: int = 3) -> pd.DataFrame:
    """把 10-Q/10-K filings 跟 fiscal year + quarter 对齐

    Args:
        ticker: e.g. "AAPL"
        n_years: 拉多少年

    Returns:
        DataFrame columns: form, accession, filing_date, period_end, fy, fp
    """
    # 拉所有 10-Q + 10-K
    q_filings = get_recent_filings(ticker, "10-Q", count=n_years * 4)
    k_filings = get_recent_filings(ticker, "10-K", count=n_years)

    all_filings = q_filings + k_filings
    df = pd.DataFrame(all_filings)

    if df.empty:
        return df

    # SEC submissions API 字段是 period_of_report (实际 end date)
    # 标准化成 period_end (跟 event_study.py / claude-equity-research 风格一致)
    df = df.rename(columns={"period_of_report": "period_end"})

    df["filing_date"] = pd.to_datetime(df["filing_date"])
    df["period_end"] = pd.to_datetime(df["period_end"])

    # FY / FP 推断 (从 period_end 月份)
    # 10-K 通常 fiscal year end 9-12 月; 10-Q 3/6/9/12 月
    def infer_fy_fp(row):
        m = row["period_end"].month
        y = row["period_end"].year
        if row["form"] == "10-K":
            return pd.Series({"fy": y, "fp": "FY"})
        # 10-Q: 季度
        if m in (1, 2, 3):
            return pd.Series({"fy": y, "fp": "Q1"})
        if m in (4, 5, 6):
            return pd.Series({"fy": y, "fp": "Q2"})
        if m in (7, 8, 9):
            return pd.Series({"fy": y, "fp": "Q3"})
        if m in (10, 11, 12):
            return pd.Series({"fy": y, "fp": "Q4"})
        return pd.Series({"fy": y, "fp": "?"})

    df[["fy", "fp"]] = df.apply(infer_fy_fp, axis=1)
    df = df.sort_values("period_end", ascending=False).reset_index(drop=True)
    return df


# ============================================================================
# 6. 财报摘要 (markdown 格式, 给研报直接用)
# ============================================================================
def get_quarterly_financials_markdown(
    ticker: str,
    n_quarters: int = 8,
) -> str:
    """拉某 ticker 最近 N 季度核心财务数据, 输出 markdown 表格

    Args:
        ticker: e.g. "AAPL"
        n_quarters: 拉多少季度 (默认 8 = 2 年)

    Returns:
        markdown 字符串, 包含 4 张表格: 营收 / 净利 / EPS / 现金流
    """
    lines = [f"# {ticker.upper()} — 最近 {n_quarters} 季度财务摘要 (SEC 10-K/10-Q)\n"]
    lines.append(f"**数据源**: SEC EDGAR XBRL companyfacts JSON (免费公开 API)")
    lines.append(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')} GMT+8")
    lines.append(f"**所有数字单位**: 百万美元 (除 EPS 外)  \n")

    # 4 个核心 metric
    for metric_key, metric_label in [
        ("revenue", "营收 (Revenue, $M)"),
        ("net_income", "净利 (Net Income, $M)"),
        ("eps_diluted", "摊薄 EPS (EPS Diluted, $)"),
        ("operating_cash_flow", "经营现金流 (OCF, $M)"),
    ]:
        lines.append(f"## {metric_label}\n")
        lines.append("| Fiscal Year | Period | Period End | Value |")
        lines.append("|---|---|---|---|")
        rows = get_metric_history(ticker, metric_key, n_quarters=n_quarters)
        if not rows:
            lines.append(f"| - | - | - | 数据缺失 |\n")
            continue
        for r in rows:
            val = r["value"]
            if metric_key in ("revenue", "net_income", "operating_cash_flow"):
                # raw unit 是 USD, 转百万
                val = f"${val / 1_000_000:.1f}M" if val else "N/A"
            elif metric_key == "eps_diluted":
                val = f"${val:.2f}" if val else "N/A"
            lines.append(f"| {r.get('fy', '?')}{r.get('fp', '?')} | {r['period_start']} → {r['period_end']} | {r['period_end']} | {val} |")
        lines.append("")

    return "\n".join(lines)


# ============================================================================
# Main / CLI 测试
# ============================================================================
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python sec_fetch.py <TICKER> [N_QUARTERS]")
        print("  e.g. python sec_fetch.py AAPL 8")
        sys.exit(1)

    ticker = sys.argv[1]
    n_q = int(sys.argv[2]) if len(sys.argv) > 2 else 8

    print(f"=== {ticker.upper()} SEC EDGAR 拉取测试 ===\n")

    print(f"[1] CIK: {get_company_cik(ticker)}")

    print(f"\n[2] 最近 4 份 10-Q:")
    for f in get_recent_filings(ticker, "10-Q", 4):
        print(f"  - {f['form']:6s} {f['accession']:24s} period_end={f['period_of_report']}")

    print(f"\n[3] Filings 跟 FY/FP 对齐:")
    df = match_filings_to_quarters(ticker, n_years=2)
    print(df[['form', 'fy', 'fp', 'period_end', 'accession']].to_string(index=False))

    print(f"\n[4] 最近 {n_q} 季度 营收:")
    rev = get_metric_history(ticker, "revenue", n_quarters=n_q)
    for r in rev:
        print(f"  {r.get('fy')}{r.get('fp'):3s} {r['period_end']:12s}  ${r['value']/1_000_000:>10.1f}M")

    print(f"\n[5] Markdown 摘要:")
    md = get_quarterly_financials_markdown(ticker, n_quarters=n_q)
    print(md[:2000])
