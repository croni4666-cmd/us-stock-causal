"""
src/etf_holdings.py - SEC EDGAR ETF 持仓公告拉取 (v0.6.8d Stage 2 of P-event-enrichment)

SEC EDGAR API:
  - 拉 ETF 的 N-CSR (annual report, 含完整 holdings)
  - 跟 P7-2 真修残差合并: 真 holdings → 真 sector weights
  - 替代 hardcode config/sector_weights.json (2026-Q2 近似值)

**ETF universe**: 我们 15 只 ETF (4 指数 + 11 行业)
  - State Street SPDR: DIA, XLK/XLF/XLE/XLY/XLP/XLV/XLI/XLU/XLB/XLRE/XLC
  - Invesco: QQQ, RSP
  - ProShares: QQQE

**Why SEC EDGAR (跟 v0.6.8b 教训)**:
  - 之前推荐 FMP etf.sectors/holdings 全 402 Restricted (免费 tier 不含)
  - SEC EDGAR 是政府公开数据, 免 key (但要 UA header)
  - 跟 P-event-2 (新 ROADMAP item) 一起做

**API endpoint**:
  - Tickers JSON: https://www.sec.gov/files/company_tickers.json (10K+ 实体)
  - Submissions: https://data.sec.gov/submissions/CIK<10-digit>.json
  - N-CSR 文档 URL: https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession_no_dashes}/{primary_doc}

**Caveats**:
  - SEC 10 req/sec 限流, 用 0.5s 间隔保险
  - UA header 强制: "Your Name <email>" (fair access policy)
  - N-CSR 是 HTML, 解析 "Schedule of Investments" 表 (Stage 2.2 写)
  - 失败优雅降级: 返回 {}, 不抛错

**Stage 2.1 scope (v0.6.8d)**: raw 拉取, 拿到 CIK + 最新 N-CSR URL, 不解析 holdings
**Stage 2.2 scope (v0.6.8e)**: 解析 N-CSR HTML + 调 equity.profile 算 sector weights + 集成 attribution
"""
from __future__ import annotations

import json
import os
import time
from datetime import date
from pathlib import Path
from typing import Optional

from loguru import logger
import requests

# UA header (SEC fair access policy 强制)
DEFAULT_UA = "us-stock-causal research@example.com"

# SEC endpoints
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession_no_dashes}/{primary_doc}"

# 缓存目录 (1d cache)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = PROJECT_ROOT / "data" / "cache" / "etf_holdings"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

TIMEOUT = 30
# SEC 限流: 文档说 10 req/sec, 实测更严, 0.5s 间隔保险
RATE_LIMIT_SECONDS = 0.5

# 我们关心的 ETF form 类型:
#   - NPORT-P: 1940 Act 月度持仓报告 (XML 格式, 含完整 Schedule of Investments)
#   - N-30D: 1940 Act 半年/年度报
#   - N-CSR / N-CSR/A: 1933 Act 年度报 (老 ETF 习惯, 现在少见)
#   - N-Q / N-Q/A: 1933 Act 季度报
#   - N-1A: 初始注册
# v0.6.8d hotfix: ETF 主发 NPORT-P (2020 SEC 新规后), 不是 N-CSR
WANTED_FORMS = ("NPORT-P", "N-30D", "N-CSR", "N-CSR/A", "N-Q", "N-Q/A", "N-1A", "N-1A/A")


def _get_proxies() -> Optional[dict]:
    """从环境变量取 proxy (clash 7897/7899)"""
    http = os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")
    https = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    if not http and not https:
        return None
    return {"http": http, "https": https}


def _rate_limit():
    """0.5s sleep 强制 rate limit (SEC fair access)"""
    time.sleep(RATE_LIMIT_SECONDS)


def _cik_zero_pad(cik: str | int) -> str:
    """CIK 10 位补 0 (data.sec.gov 路径用 10-digit)"""
    return str(cik).zfill(10)


