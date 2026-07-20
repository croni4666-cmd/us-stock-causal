"""
src/events_gdelt.py - GDELT 2.0 全球新闻事件 (v0.6.8c P-event-enrichment)

GDELT 2.0 Doc API:
  - 拉全球多语种新闻流,免费,无 key
  - 5 秒限流友好 (cache 1h 友好)
  - 含 tone (情绪) 打分 -100 ~ +100
  - URL: https://api.gdeltproject.org/api/v2/doc/doc

为美股事件,拉 macro 关键词 (FOMC/CPI/NFP/PCE) 过去 24h 新闻
转成 MacroEvent 合并到 events.py,补 "为什么这只票今天跌"的外部事件

**Why GDELT not yfinance news**:
  - yfinance 2026 限流 (v0.6.8b 新发现), news 字段缺失/不稳定
  - GDELT 公开 + 情绪打分 + 多语种
  - 跟 P6-3 多窗口归因互补: 单日残差偏大可能是"GDELT 漏了 X 事件"

**范式参考**:
  - Kansoku `.claude/skills/gdelt/scripts/fetch.py` (v0.6.8b 借鉴)
  - 我们不走 mavis skill 包装 (目标不同, Kansoku 是桌面 app, 我们是 CLI)
  - 写独立 src/ 模块, 跟现有 events.py 合并

**Caveats**:
  - GDELT 5 秒限流, 别频繁调 (cache 1h 友好)
  - 文档是 past events, 不能预测未来
  - description = title 前 80 字 + tone 打分
  - 失败 (timeout/rate limit/network) 返回 [], 优雅降级
"""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from typing import Optional
from urllib.parse import urlencode

from loguru import logger
import requests

# Lazy import: src.events.MacroEvent / src.proxy 挪到函数内,
# 这样 src/events_gdelt.py 直接 python 跑 main 时不依赖 sys.path

GDELT_DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"

# 默认 macro 关键词: 美股核心宏观事件 + Fed/Powell
DEFAULT_KEYWORDS = [
    "Federal Reserve", "FOMC",
    "CPI", "inflation", "PPI", "PCE",
    "nonfarm payrolls", "NFP", "unemployment",
    "Treasury", "yield",
    "rate cut", "rate hike", "rate decision",
    "Powell",
]

DEFAULT_LOOKBACK_HOURS = 24
DEFAULT_MAX_RECORDS = 50
TONE_HIGH_THRESHOLD = 5.0  # abs(tone) >= 5 算 high impact
TIMEOUT = 30


def _build_query(keywords: list[str]) -> str:
    """
    用 OR 拼 query, 整段加括号
    GDELT 限制: OR'd terms 必须被 () 包起来
    例: ("Federal Reserve" OR "FOMC" OR "CPI")
    """
    return "(" + " OR ".join(f'"{kw}"' for kw in keywords) + ")"


def _parse_seendate(s: str) -> Optional[date]:
    """GDELT '20260715T120000Z' → date(2026,7,15)"""
    try:
        return datetime.strptime(s[:8], "%Y%m%d").date()
    except (ValueError, TypeError):
        return None


def _tone_to_impact(tone: float) -> str:
    """abs(tone) >= 5 → high, 否则 medium"""
    if abs(tone) >= TONE_HIGH_THRESHOLD:
        return "high"
    return "medium"


def _get_proxies() -> Optional[dict]:
    """从环境变量取 proxy (clash 7897/7899)"""
    http = os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")
    https = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    if not http and not https:
        return None
    return {"http": http, "https": https}


