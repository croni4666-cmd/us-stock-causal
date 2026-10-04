"""Offline-first, asset-specific report. No implicit network or proxy changes."""
from __future__ import annotations

from datetime import date, datetime, time, timezone
import hashlib
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from src.asset_models import (ASSET_KINDS, duration_effect, equity_contributions,
                              gold_archive_metrics, period_return, return_summary, treasury_profile)
from src.asset_sources import SOURCE_SPECS, eligible_snapshot, load_sources
from src.asset_market import action_summary, select_market
from src.asset_daily import daily_equity_attribution


def _read_market(symbol, root, market_files=None):
    # Called with supported assets or issuer tickers; never interpolate a path
    # supplied by a remote issuer into directory traversal or glob wildcards.
    if not symbol or any(c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789^=._-" for c in symbol):
        raise ValueError("invalid market symbol")
    name = symbol.replace("^", "_").replace("=", "_").replace(".", "_") + ".parquet"
    paths = ([Path(market_files[symbol])] if market_files and symbol in market_files else
             list(Path(root).rglob(name)))
    if not paths:
        raise ValueError(f"market cache missing: {symbol}")
    if len(paths) != 1:
        raise ValueError(f"ambiguous market cache: {symbol}")
    data = pd.read_parquet(paths[0])
    data.attrs['market_source'] = {"path": str(paths[0]),
        "sha256": hashlib.sha256(paths[0].read_bytes()).hexdigest(),
        "availability_status": "historical publication and revision times unverified"}
    return data


def _unavailable(reason):
    return {"status": "unavailable", "reason": reason, "causal_status": "not_identified"}


def _available(doc, end, mode):
    if mode == "retrospective":
        return True
    cutoff = datetime.combine(date.fromisoformat(end), time(16, 30), ZoneInfo("America/New_York"))
    return datetime.fromisoformat(doc["available_at"]) <= cutoff


def _source_summary(doc):
    return {key: doc[key] for key in ("symbol", "provider", "source_url", "sha256", "as_of",
                                      "retrieved_at", "available_at", "warnings")}


def _qqq_profile(doc):
    equity = [r for r in doc["rows"] if r["asset_class"] == "Equity"]
    return {"as_of": doc["as_of"], "holding_count": len(doc["rows"]), "equity_count": len(equity),
            "equity_weight": sum(r["weight"] for r in equity if r.get("weight") is not None),
            "known_weight": sum(r["weight"] for r in doc["rows"] if r.get("weight") is not None),
            "unknown_weight_count": sum(r.get("weight") is None for r in doc["rows"]),
            "classification": doc.get("classification"),
            "non_equity": [{"type": r["asset_class"], "weight": r["weight"]}
                           for r in doc["rows"] if r["asset_class"] != "Equity"]}


def build_asset_report(symbols: list[str], start: str, end: str, market_root: Path,
                       source_root: Path, *, mode: str = "point_in_time", market_files: dict | None = None,
                       market_store: Path | None = None) -> dict:
    if mode not in ("point_in_time", "retrospective"):
        raise ValueError("mode must be point_in_time or retrospective")
    if date.fromisoformat(start) > date.fromisoformat(end):
        raise ValueError("start must not be after end")
    if not symbols or len(symbols) != len(set(symbols)) or any(s not in ASSET_KINDS for s in symbols):
        raise ValueError("expected unique supported asset symbols")
    if market_store is not None and market_files:
        raise ValueError('market-store and explicit legacy market-file cannot be combined')
    def read_market(symbol):
        return (select_market(symbol, market_store, start, end, mode=mode) if market_store is not None
                else _read_market(symbol, market_root, market_files))
    result = {"schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(),
              "start": start, "end": end, "mode": mode, "assets": [],
              "historical_trade_backtest_ready": False,
              "limitations": ["market cache observation dates do not certify historical publication or revision times"],
              "causal_readiness": {"status": "not_identified", "required": [
                  "timestamped external policy surprise series and independent asset event-window quotes",
                  "information-effect treatment, concurrent-event exclusions and prespecified estimand",
                  "time-held-out validation, placebo tests and uncertainty intervals"]}}
    for symbol in symbols:
        item = {"symbol": symbol, "kind": ASSET_KINDS[symbol], "returns": None,
                "profile": None, "source": None, "market_source": None, "actions": None,
                'daily_attribution': None,
                "attribution": _unavailable("asset-specific inputs unavailable"),
                "errors": []}
        result["assets"].append(item)
        try:
            market = read_market(symbol)
            item["market_source"] = market.attrs['market_source']
            item["returns"] = return_summary(symbol, market, start, end)
            if ASSET_KINDS[symbol].endswith('etf'):
                item['actions'] = action_summary(market, start, end)
        except (ValueError, OSError, KeyError) as exc:
            item["errors"].append(str(exc))
        if symbol not in SOURCE_SPECS:
            item["attribution"] = _unavailable("no official fund holdings model for this price index, futures or yield quote")
            continue
        try:
            docs = load_sources(symbol, source_root)
            valid = [doc for doc in docs if _available(doc, end, mode) and
                     (doc["kind"] == "gold_archive" or doc["as_of"] <= end)]
            current = max(valid, key=lambda d: (d["as_of"], d["available_at"]), default=None)
            if symbol == 'QQQ' and item['returns'] is not None:
                def read_daily_stock(ticker, first, last):
                    return (select_market(ticker, market_store, first, last, mode=mode, availability_end=end)
                            if market_store is not None else _read_market(ticker, market_root, market_files))
                item['daily_attribution'] = daily_equity_attribution(docs, market, read_daily_stock, start, end, mode=mode)
            if current is None:
                item["attribution"] = _unavailable("no official source meeting analysis date/availability cutoff")
                continue
            item["source"] = _source_summary(current)
            if symbol == "GLD":
                rows = [r for r in current["rows"] if r["date"] <= end]
                if rows:
                    item["profile"] = {"as_of": rows[-1]["date"], **rows[-1]}
                item["attribution"] = gold_archive_metrics(current, start, end, mode)
                continue
            item["profile"] = treasury_profile(current) if symbol in ("IEF", "TLT") else _qqq_profile(current)
            beginnings = [doc for doc in docs if eligible_snapshot(doc, start, mode)]
            beginning = max(beginnings, key=lambda d: (d["as_of"], d["available_at"]), default=None)
            if beginning is None:
                item["attribution"] = _unavailable("no eligible beginning holdings/availability; current structure is not historical attribution")
                continue
            if item["returns"] is None:
                item["attribution"] = _unavailable("asset return endpoints unavailable")
                continue
            if symbol == "QQQ":
                stocks, stock_sources = {}, {}
                for row in beginning["rows"]:
                    if row["asset_class"] != "Equity" or not row.get("ticker"):
                        continue
                    try:
                        stock_data = read_market(row["ticker"])
                        stocks[row["ticker"]] = period_return(stock_data["close"], start, end)
                        stock_sources[row["ticker"]] = stock_data.attrs['market_source']
                    except (ValueError, OSError, KeyError):
                        continue  # explicitly reported as missing coverage by the model
                item["attribution"] = equity_contributions(beginning, stocks,
                    item["returns"]["price_return"], start, mode)
                item["attribution"]["market_sources"] = stock_sources
            else:
                profile = treasury_profile(beginning)
                if not profile["complete"]:
                    item["attribution"] = _unavailable("beginning portfolio duration coverage incomplete")
                    continue
                proxy = "^TNX" if symbol == "IEF" else "^TYX"
                yield_data = read_market(proxy)
                yields = return_summary(proxy, yield_data, start, end)
                effect = duration_effect(profile["weighted_duration_years"], yields["yield_delta_bp"])
                item["attribution"] = {"status": "approximation", "method": "single-tenor yield proxy; linear duration",
                    "beginning_as_of": beginning["as_of"], "beginning_source": _source_summary(beginning),
                    "yield_proxy": proxy, "yield_delta_bp": yields["yield_delta_bp"],
                    "yield_source": yield_data.attrs['market_source'],
                    "duration_years": profile["weighted_duration_years"], "estimated_price_effect": effect,
                    "residual": item["returns"]["price_return"] - effect, "causal_status": "not_identified",
                    "limitations": ["not full-curve repricing; carry, nonparallel shifts, convexity and fees remain unmodeled"]}
            if symbol == "QQQ":
                item["attribution"]["beginning_source"] = _source_summary(beginning)
        except (ValueError, OSError, KeyError) as exc:
            item["errors"].append(str(exc))
            item["attribution"] = _unavailable(str(exc))
    return result


def _pct(value):
    return "缺失" if value is None else f"{value * 100:+.4f}%"


def render_asset_report(result: dict) -> str:
    mode = "事后解释，不能作为当时可交易回测" if result["mode"] == "retrospective" else "官方输入按当时可用时间约束；行情发布时间尚未验证"
    lines = ["# 资产专用分析", "", f"期间：{result['start']} → {result['end']}。模式：{mode}。", "",
             "因果效应：未识别。以下为回报描述、官方结构和满足条件的机械近似。", "",
             "个人账户持仓不是此报告的输入。行情缓存缺少历史发布与修订时间，当前不能认证为可交易历史回测。"]
    for item in result["assets"]:
        symbol, returns, profile, attr = item["symbol"], item["returns"], item["profile"], item["attribution"]
        lines.extend(["", f"## {symbol}", ""])
        if returns:
            if item["kind"] == "yield_quote":
                lines.append(f"收益率 {returns['yield_start_pct']:.3f}% → {returns['yield_end_pct']:.3f}%，变化 {returns['yield_delta_bp']:+.2f}bp；不是债券投资回报。")
            else:
                lines.append(f"价格/报价变动：{_pct(returns['price_return'])}。")
                if item["kind"].endswith("etf"):
                    lines.append(f"供应商调整序列总回报代理：{_pct(returns['adjusted_return_proxy'])}；与价格回报差：{_pct(returns['adjustment_gap'])}，不能直接当现金分红收益。")
            lines.extend(returns["limitations"])
        if item["source"]:
            source = item["source"]
            lines.append(f"官方数据所属日期：{source['as_of']}；取得/保守可用时间：{source['available_at']}。")
            lines.append(f"来源：[{source['provider']}]({source['source_url']})；SHA256：`{source['sha256']}`。")
            lines.extend(source["warnings"])
        if item.get('actions'):
            actions = item['actions']
            lines.append('公司行动（区间起点不包含、终点包含；保留提供商每股金额与拆股比率）：')
            for event in actions['events']:
                lines.append(f"- {event['date']}：{event['field']} = {event['value']}。")
            if not actions['events']:
                lines.append('已提供字段未记录非零事件。')
            if actions['missing_fields']:
                lines.append('事件字段不完整：' + ', '.join(actions['missing_fields']) + '；不补零。')
            if actions.get('missing_market_dates'):
                lines.append('公司行动观察缺少交易日：' + ', '.join(actions['missing_market_dates']) + '；期间现金合计未知。')
            lines.append('价格已含提供商拆股调整，不重复乘拆股比率；每股分红记录不等于认证总收益。')
        if item.get('daily_attribution'):
            daily = item['daily_attribution']
            if daily['status'] == 'unavailable':
                lines.append('QQQ逐日核算未就绪；完整期间链接贡献未输出。')
                if daily['missing_weight_dates']:
                    lines.append('缺少同日期期初权重/可用时间：' + ', '.join(daily['missing_weight_dates']) + '。')
                if daily['missing_market_dates']:
                    lines.append('缺少行情交易日：' + ', '.join(daily['missing_market_dates']) + '。')
            else:
                lines.append(f"QQQ逐日财富链接贡献 {_pct(daily['linked_contribution'])}；链接残差 {_pct(daily['linked_residual'])}；两者合计为ETF价格回报 {_pct(daily['etf_price_return'])}。")
                lines.append('逐日保留原始权重，缺失股票不重归一化；机械核算不代表因果效应。')
        if profile:
            lines.append(f"结构日期：{profile['as_of']}。")
            if symbol in ("IEF", "TLT"):
                lines.append(f"债券 {profile['bond_count']} 支，权重 {profile['bond_weight']:.4%}；已知权重总计 {profile['known_weight']:.4%}；久期已覆盖债券权重 {profile['duration_covered_weight']:.4%}。")
                lines.append(f"按原始权重计算的久期：{profile['weighted_duration_years']:.4f} 年。")
                if profile["complete"]:
                    lines.append(f"当前结构平行上移10bp的线性价格敏感性：{_pct(duration_effect(profile['weighted_duration_years'], 10))}，不是历史回报归因。")
                else:
                    lines.append("久期覆盖不完整，未提供全组合敏感性。")
            elif symbol == "QQQ":
                lines.append(f"官方记录 {profile['holding_count']} 条；股票 {profile['equity_count']} 条，权重 {profile['equity_weight']:.4%}；已知权重总计 {profile['known_weight']:.4%}；未知权重记录 {profile['unknown_weight_count']} 条。")
                lines.append("非股票原始权重：" + "；".join(f"{r['type']}={r['weight']:.6%}" if r['weight'] is not None else f"{r['type']}=未知" for r in profile['non_equity']))
            elif symbol == "GLD":
                lines.append(f"每股黄金：{profile.get('ounces_per_share')} 盎司；16:15官方溢折价：{profile.get('premium_pct_1615')}%（缺值时不补齐）。")
        if attr["status"] == "unavailable":
            lines.append(f"专用期间分析未就绪：{attr['reason']}。")
        elif symbol in ("IEF", "TLT"):
            beginning_source = attr['beginning_source']
            lines.append(f"归因期初证据：日期 {beginning_source['as_of']}；取得/可用时间 {beginning_source['available_at']}；SHA256 `{beginning_source['sha256']}`。")
            lines.append(f"期初持仓 {attr['beginning_as_of']}；单期限代理 {attr['yield_proxy']} 变化 {attr['yield_delta_bp']:+.2f}bp，线性久期近似 {_pct(attr['estimated_price_effect'])}，价格残差 {_pct(attr['residual'])}。")
            lines.append("此近似未覆盖全曲线、凸性、票息、费用与非平行变化。")
        elif symbol == "QQQ":
            beginning_source = attr['beginning_source']
            lines.append(f"归因期初证据：日期 {beginning_source['as_of']}；取得/可用时间 {beginning_source['available_at']}；SHA256 `{beginning_source['sha256']}`。")
            lines.append(f"固定期初权重覆盖 {attr['covered_weight']:.4%}；股票价格贡献 {_pct(attr['contribution'])}；残差 {_pct(attr['residual'])}。")
            if attr["missing_tickers"]:
                lines.append("缺失股票回报：" + ", ".join(attr["missing_tickers"]))
            lines.extend(["", "| 股票 | 原始权重 | 价格回报 | 贡献 |", "|---|---:|---:|---:|"])
            for row in attr["contributions"][:10]:
                lines.append(f"| {row['ticker']} | {row['weight']:.4%} | {_pct(row['price_return'])} | {_pct(row['contribution'])} |")
            lines.extend(["", "成分股行情证据（本地输入，不代表历史发布时间）：", ""])
            for ticker, evidence in attr['market_sources'].items():
                lines.append(f"- {ticker}：`{evidence['path']}`；SHA256 `{evidence['sha256']}`。")
            lines.append("固定期初权重的期间近似；现金、衍生品、分红、费用和交易留在残差，未重归一化。")
        elif symbol == "GLD":
            lines.append(f"官方档案价格回报 {_pct(attr['price_return'])}；纽约10:30 NAV回报 {_pct(attr['nav_return_1030'])}；每股黄金储备变化 {_pct(attr['backing_change'])}。")
            lines.append("价格与NAV定价时点不同；回报差不能当净跟踪误差。独立授权黄金基准缺失，不能做黄金价格因果分解。")
        lines.extend(f"数据问题：{error}" for error in item["errors"])
    lines.extend(["", "## 因果研究下一步", "", "需要带时间戳的政策意外冲击、独立的事件窗口报价、信息效应处理和样本外检验。日线、持仓核算与普通回归不足以识别政策冲击的因果效应。", ""])
    return "\n".join(lines)
