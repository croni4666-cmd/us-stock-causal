"""
src/etf_holdings_parser.py - N-30D HTML 解析 (v0.6.8e Stage 2.2.1)

拉 N-30D 1.16MB HTML, 找 Schedule of Investments table, 拿 holdings list
(ticker / security name / shares / market value / % of net assets)

**v0.6.8e Stage 2.2.1 scope (fail-fast 验证)**:
- 拉 N-30D HTML + cache 1d
- 找 Schedule of Investments table
- 解析 holdings row (name + market value + pct)
- 验证: 解析出 ~500 holdings (SPY 应该有 500+)
- **不调** FMP equity.profile (留给 2.2.2)
- **不集成** attribution (留给 2.2.3)

**v0.6.8b/c 教训应用**:
- 写代码前先看实际 holdings row schema (1 个 ETF 真测)
- 不假设 N-CSR 老 schema, 走 N-30D 新 schema

**Caveats**:
- N-30D HTML schema 跟 issuer 变 (SPY / QQQ / XLK 各自不同)
- 行数 ~500 (SPY) 到 ~80 (XLK 等 sector ETF)
- 头部 N 行 = section header (Common Stocks / Warrants / Money Market)
- 尾部 N 行 = "Total" + footnotes
"""
from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

from loguru import logger
import requests
import lxml.html
import lxml.etree

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = PROJECT_ROOT / "data" / "cache" / "etf_holdings_html"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

TIMEOUT = 60  # 1.16MB HTML 拉可能慢
UA = "us-stock-causal research@example.com"


def fetch_n30d_html(url: str, use_cache: bool = True) -> Optional[str]:
    """拉 N-30D HTML, 缓存 1d 到 data/cache/etf_holdings_html/"""
    # cache key 用 URL 末尾文件名 (含 accession + primary doc)
    cache_key = url.split("/")[-1]
    cache_file = CACHE_DIR / f"{cache_key}.html"
    if use_cache and cache_file.exists():
        logger.info(f"[n30d-parser] HTML cache hit {cache_key} ({cache_file.stat().st_size // 1024}KB)")
        return cache_file.read_text(encoding="utf-8", errors="ignore")

    try:
        resp = requests.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT)
        resp.raise_for_status()
    except Exception as e:
        logger.warning(f"[n30d-parser] HTML 拉取失败: {e}")
        return None

    html = resp.text
    try:
        cache_file.write_text(html, encoding="utf-8", errors="ignore")
    except Exception as e:
        logger.warning(f"[n30d-parser] 写 cache 失败: {e}")
    logger.info(f"[n30d-parser] HTML 拉取 {cache_key} ({len(html) // 1024}KB)")
    return html


def find_industry_sector_table(html: str) -> tuple[Optional[lxml.html.HtmlElement], list]:
    """
    找 INDUSTRY (GICS sector) 行业表 (N-30D 简化路径)

    v0.6.8e hotfix: SPY N-30D table 22 含 "INDUSTRY / % OF NET ASSETS" 11 行,
    这是 GICS 11 sector × %, 不需要解析 500+ holdings + 调 FMP equity.profile

    关键: 这表行数少 (11 row) + 直接给 sector weight 真值, 完美符合 P7-2 真修需求

    Returns:
        (table_element_or_None, all_tables_count)
    """
    try:
        doc = lxml.html.fromstring(html)
    except Exception as e:
        logger.warning(f"[n30d-parser] HTML 解析失败: {e}")
        return None, []

    tables = doc.xpath("//table")
    if not tables:
        return None, []

    logger.info(f"[n30d-parser] 找到 {len(tables)} 个 table")

    # 1. 找含 "INDUSTRY" + "%" / "NET ASSETS" 文本的 table (2 列: sector + %)
    for i, t in enumerate(tables):
        text = t.text_content() if hasattr(t, 'text_content') else ""
        upper = text[:500].upper()
        if "INDUSTRY" in upper and ("%" in text or "NET ASSETS" in upper):
            rows = t.xpath(".//tr")
            logger.info(f"[n30d-parser] table {i} 含 INDUSTRY sector table, {len(rows)} 行")
            return t, tables

    # 2. fallback: 找 Schedule of Investments (老 schema)
    for i, t in enumerate(tables):
        text = t.text_content() if hasattr(t, 'text_content') else ""
        upper = text[:5000].upper()
        if "SCHEDULE OF INVESTMENTS" in upper or "PORTFOLIO OF INVESTMENTS" in upper:
            rows = t.xpath(".//tr")
            logger.info(f"[n30d-parser] table {i} 含 Schedule of Investments (老 schema), {len(rows)} 行")
            return t, tables

    return None, tables


