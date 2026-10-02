"""examples/track_30days.py — 30 天 daily sector 跟踪报告

每天回答:
- 4 指数 (DIA/QQQ/RSP/QQQE) 1d 涨跌
- 11 行业 (XL* 11) 1d 涨跌, 涨最多 / 跌最多
- 6 macro (VIX/TNX/DXY/IRX/FVX/TYX) 1d 变化
- 涨/跌最多 板块原因 (跟 macro 关联 + 期货商品)

跑法: python examples/track_30days.py [--days 30] [--output output/track_30days.md]
"""
from __future__ import annotations

import argparse
import io
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# 4 指数
INDICES = ["DIA", "QQQ", "RSP", "QQQE"]
INDICES_LAYER = "indices"
# 11 行业 (GICS)
SECTORS = [
    ("XLK", "Tech"),
    ("XLF", "Fin"),
    ("XLV", "Health"),
    ("XLE", "Energy"),
    ("XLY", "ConsDisc"),
    ("XLP", "ConsStap"),
    ("XLI", "Industrial"),
    ("XLU", "Utility"),
    ("XLB", "Material"),
    ("XLRE", "RealEstate"),
    ("XLC", "CommSvc"),
]
SECTORS_LAYER = "sectors"
# 6 macro
MACROS = ["^VIX", "DXY", "^IRX", "^FVX", "^TNX", "^TYX"]
MACROS_LAYER = "macro"
# 4 关键期货 (金/油/气/铜, 跟 industry 中介)
FUTURES = ["GC=F", "CL=F", "NG=F", "HG=F"]  # 金 / WTI 油 / 天然气 / 铜
FUTURES_LAYER = "commodities_futures"


def _safe_name(symbol: str) -> str:
    return symbol.replace("^", "_").replace("=", "_")


def _load_close(symbol: str, layer: str) -> pd.Series:
    safe = _safe_name(symbol)
    pq = PROJECT_ROOT / "data" / "raw" / layer / f"{safe}.parquet"
    df = pd.read_parquet(pq)
    return df["close"]


def _last_n_days(series: pd.Series, n: int) -> pd.Series:
    return series.dropna().tail(n)


def _format_reason_sector(sector_sym: str, sector_name: str, ret_pct: float,
                          idx_returns: dict, macro_changes: dict, future_changes: dict) -> str:
    """根据 macro / 期货变化 推断 板块涨跌原因 (启发式, 非严格因果)"""
    reasons = []
    sym_upper = sector_sym.upper()  # e.g. XLE
    # 1. 跟 macro 关联
    if sym_upper == "XLE" and macro_changes.get("CL=F", 0) > 0.02:
        reasons.append(f"原油 CL=F +{macro_changes['CL=F']*100:.1f}% → 能源股 受益")
    elif sym_upper == "XLE" and macro_changes.get("CL=F", 0) < -0.02:
        reasons.append(f"原油 CL=F {macro_changes['CL=F']*100:.1f}% → 能源股 承压")
    if sym_upper == "XLF" and macro_changes.get("DXY", 0) > 0.005:
        reasons.append(f"美元 DXY +{macro_changes['DXY']*100:.2f}% → 金融股 利率敏感")
    if sym_upper == "XLU" and macro_changes.get("^TNX", 0) > 0.05:
        reasons.append(f"10Y TNX +{macro_changes['^TNX']*100:.2f}% → 公用事业 折现率上升")
    if sym_upper == "XLB" and macro_changes.get("GC=F", 0) > 0.015:
        reasons.append(f"黄金 GC=F +{macro_changes['GC=F']*100:.1f}% → 材料股 避险")
    if sym_upper == "XLRE" and macro_changes.get("^TNX", 0) > 0.05:
        reasons.append(f"10Y TNX +{macro_changes['^TNX']*100:.2f}% → 房地产 折现率上升")
    if sym_upper == "XLV" and macro_changes.get("^VIX", 0) > 0.10:
        reasons.append(f"VIX +{macro_changes['^VIX']*100:.0f}% → 医疗防御性 受益")
    if sym_upper == "XLP" and macro_changes.get("^VIX", 0) > 0.10:
        reasons.append(f"VIX +{macro_changes['^VIX']*100:.0f}% → 消费必需品 防御性")
    if sym_upper == "XLK" and macro_changes.get("^TNX", 0) > 0.05:
        reasons.append(f"10Y TNX +{macro_changes['^TNX']*100:.2f}% → 科技股 DCF 折现率上升")
    # 2. 跟 VIX 关联 (general risk-on/off)
    if macro_changes.get("^VIX", 0) < -0.05 and ret_pct > 0:
        reasons.append("VIX 跌 (风险偏好回升) 板块普涨")
    elif macro_changes.get("^VIX", 0) > 0.10 and ret_pct < 0:
        reasons.append("VIX 涨 (风险厌恶) 板块普跌")
    # 3. 跟指数强弱关联
    qqq = idx_returns.get("QQQ", 0)
    dia = idx_returns.get("DIA", 0)
    if sym_upper in ("XLK", "XLC", "XLY") and qqq > 0.005 and ret_pct > qqq:
        reasons.append(f"QQQ +{qqq*100:.2f}% 板块跑赢 (科技/消费/通讯强势)")
    if sym_upper in ("XLE", "XLF", "XLI") and dia > 0.005 and ret_pct > dia:
        reasons.append(f"DIA +{dia*100:.2f}% 板块跑赢 (传统经济强势)")
    # 默认: 板块自身动量
    if not reasons:
        if ret_pct > 0.02:
            reasons.append("板块自身动量 (无明显 macro 触发, 可能公司 / 行业事件)")
        elif ret_pct < -0.02:
            reasons.append("板块自身回调 (无明显 macro 触发)")
        else:
            reasons.append("板块窄幅波动")
    return " | ".join(reasons)


