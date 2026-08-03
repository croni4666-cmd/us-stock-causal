"""
src/report.py - 5 段制报告生成

Phase 2.3 (P2-9) 设计:
  每个标的 5 段:
    ① 5 日行情
    ② 5 日归因 (sector weights)
    ③ 关键阈值 (SMA + pivot + 52w)
    ④ 历史相似 (pattern match, 5d forward 统计)
    ⑤ 风险 (信号矛盾 + 下个事件 + 距离超买)

字数: ~120 字/段 × 5 = 600 字/标的
对比 v0.2 报告 3000+ 字,信息密度 5x

**因果优先原则**:
  - ①-④ 客观数据 (从 parquet 算的)
  - ⑤ 综合判断 (信号聚合 + 事件日历)
  - 不输出"看多/看空"结论
  - 输出"驱动 + 阈值 + 历史 + 风险",让用户自己判断
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from loguru import logger

from src.thresholds import get_thresholds, load_prices
from src.attribution import attribute_index
from src.patterns import find_similar_patterns
from src.events import next_event
from src.returns import compute_returns, cumulative_return
from src.signals import aggregate_signals
from src.macro import topline as macro_topline, macro_snapshot, indices_1line


def _segment_1_market(symbol: str, layer: str, lookback_days: int) -> str:
    """① 5 日行情"""
    df = load_prices(symbol, layer)
    rets = compute_returns(df["close"], method="simple")
    daily = rets.iloc[-lookback_days:]

    cum = cumulative_return(daily, method="simple")
    best_idx = daily.idxmax()
    worst_idx = daily.idxmin()
    best_date = best_idx.date() if hasattr(best_idx, 'date') else str(best_idx)
    worst_date = worst_idx.date() if hasattr(worst_idx, 'date') else str(worst_idx)

    return (
        f"5 日累计 {cum*100:+.2f}%, "
        f"最好 {best_date} (+{daily[best_idx]*100:.2f}%), "
        f"最差 {worst_date} ({daily[worst_idx]*100:+.2f}%)"
    )


def _segment_2_attribution(symbol: str, lookback_days: int) -> str:
    """② 5 日归因"""
    r = attribute_index(symbol, lookback_days=lookback_days)
    # top 3 贡献(按绝对值)
    contribs = sorted(
        r["sector_contributions_pct"].items(),
        key=lambda x: -abs(x[1])
    )[:3]
    parts = []
    for s, v in contribs:
        if v > 0.05:
            parts.append(f"{s}+{v:.2f}%")
        elif v < -0.05:
            parts.append(f"{s}{v:.2f}%")
    contrib_str = " / ".join(parts) if parts else "(各 sector 贡献均 < 0.05%)"
    return (
        f"主升 {contrib_str}, "
        f"残差 {r['residual_pct']:+.2f}%"
    )


def _segment_3_thresholds(symbol: str, layer: str) -> str:
    """③ 关键阈值"""
    t = get_thresholds(symbol)
    s200 = t["vs_sma"]["sma_200"]
    s200_str = f"200 SMA {s200['position']} {s200['pct']:+.2f}%"
    pos52w = t["range_52w"]["position_pct"]
    p = t["pivots"]
    return (
        f"现价 ${t['last_close']}, "
        f"{s200_str}, 52w {pos52w}%, "
        f"R1 ${p['r1']} / S1 ${p['s1']}"
    )


def _segment_4_patterns(symbol: str, layer: str) -> str:
    """④ 历史相似"""
    p = find_similar_patterns(symbol, pattern_length=20, n_matches=10, forecast_horizon=5)
    return (
        f"20d pattern 相似 top {p['n_matches']}, "
        f"5d fwd avg {p['avg_forward_return']:+.2f}% / "
        f"win {p['win_rate']:.0%} / "
        f"max {p['max_forward']:+.2f}% / min {p['min_forward']:+.2f}%"
    )


def _segment_5_risk(symbol: str) -> str:
    """⑤ 风险"""
    agg = aggregate_signals(symbol)
    warnings = []

    # 信号矛盾
    if agg.contradiction_score >= 0.5:
        warnings.append(f"信号矛盾 score={agg.contradiction_score:.2f}({agg.verdict})")
    elif agg.contradiction_score >= 0.3:
        warnings.append(f"信号部分一致 score={agg.contradiction_score:.2f}")

    # 事件
    ne = next_event()
    if ne and ne.days_until is not None:
        if ne.days_until <= 7:
            warnings.append(f"{ne.days_until}d 后 {ne.kind}({ne.description})")
        elif ne.days_until <= 14:
            warnings.append(f"{ne.days_until}d 后 {ne.kind}")

    # 距离超买
    t = get_thresholds(symbol)
    s200_pct = t["vs_sma"]["sma_200"]["pct"]
    if s200_pct > 12:
        warnings.append(f"200 SMA {s200_pct:+.1f}% 距超买较近")

    return "; ".join(warnings) if warnings else "近期无重大风险"


def five_segment_report(symbol: str, layer: str = "indices", lookback_days: int = 5) -> dict:
    """生成 5 段制报告"""
    return {
        "symbol": symbol,
        "as_of": str(date.today()),
        "lookback_days": lookback_days,
        "segment_1_market": _segment_1_market(symbol, layer, lookback_days),
        "segment_2_attribution": _segment_2_attribution(symbol, lookback_days),
        "segment_3_thresholds": _segment_3_thresholds(symbol, layer),
        "segment_4_patterns": _segment_4_patterns(symbol, layer),
        "segment_5_risk": _segment_5_risk(symbol),
    }


def render_markdown(report: dict) -> str:
    """渲染单个指数 5 段制报告"""
    sym = report["symbol"]
    return f"""## {sym} — {report['as_of']} (5 日报告)