def parse_industry_sector_table(table) -> list[dict]:
    """
    解析 INDUSTRY sector table → [{sector, pct}, ...] 11 rows

    N-30D table 22 (SPY 实测) row 格式:
      [0] "Semiconductors & Semiconductor Equipment"
      [1] "14.5%"  或  "14.5"  或  "0.145"
    """
    if table is None:
        return []

    rows = table.xpath(".//tr")
    sectors = []
    for tr in rows:
        cells = [c.text_content().strip() for c in tr.xpath(".//td | .//th")]
        if len(cells) < 2:
            continue
        # row 格式: [sector name, pct]
        sector = cells[0].strip()
        pct_str = cells[-1].replace(',', '').replace('$', '').replace('%', '').strip()
        if not sector or not pct_str:
            continue
        # 排除 header row (sector = "INDUSTRY" 或类似)
        if sector.upper() in ("INDUSTRY", "SECTOR", "GICS SECTOR", "INDUSTRY SECTOR"):
            continue
        try:
            pct = float(pct_str)
        except ValueError:
            continue
        # 0-100 直接, 0-1 则是 fraction
        if pct > 1:
            pass  # 已经是 %
        elif 0 < pct <= 1:
            pct = pct * 100
        if 0 < pct <= 100:
            sectors.append({"sector": sector, "pct": pct})

    # 检查 sector 名称是否合理 (GICS 11 sectors)
    gics_keywords = [
        "Information Technology", "Technology", "Software", "Semiconductor",
        "Health Care", "Healthcare", "Pharmaceutical", "Biotechnology",
        "Financials", "Financial", "Banks", "Insurance",
        "Consumer Discretionary", "Consumer Staples",
        "Industrials", "Energy", "Materials",
        "Utilities", "Real Estate", "Communication Services",
    ]
    is_industry = any(any(kw in s["sector"] for kw in gics_keywords) for s in sectors)
    if not is_industry:
        logger.warning(f"[n30d-parser] sectors 解析不匹配 GICS 关键词: {[s['sector'] for s in sectors[:3]]}")

    return sectors


def _parse_number(s: str) -> Optional[float]:
    """解析 '1,234.56' / '(1,234.56)' / '1.23%' → float, 返回 None 表示非数字"""
    if not s:
        return None
    s = s.replace(',', '').replace('$', '').replace('%', '').strip()
    if not s:
        return None
    neg = False
    if s.startswith('(') and s.endswith(')'):
        neg = True
        s = s[1:-1]
    try:
        v = float(s)
        return -v if neg else v
    except ValueError:
        return None


def parse_holdings_row(tr) -> Optional[dict]:
    """
    解析 holdings row (老 schema 兼容, 但 v0.6.8e 主用 industry_sector_table)

    N-30D Schedule of Investments 典型列 (SPY 实测):
      [0] 空 (缩进)
      [1] Security name (~30-80 字符)
      [2] 空 或 footnote marker
      [3] Shares (数字, 可能有逗号)
      [4] Market value $ (数字, 可能有逗号)
      [5] % of net assets (数字, 1.234%)
    """
    cells = tr.xpath(".//td | .//th")
    if len(cells) < 3:
        return None

    texts = [c.text_content().strip() for c in cells]
    if not any(t for t in texts):
        return None
    if not any(re.search(r'\d', t) for t in texts):
        return None

    pct = None
    for t in reversed(texts):
        if '%' in t:
            m = _parse_number(t)
            if m is not None and 0 < m < 100:
                pct = m
                break
        else:
            m = _parse_number(t)
            if m is not None and 0 < m < 1:
                pct = m * 100
                break

    mv = None
    for t in reversed(texts):
        t_clean = t.replace(',', '').replace('$', '').strip()
        m = re.match(r"^\(?(\d+\.?\d*)\)?$", t_clean)
        if m:
            v = float(m.group(1))
            if v > 1000:
                mv = v
                break

    shares = None
    for t in reversed(texts):
        t_clean = t.replace(',', '').strip()
        m = re.match(r"^\(?(\d+)\)?$", t_clean)
        if m:
            v = float(m.group(1))
            if v > 100:
                shares = v
                break

    candidates = [t for t in texts if t and not re.match(r"^[\d\.,()\$\s%-]+$", t)]
    name = max(candidates, key=len) if candidates else ""

    if not name or mv is None:
        return None

    return {
        "name": name,
        "shares": shares,
        "market_value": mv,
        "pct_of_net_assets": pct,
    }