def fetch_gdelt_events(
    from_date: Optional[date] = None,
    lookahead_days: int = 1,
    keywords: Optional[list[str]] = None,
    max_records: int = DEFAULT_MAX_RECORDS,
    use_proxy: bool = True,
) -> list[MacroEvent]:
    """
    拉 GDELT 过去 N 天 (默认 1) macro 关键词新闻, 转成 MacroEvent

    Args:
        from_date: 起始日期 (默认今天)
        lookahead_days: 看未来 N 天 (GDELT 文档都是 past, 实际 1-2 天)
        keywords: macro 关键词列表, 默认 DEFAULT_KEYWORDS
        max_records: API 单次拉取最大数 (GDELT 限 250)
        use_proxy: 是否走 clash proxy (用户机器默认有)

    Returns:
        MacroEvent list (kind="GDELT"), 按日期排序
    """
    # Lazy import (兼容 src/events_gdelt.py 独立运行)
    from src.events import MacroEvent
    from src.proxy import is_proxied

    if from_date is None:
        from_date = date.today()
    if keywords is None:
        keywords = DEFAULT_KEYWORDS

    query = _build_query(keywords)
    params = {
        "query": query,
        "mode": "ToneChart",  # 返回 tone 字段
        "format": "json",
        "maxrecords": str(min(max_records, 250)),
        "sourcelang": "English",
    }
    url = f"{GDELT_DOC_API}?{urlencode(params)}"

    proxies = _get_proxies() if use_proxy else None

    try:
        resp = requests.get(url, timeout=TIMEOUT, proxies=proxies)
        resp.raise_for_status()
    except requests.exceptions.HTTPError as e:
        if e.response is not None and e.response.status_code == 429:
            logger.warning(f"[gdelt] 限流 (429), 跳过本次")
        else:
            logger.warning(f"[gdelt] HTTP 错误: {e}")
        return []
    except Exception as e:
        logger.warning(f"[gdelt] 拉取失败: {e}")
        return []

    # v0.6.8c hotfix: GDELT 限流时返回 plain text (不是 JSON)
    # 检查 content-type + body, 优雅降级
    content_type = resp.headers.get("content-type", "")
    if "json" not in content_type.lower():
        body_lower = resp.text[:500].lower() if resp.text else ""
        if "limit" in body_lower or "rate" in body_lower:
            logger.warning(
                f"[gdelt] 限流 (5s 限流, content-type={content_type}): "
                f"等待下次重试"
            )
        else:
            logger.warning(
                f"[gdelt] 非 JSON 响应 (content-type={content_type}): {resp.text[:200]}"
            )
        return []

    try:
        data = resp.json()
    except Exception as e:
        logger.warning(f"[gdelt] JSON 解析失败: {e}")
        return []

    articles = data.get("articles", [])
    if not articles:
        logger.info(f"[gdelt] 0 篇文章 (query 命中空, query 头: {query[:50]}...)")
        return []

    end_date = from_date + timedelta(days=lookahead_days)
    events = []
    for art in articles:
        d = _parse_seendate(art.get("seendate", ""))
        if d is None or not (from_date <= d <= end_date):
            continue
        try:
            tone = float(art.get("tone", 0.0) or 0.0)
        except (ValueError, TypeError):
            tone = 0.0
        title = (art.get("title") or "").strip()
        if not title:
            continue
        # 截断 title 到 80 字, 加 tone 打分
        desc = f"tone={tone:+.1f} {title[:80]}"
        events.append(MacroEvent(
            date=d,
            kind="GDELT",
            description=desc,
            impact=_tone_to_impact(tone),
        ))

    logger.info(f"[gdelt] 拉取 {len(events)} 条事件 (query 命中 {len(articles)} 篇)")
    return sorted(events, key=lambda e: e.date)


if __name__ == "__main__":
    import sys
    from pathlib import Path
    # 让 src package 可被 import (events_gdelt.py 跑 main 时需要)
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

    import argparse
    parser = argparse.ArgumentParser(description="GDELT events fetcher (v0.6.8c)")
    parser.add_argument("--smoke", action="store_true", help="连通性自检 (参考 Kansoku skill 范式)")
    parser.add_argument("--lookback", type=int, default=1, help="向后看 N 天 (默认 1)")
    parser.add_argument("--max-records", type=int, default=DEFAULT_MAX_RECORDS)
    args = parser.parse_args()

    # 现在可以 import src 子包 (Lazy 已在 fetch_gdelt_events 内)
    from src.proxy import is_proxied  # main 自己用

    print(f"今日: {date.today()}")
    print(f"Proxy active: {is_proxied()}")

    if args.smoke:
        # 自检: 1 个请求, 验证 endpoint 通
        print("\n[--smoke] 连通性自检:")
        events = fetch_gdelt_events(
            lookahead_days=args.lookback,
            max_records=5,
        )
        if events:
            print(f"  OK: 拉到 {len(events)} 条 (示例: {events[0].kind} {events[0].description[:50]})")
        else:
            print(f"  WARN: 0 条 (可能限流, 等 5s 重试, 或检查 proxy)")
    else:
        print(f"\nGDELT 拉取 (向后 {args.lookback} 天 macro 关键词):")
        events = fetch_gdelt_events(
            lookahead_days=args.lookback,
            max_records=args.max_records,
        )
        print(f"  共 {len(events)} 条")
        for e in events[:10]:
            print(f"  {e.date} {e.kind}: {e.description[:80]}")