def fetch_ticker_to_cik(force_refresh: bool = False) -> dict[str, str]:
    """
    拉 SEC EDGAR tickers.json, 返回 {ticker: CIK_str_10digit} 映射

    缓存 1d 到 data/cache/etf_holdings/tickers_<date>.json
    """
    cache_file = CACHE_DIR / f"tickers_{date.today().isoformat()}.json"
    if cache_file.exists() and not force_refresh:
        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            logger.info(f"[etf-holdings] tickers cache hit ({len(data)} tickers)")
            return data
        except Exception as e:
            logger.warning(f"[etf-holdings] tickers cache 读失败: {e}")

    headers = {"User-Agent": DEFAULT_UA, "Accept-Encoding": "gzip, deflate"}
    try:
        resp = requests.get(TICKERS_URL, timeout=TIMEOUT, headers=headers, proxies=_get_proxies())
        resp.raise_for_status()
    except Exception as e:
        logger.warning(f"[etf-holdings] tickers 拉取失败: {e}")
        return {}

    try:
        data = resp.json()
    except Exception as e:
        logger.warning(f"[etf-holdings] tickers JSON 解析失败: {e}")
        return {}

    # data 是 {0: {cik_str, ticker, title}, 1: {...}, ...}
    result = {}
    for entry in data.values():
        ticker = entry.get("ticker", "").upper()
        cik = entry.get("cik_str", "")
        if ticker and cik:
            result[ticker] = _cik_zero_pad(cik)

    try:
        cache_file.write_text(json.dumps(result, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning(f"[etf-holdings] tickers 写 cache 失败: {e}")
    logger.info(f"[etf-holdings] tickers 拉取 {len(result)} 个 (cik 10-digit)")
    _rate_limit()
    return result


def fetch_etf_submissions(cik: str, force_refresh: bool = False) -> dict:
    """
    拉 ETF 的 submissions.json, 找最新 N-CSR / N-Q / N-1A filings

    Returns:
        dict with: cik, name, ticker, recent_filings (list of dicts)
    """
    cache_file = CACHE_DIR / f"submissions_CIK{cik}_{date.today().isoformat()}.json"
    if cache_file.exists() and not force_refresh:
        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            logger.info(f"[etf-holdings] submissions cache hit CIK {cik}")
            return data
        except Exception as e:
            logger.warning(f"[etf-holdings] submissions cache 读失败: {e}")

    url = SUBMISSIONS_URL.format(cik=cik)
    headers = {"User-Agent": DEFAULT_UA, "Accept-Encoding": "gzip, deflate"}
    try:
        resp = requests.get(url, timeout=TIMEOUT, headers=headers, proxies=_get_proxies())
        resp.raise_for_status()
    except Exception as e:
        logger.warning(f"[etf-holdings] submissions CIK {cik} 失败: {e}")
        return {"cik": cik, "name": "", "recent_filings": []}

    try:
        data = resp.json()
    except Exception as e:
        logger.warning(f"[etf-holdings] submissions CIK {cik} JSON 失败: {e}")
        return {"cik": cik, "name": "", "recent_filings": []}

    # submissions.json 格式: filings.recent.{form[], filingDate[], accessionNumber[], primaryDocument[]}
    recent = data.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    filing_dates = recent.get("filingDate", [])
    accession_numbers = recent.get("accessionNumber", [])
    primary_documents = recent.get("primaryDocument", [])
    report_dates = recent.get("reportDate", [])

    recent_filings = []
    # submissions.recent 已经是时间倒序 (verified 2026-07-20 SPY 看 274 filings)
    # 不需要重新排序, 直接按顺序找 WANTED_FORMS
    for i, form in enumerate(forms):
        if form in WANTED_FORMS:
            recent_filings.append({
                "form": form,
                "filing_date": filing_dates[i] if i < len(filing_dates) else "",
                "report_date": report_dates[i] if i < len(report_dates) else "",
                "accession_number": accession_numbers[i] if i < len(accession_numbers) else "",
                "primary_document": primary_documents[i] if i < len(primary_documents) else "",
            })
            if len(recent_filings) >= 5:
                break

    result = {
        "cik": cik,
        "name": data.get("name", ""),
        "ticker": data.get("tickers", [""])[0] if data.get("tickers") else "",
        "recent_filings": recent_filings[:5],
    }

    try:
        cache_file.write_text(json.dumps(result, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning(f"[etf-holdings] submissions 写 cache 失败: {e}")
    logger.info(f"[etf-holdings] submissions CIK {cik}: {len(recent_filings)} 个 NPORT-P/N-CSR 找")
    _rate_limit()
    return result


def get_etf_filing_url(cik: str, accession_number: str, primary_document: str) -> str:
    """
    拼 N-CSR 文档 URL (HTML, 含 Schedule of Investments)

    SEC Archives 路径: /Archives/edgar/data/{cik_int}/{accession_no_dashes}/{primary_doc}
    """
    cik_int = str(int(cik))  # 去前导 0
    accession_no_dashes = accession_number.replace("-", "")
    return ARCHIVES_URL.format(
        cik_int=cik_int,
        accession_no_dashes=accession_no_dashes,
        primary_doc=primary_document,
    )


def fetch_etf_latest_filing(ticker: str, force_refresh: bool = False) -> dict:
    """
    给定 ETF ticker, 找最新 N-CSR / N-Q URL + 文档元数据

    Returns:
        dict with: ticker, cik, cik_name, latest_filing_date, latest_form,
                   primary_document, accession_number, filing_url
        或 error: "cik_not_found" / "no_n_csr_filing"
    """
    ticker_to_cik = fetch_ticker_to_cik()
    cik = ticker_to_cik.get(ticker.upper())
    if not cik:
        logger.warning(f"[etf-holdings] {ticker} CIK 未找到 (不在 SEC tickers.json)")
        return {"ticker": ticker, "cik": None, "error": "cik_not_found"}

    submissions = fetch_etf_submissions(cik, force_refresh=force_refresh)
    if not submissions.get("recent_filings"):
        return {"ticker": ticker, "cik": cik, "error": "no_n_csr_filing"}

    latest = submissions["recent_filings"][0]  # 最新 (已排序)
    return {
        "ticker": ticker,
        "cik": cik,
        "cik_name": submissions.get("name", ""),
        "latest_form": latest["form"],
        "latest_filing_date": latest["filing_date"],
        "latest_report_date": latest.get("report_date", ""),
        "primary_document": latest["primary_document"],
        "accession_number": latest["accession_number"],
        "filing_url": get_etf_filing_url(cik, latest["accession_number"], latest["primary_document"]),
    }


if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

    import argparse
    parser = argparse.ArgumentParser(description="SEC EDGAR ETF 持仓公告 (v0.6.8d Stage 2)")
    parser.add_argument("--smoke", action="store_true", help="连通性自检 (1 ETF)")
    parser.add_argument("--ticker", type=str, default="SPY", help="指定 ETF ticker (默认 SPY)")
    args = parser.parse_args()

    if args.smoke:
        print(f"[--smoke] 拉 {args.ticker} 持仓元数据 (force_refresh=True):")
        r = fetch_etf_latest_filing(args.ticker, force_refresh=True)
        if r.get("error"):
            print(f"  FAIL: {r['error']}")
        else:
            print(f"  OK: CIK={r['cik']}, name={r['cik_name'][:50]}")
            print(f"  latest filing: {r['latest_form']} {r['latest_filing_date']} (report {r['latest_report_date']})")
            print(f"  primary doc: {r['primary_document']}")
            print(f"  url: {r['filing_url']}")
    else:
        # 批量遍历 15 只 ETF
        from src.tickers_universe import ETF_TICKERS  # 跟 P7-2 真修共享
        print(f"遍历 {len(ETF_TICKERS)} 只 ETF 持仓元数据:")
        for t in ETF_TICKERS:
            r = fetch_etf_latest_filing(t)
            if r.get("error"):
                print(f"  {t}: FAIL {r['error']}")
            else:
                print(f"  {t}: {r['latest_form']} {r['latest_filing_date']} (CIK {r['cik']})")