def parse_n30d_holdings(url: str) -> dict:
    """
    主函数: 拉 N-30D + 找 INDUSTRY sector table (P7-2 真修路径)
    Returns: {url, n_sectors, sectors, elapsed_seconds, table_rows}
    """
    t0 = time.time()
    html = fetch_n30d_html(url)
    if not html:
        return {"error": "html_fetch_failed", "url": url}

    table, all_tables = find_industry_sector_table(html)
    if table is None:
        return {"error": "no_industry_table_found", "url": url, "n_tables": len(all_tables)}

    sectors = parse_industry_sector_table(table)
    elapsed = time.time() - t0

    # 验证: 11 sector + 总和 ~100%, 否则 fallback
    total = sum(s["pct"] for s in sectors)
    if not (8 <= len(sectors) <= 15) or not (90 < total < 110):
        logger.warning(f"[n30d-parser] 第一次解析不符: {len(sectors)} sectors, total {total:.1f}%, 试其他 table")
        # 找所有可能含 INDUSTRY 文本的表
        for i, t in enumerate(all_tables):
            text = t.text_content() if hasattr(t, 'text_content') else ""
            upper = text[:500].upper()
            if "INDUSTRY" not in upper and "SECTOR" not in upper:
                continue
            if "NET ASSETS" not in upper and "%" not in text:
                continue
            test_sectors = parse_industry_sector_table(t)
            test_total = sum(s["pct"] for s in test_sectors)
            if 8 <= len(test_sectors) <= 15 and 90 < test_total < 110:
                logger.info(f"[n30d-parser] table {i} 找到真 11 sector 总表, {len(test_sectors)} sectors, {test_total:.1f}%")
                sectors = test_sectors
                table = t
                total = test_total
                break

    logger.info(f"[n30d-parser] sector 解析完成: {len(sectors)} 个 GICS sector, total {total:.1f}%, {elapsed:.1f}s")

    return {
        "url": url,
        "n_sectors": len(sectors),
        "sectors": sectors,
        "elapsed_seconds": elapsed,
    }


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

    import argparse
    parser = argparse.ArgumentParser(description="N-30D HTML parser (v0.6.8e Stage 2.2.1)")
    parser.add_argument("--smoke", action="store_true", help="解析 1 个 N-30D (默认 SPY)")
    parser.add_argument("--url", type=str,
                        default="https://www.sec.gov/Archives/edgar/data/884394/000119312526247066/d75559dn30d.htm",
                        help="N-30D HTML URL")
    args = parser.parse_args()

    if args.smoke:
        print(f"[--smoke] 解析 N-30D (industry sector table):")
        r = parse_n30d_holdings(args.url)
        if r.get("error"):
            print(f"  FAIL: {r['error']}")
        else:
            print(f"  OK: {r['n_sectors']} GICS sector 解析 ({r['elapsed_seconds']:.1f}s)")
            print(f"\n  11 GICS sector weights:")
            for s in r["sectors"]:
                print(f"    {s['sector'][:50]:50s}  {s['pct']:>5.2f}%")
            total = sum(s["pct"] for s in r["sectors"])
            print(f"\n  总和: {total:.2f}% (应 ~100%)")