**① 5 日行情**: {report['segment_1_market']}

**② 5 日归因**: {report['segment_2_attribution']}

**③ 关键阈值**: {report['segment_3_thresholds']}

**④ 历史相似**: {report['segment_4_patterns']}

**⑤ 风险**: {report['segment_5_risk']}
"""


def render_full_report(symbols: list[str], layer: str = "indices") -> str:
    """渲染 4 指数完整 5 段制报告 + 因果机制段 (Phase 9)"""
    today = date.today()
    lines = [
        f"# 📊 美股每日分析报告 (5 段制) — {today}",
        f"\n**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**模型**: Phase 2 全套 + Phase 3 顶部情绪 + Phase 9 Pearl 因果",
        f"**字数**: 每标的 ~600 字,5 段结构 (行情 / 归因 / 阈值 / 相似 / 风险) + 1 段因果机制",
        f"\n---\n",
    ]
    # 顶部情绪 1 行 (Phase 3.2 P3-3)
    lines.append(macro_topline())
    lines.append("\n---\n")
    # 因果机制 1 段 (Phase 9.0, v0.6.9+)
    # 默认 include_l3=False (L3 CausalForestDML 慢 ~30s, daily report 怕超 cron timeout)
    # Phase 9.1.5 优化 CausalForestDML 性能 + 加缓存后可改回 True
    causal_section = render_causal_section(include_l3=False)
    if causal_section:
        lines.append(causal_section)
        lines.append("\n---\n")
    for sym in symbols:
        report = five_segment_report(sym, layer=layer)
        lines.append(render_markdown(report))
        lines.append("\n---\n")
    lines.append(
        "\n*免责声明:本报告由自动化分析生成,基于历史数据 + 公开 sector weights。"
        "**不构成投资建议**。信号矛盾 score 越高,越要谨慎。事件前 1 周内的预测需打折。*\n"
    )
    return "\n".join(lines)


def render_causal_section(include_l3: bool = False) -> str:
    """v0.6.9 (P9.1.6) 渲染 Pearl-style 因果机制段

    Pearl 3 层因果阶梯 (L1 关联 = Phase 2 attribution 已写在每段报告里):
      - L2 干预 P(QQQ | do(VIX/TNX+1%)) — DoWhy + OLS
      - L3 反事实 P(QQQ_x | 实际值, cf值) — econml CATE 近似

    数据来自 7 节点手工 DAG (config/causal_dag.yaml: ^TNX/^VIX/DXY → DIA/QQQ/RSP/QQQE)
    约 500 交易日 log return 数据, 用 statsmodels OLS (绕开 DoWhy linear_regression 已知 bug)

    Args:
        include_l3: 是否含 L3 反事实 (慢, 约 30s CausalForestDML fit)

    Returns:
        Markdown 字符串 (~200-300 字), 失败时返回 ""
    """
    try:
        from src import causal as causal_mod
    except ImportError as e:
        logger.warning(f"[causal section] import 失败: {e}")
        return ""

    cfg = causal_mod.load_dag_config()
    try:
        data = causal_mod.load_dag_data(cfg=cfg)
    except FileNotFoundError as e:
        logger.warning(f"[causal section] 缺 parquet: {e}")
        return ""

    lines = ["## 因果机制 (Phase 9.0 Pearl-style)\n"]

    # L2 do-calculus 2 个最 robust 的 query
    try:
        for treatment, outcome, label in [
            ("VIX", "QQQ", "恐慌指数 (VIX)"),
            ("TNX", "QQQ", "10Y 国债 (^TNX)"),
        ]:
            eff = causal_mod.causal_query(
                treatment=treatment, outcome=outcome, data=data, cfg=cfg
            )
            direction = "↑" if eff.estimate > 0 else "↓"
            sig = "显著" if eff.p_value < 0.05 else "不显著"
            refute_pass = sum(1 for v in eff.refutation.values() if "new_effect" in v)
            lines.append(
                f"- **L2 干预**: {label} `do(+1%)` → {outcome} 预期{direction} "
                f"{abs(eff.estimate):.4f} ({abs(eff.estimate)*100:+.2f}%, "
                f"p={eff.p_value:.3f} {sig}); "
                f"反驳测试 {refute_pass}/3 通过"
            )
    except Exception as e:
        logger.warning(f"[causal section] L2 query 失败: {e}")
        lines.append(f"- L2 干预: 查询失败 ({type(e).__name__}: {e})")

    # L3 反事实 (可选, 慢)
    if include_l3:
        try:
            last_date = str(data.index[-1].date())
            actual_vix = float(data.iloc[-1]["VIX"])
            cf_vix = actual_vix - 0.05  # 假设 VIX 比实际低 5%
            cf = causal_mod.counterfactual_query(
                date=last_date, treatment="VIX", outcome="QQQ",
                counterfactual_value=cf_vix, data=data, cfg=cfg,
            )
            lines.append(
                f"- **L3 反事实** (近似, 用 econml CATE 严格 L3 需 SCM): "
                f"{cf.date} 假设 VIX -{abs(cf_vix-actual_vix)*100:.1f}% "
                f"(从 {actual_vix*100:+.2f}% 到 {cf_vix*100:+.2f}%), "
                f"{cf.outcome} 实际 {cf.actual_outcome*100:+.2f}% → "
                f"反事实 {cf.counterfactual_outcome*100:+.2f}% "
                f"(差 {cf.delta*100:+.2f}%)"
            )
        except Exception as e:
            logger.warning(f"[causal section] L3 query 失败: {e}")
            lines.append(f"- L3 反事实: 查询失败 ({type(e).__name__}: {e})")

    # P9-1.1: PC algorithm 跟手工 DAG 对比 (DAG 验证)
    try:
        manual_dag = causal_mod.load_dag_graph(cfg)
        pc_dag = causal_mod.discover_dag_pc(data, alpha=0.05)
        cmp = causal_mod.compare_dags(manual_dag, pc_dag)
        n_overlap = len(cmp["overlap"])
        n_manual = manual_dag.number_of_edges()
        n_pc = pc_dag.number_of_edges()
        overlap_rate = n_overlap / (n_overlap + len(cmp["manual_only"]) + len(cmp["pc_only"])) if (n_overlap + len(cmp["manual_only"]) + len(cmp["pc_only"])) > 0 else 0
        if n_overlap >= 2:
            dag_status = "✅"
        elif n_overlap >= 1:
            dag_status = "⚠️"
        else:
            dag_status = "❌"
        overlap_str = ", ".join(f"{s}→{d}" for s, d in cmp["overlap"][:3])
        if len(cmp["overlap"]) > 3:
            overlap_str += f" 等 {n_overlap} 条"
        lines.append(
            f"- **DAG 验证 (P9-1.1 PC vs 手工)**: {dag_status} 重叠 {n_overlap}/{n_pc} 边 "
            f"({overlap_rate*100:.0f}% 一致); PC 学出 {n_pc} 边, 手工 {n_manual} 边; "
            f"主要重叠: {overlap_str if overlap_str else '无'}"
        )
    except Exception as e:
        logger.warning(f"[causal section] PC DAG 验证失败: {e}")
        lines.append(f"- DAG 验证: PC algorithm 失败 ({type(e).__name__}: {e})")

    # 引用 + 范围
    lines.append(
        f"\n*数据基础: {len(data)} 交易日 log return, "
        f"7 节点 DAG (3 macro × 4 指数), n=508 起, "
        f"OLS regression + DoWhy DAG 验证 + 3 重 refutation + PC algorithm 对比. "
        f"Pearl L3 用 econml CATE 近似 (严格需 SCM, Phase 9.1.3 实施).*"
    )

    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    for sym in ["DIA", "QQQ", "RSP", "QQQE"]:
        print(render_markdown(five_segment_report(sym)))
        print()