def track(days: int = 30, output_path: Path = None) -> None:
    """30 天 daily sector 跟踪"""
    # 加载所有数据 (close price series)
    idx_data = {sym: _load_close(sym, INDICES_LAYER) for sym in INDICES}
    sec_data = {sym: _load_close(sym, SECTORS_LAYER) for sym, _ in SECTORS}
    macro_data = {sym: _load_close(sym, MACROS_LAYER) for sym in MACROS}
    fut_data = {sym: _load_close(sym, FUTURES_LAYER) for sym in FUTURES}

    # 找 days+1 天公共日期范围 (last_n 是后 days 天, prev_baseline 是 day 0 之前 1 天)
    all_dates = set(idx_data[INDICES[0]].index)
    for d in idx_data.values():
        all_dates &= set(d.index)
    for d in sec_data.values():
        all_dates &= set(d.index)
    sorted_dates = sorted(all_dates)
    last_n = sorted_dates[-(days+1):]  # days+1 天 (含 1 个 prev baseline)

    lines = [
        f"# 📊 30 天 Daily Sector 跟踪报告 (深度追踪)",
        f"\n**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**追踪范围**: {last_n[0].date()} ~ {last_n[-1].date()} (共 {len(last_n)} 个交易日)",
        f"**追踪对象**: 4 指数 + 11 行业 + 6 macro + 4 关键期货",
        f"\n---\n",
    ]

    # 累计趋势 (用 last_n[1:] 跟 [0] 比)
    lines.append("## 30 天累计趋势 (last 30 trading days)\n")
    lines.append("### 4 指数 累计收益")
    lines.append("| 指数 | 累计收益 | 涨/跌 |")
    lines.append("|---|---|---|")
    for sym in INDICES:
        start = idx_data[sym].loc[last_n[0]]
        end = idx_data[sym].loc[last_n[-1]]
        ret = (end / start - 1) * 100
        arrow = "🟢" if ret > 0 else "🔴"
        lines.append(f"| **{sym}** | {ret:+.2f}% | {arrow} |")

    lines.append("\n### 11 行业 累计收益 (按累计收益排序)")
    lines.append("| 行业 | 累计收益 | 涨/跌 |")
    lines.append("|---|---|---|")
    sec_cum = []
    for sym, name in SECTORS:
        start = sec_data[sym].loc[last_n[0]]
        end = sec_data[sym].loc[last_n[-1]]
        ret = (end / start - 1) * 100
        sec_cum.append((sym, name, ret))
    sec_cum.sort(key=lambda x: x[2], reverse=True)
    for sym, name, ret in sec_cum:
        arrow = "🟢" if ret > 0 else "🔴"
        lines.append(f"| **{sym}** ({name}) | {ret:+.2f}% | {arrow} |")

    lines.append("\n### 6 macro 变化 (30 天累计, 绝对变化)")
    lines.append("| Macro | 起始 | 结束 | 变化 | 解读 |")
    lines.append("|---|---|---|---|---|")
    for sym in MACROS:
        s = macro_data[sym].loc[last_n[0]]
        e = macro_data[sym].loc[last_n[-1]]
        delta = e - s
        if sym == "^VIX":
            interp = f"VIX {'升 (风险厌恶)' if delta > 0 else '降 (风险偏好)'}"
        elif sym.startswith("^") or sym in ("^TNX", "^TYX", "^FVX", "^IRX"):
            interp = f"利率 {'升' if delta > 0 else '降'} ({delta*100:+.0f}bp)"
        elif sym == "DXY":
            interp = f"美元 {'升' if delta > 0 else '降'}"
        else:
            interp = ""
        lines.append(f"| **{sym}** | {s:.2f} | {e:.2f} | {delta:+.2f} | {interp} |")

    lines.append("\n### 4 关键期货 30 天累计")
    lines.append("| 期货 | 累计 |")
    lines.append("|---|---|")
    for sym in FUTURES:
        start = fut_data[sym].loc[last_n[0]]
        end = fut_data[sym].loc[last_n[-1]]
        ret = (end / start - 1) * 100
        lines.append(f"| **{sym}** | {ret:+.2f}% |")

    lines.append("\n---\n")
    lines.append("## 每日详细 (last 30 trading days)\n")

    # 每日详细 (last_n 含 days+1 天, 但 day count 跟 user 期望的 days 一致)
    for i, date in enumerate(last_n[1:], start=1):  # 跳过 prev baseline (index 0)
        lines.append(f"\n### {date.date()} (Day {i}/{len(last_n)-1})\n")

        # 4 指数 1d 收益
        lines.append("**4 指数 1d**:")
        idx_returns_today = {}
        prev_date = last_n[i-1]  # 永远有 (last_n 是 days+1 天)
        for sym in INDICES:
            try:
                today_p = idx_data[sym].loc[date]
                prev_p = idx_data[sym].loc[prev_date]
                ret = (today_p / prev_p - 1) * 100
                idx_returns_today[sym] = ret / 100
                arrow = "🟢" if ret > 0 else "🔴"
                lines.append(f"- {sym}: {ret:+.2f}% {arrow}")
            except (KeyError, IndexError):
                lines.append(f"- {sym}: n/a")

        # 11 行业 1d 收益, 排序找最大 / 最小
        sec_rets_today = []
        for sym, name in SECTORS:
            try:
                today_p = sec_data[sym].loc[date]
                prev_p = sec_data[sym].loc[prev_date]
                ret = (today_p / prev_p - 1) * 100
                sec_rets_today.append((sym, name, ret))
            except (KeyError, IndexError):
                pass
        sec_rets_today.sort(key=lambda x: x[2], reverse=True)

        if sec_rets_today:
            top = sec_rets_today[0]
            bot = sec_rets_today[-1]
            lines.append(f"\n**11 行业 1d 排序** (涨最多 → 跌最多):")
            for sym, name, ret in sec_rets_today[:6]:  # top 6
                arrow = "🟢" if ret > 0 else "🔴"
                lines.append(f"- {sym} ({name}): {ret:+.2f}% {arrow}")
            if len(sec_rets_today) > 6:
                lines.append(f"- ... ({len(sec_rets_today)-6} more)")
            for sym, name, ret in sec_rets_today[-3:]:  # bottom 3
                arrow = "🟢" if ret > 0 else "🔴"
                lines.append(f"- {sym} ({name}): {ret:+.2f}% {arrow}")

        # macro + 期货 变化
        macro_changes_today = {}
        lines.append(f"\n**Macro & 期货 1d 变化**:")
        for sym in MACROS:
            try:
                today_p = macro_data[sym].loc[date]
                prev_p = macro_data[sym].loc[prev_date]
                delta = today_p - prev_p
                macro_changes_today[sym] = delta
                if sym == "^VIX":
                    interp = "(VIX 涨 = 风险厌恶)"
                elif sym.startswith("^"):
                    interp = f"({delta*100:+.0f}bp)"
                elif sym == "DXY":
                    interp = f"({delta*100:+.2f}%)"
                else:
                    interp = ""
                lines.append(f"- {sym}: {delta:+.2f} {interp}")
            except (KeyError, IndexError):
                pass
        for sym in FUTURES:
            try:
                today_p = fut_data[sym].loc[date]
                prev_p = fut_data[sym].loc[prev_date]
                ret = (today_p / prev_p - 1) * 100
                macro_changes_today[sym] = ret / 100
                lines.append(f"- {sym}: {ret:+.2f}%")
            except (KeyError, IndexError):
                pass

        # 涨最多板块 原因
        if sec_rets_today:
            top_sym, top_name, top_ret = sec_rets_today[0]
            bot_sym, bot_name, bot_ret = sec_rets_today[-1]
            lines.append(f"\n**🟢 涨最多: {top_sym} ({top_name}) +{top_ret:.2f}%**")
            lines.append(f"   - 原因: {_format_reason_sector(top_sym, top_name, top_ret/100, idx_returns_today, macro_changes_today, macro_changes_today)}")
            lines.append(f"\n**🔴 跌最多: {bot_sym} ({bot_name}) {bot_ret:+.2f}%**")
            lines.append(f"   - 原因: {_format_reason_sector(bot_sym, bot_name, bot_ret/100, idx_returns_today, macro_changes_today, macro_changes_today)}")

        lines.append("\n---")

    # 写文件
    report = "\n".join(lines)
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report, encoding="utf-8")
        print(f"✅ 报告写到: {output_path} ({len(report)} chars, {len(report.splitlines())} lines)", flush=True)
    print("\n" + report[:3000] + ("\n\n... (省略中间 " + f"{len(last_n)-10}" + " 天)\n\n" if len(last_n) > 10 else "\n"), flush=True)
    if len(last_n) > 10:
        print("... (完整报告在文件里)", flush=True)


def main():
    parser = argparse.ArgumentParser(description="30 天 daily sector 跟踪报告")
    parser.add_argument("--days", type=int, default=30, help="追踪天数 (默认 30)")
    parser.add_argument("--output", type=str, default="output/track_30days.md", help="输出文件路径")
    args = parser.parse_args()
    output_path = PROJECT_ROOT / args.output
    track(days=args.days, output_path=output_path)


if __name__ == "__main__":
    main()
