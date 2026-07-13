"""
examples/attribute.py - 归因分析 v0.3.0 demo

输出:
  - 控制台表格 (4 指数 × 当日归因)
  - output/attribution_<date>.png  (stacked bar: sector contributions)

跑: python examples/attribute.py
"""
from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import matplotlib
matplotlib.use("Agg")  # non-interactive
import matplotlib.pyplot as plt
import numpy as np
from loguru import logger

from src import proxy  # noqa: F401
from src.attribution import attribute_all_indices, attribute_index


def render_console_table(results: list[dict]) -> str:
    """渲染 4 指数归因表到 Markdown"""
    lines = []
    lines.append(f"\n## 4 指数归因 ({results[0]['date']})\n")
    lines.append("| 指数 | 实际 % | 预测 % | 残差 % | 主驱动 (top 3) |")
    lines.append("|------|--------|--------|--------|----------------|")
    for r in results:
        top = ", ".join(f"**{s}** {r['sector_contributions_pct'][s]:+.2f}" for s in r["top_drivers"])
        lines.append(f"| {r['index']} | {r['actual_return_pct']:+.2f} | {r['predicted_return_pct']:+.2f} | {r['residual_pct']:+.2f} | {top} |")
    return "\n".join(lines)


def render_one_index_detail(r: dict) -> str:
    """单个指数的详细归因"""
    lines = [f"\n### {r['index']} — 实际 {r['actual_return_pct']:+.2f}% (预测 {r['predicted_return_pct']:+.2f}%, 残差 {r['residual_pct']:+.2f}%)"]
    lines.append("| 行业 | GICS | 贡献 % | 解读 |")
    lines.append("|------|------|---------|------|")
    gics_names = {
        "XLK": "Technology", "XLF": "Financials", "XLE": "Energy",
        "XLY": "Cons Discr", "XLP": "Cons Staples", "XLV": "Health Care",
        "XLI": "Industrials", "XLU": "Utilities", "XLB": "Materials",
        "XLRE": "Real Estate", "XLC": "Comm Services"
    }
    for s, v in r["sector_contributions_pct"].items():
        # 解读: 大正贡献 / 大负拖累 / 中性
        if abs(v) > 0.3:
            direction = "📈 主升" if v > 0 else "📉 主跌"
        elif abs(v) > 0.1:
            direction = "⬆️ 拉升" if v > 0 else "⬇️ 拖累"
        else:
            direction = "≈ 中性"
        lines.append(f"| {s} | {gics_names.get(s, '?')} | {v:+.2f} | {direction} |")
    return "\n".join(lines)


def render_stacked_bar(results: list[dict], path: Path) -> None:
    """画 4 指数 stacked bar: sector contribution 横向 (English labels to avoid CJK font issue)"""
    sectors = ["XLK", "XLF", "XLE", "XLY", "XLP", "XLV", "XLI", "XLU", "XLB", "XLRE", "XLC"]
    sector_colors = {
        "XLK": "#1f77b4", "XLF": "#ff7f0e", "XLE": "#2ca02c", "XLY": "#d62728",
        "XLP": "#9467bd", "XLV": "#8c564b", "XLI": "#e377c2", "XLU": "#7f7f7f",
        "XLB": "#bcbd22", "XLRE": "#17becf", "XLC": "#aec7e8"
    }
    sector_short = {
        "XLK": "Tech", "XLF": "Fin", "XLE": "Engy", "XLY": "ConsD",
        "XLP": "ConsS", "XLV": "Health", "XLI": "Indus", "XLU": "Util",
        "XLB": "Mat", "XLRE": "RE", "XLC": "Comm"
    }

    fig, axes = plt.subplots(2, 2, figsize=(14, 8))
    axes = axes.flatten()

    for ax, r in zip(axes, results):
        contribs = r["sector_contributions_pct"]
        labels = list(contribs.keys())
        short_labels = [sector_short.get(s, s) for s in labels]
        values = [contribs[s] for s in labels]
        colors = [sector_colors.get(s, "#333333") for s in labels]

        # 横向 bar,正负分开
        y_pos = np.arange(len(labels))
        colors_applied = [c if v >= 0 else "#cc4444" for c, v in zip(colors, values)]
        ax.barh(y_pos, values, color=colors_applied, edgecolor="black", linewidth=0.5)
        ax.set_yticks(y_pos)
        ax.set_yticklabels(short_labels, fontsize=9)
        ax.set_xlabel("Contribution (%)")
        ax.set_title(f"{r['index']} - {r['date']}\nactual {r['actual_return_pct']:+.2f}% / residual {r['residual_pct']:+.2f}%",
                     fontsize=10, fontweight="bold")
        ax.axvline(0, color="black", linewidth=0.8)
        ax.invert_yaxis()  # 最大的在最上面
        ax.grid(axis="x", linestyle="--", alpha=0.3)

    plt.suptitle(f"us-stock-causal v0.3.0 - Sector Attribution ({results[0]['date']})",
                 fontsize=12, fontweight="bold", y=1.00)
    plt.tight_layout()
    plt.savefig(path, dpi=120, bbox_inches="tight")
    plt.close(fig)


def main() -> int:
    print("=" * 72)
    print(f"us-stock-causal v0.3.0 — attribution (Phase 2 demo)")
    print(f"Run time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Proxy active: {proxy.is_proxied()}")
    print("=" * 72)

    t0 = time.time()

    # 当日归因 (4 指数)
    print("\n[1/2] 4 指数当日归因...")
    daily_results = attribute_all_indices(lookback_days=1)

    # 5 日累计归因 (QQQ 详细展示)
    print("[2/2] 4 指数 5 日累计归因...")
    weekly_results = attribute_all_indices(lookback_days=5)

    # 控制台输出
    print(render_console_table(daily_results))
    for r in daily_results:
        print(render_one_index_detail(r))

    # 控制台输出 5 日
    print(f"\n## 4 指数 5 日累计归因 (lookback 5d)\n")
    print(render_console_table(weekly_results))

    # 画图
    output_dir = PROJECT_ROOT / "output"
    output_dir.mkdir(exist_ok=True)
    chart_path = output_dir / f"attribution_{daily_results[0]['date']}.png"
    render_stacked_bar(daily_results, chart_path)

    # 写 Markdown 报告
    md_lines = [
        f"# 📊 归因报告 — {daily_results[0]['date']}",
        f"\n**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**模型**: sector weights (config/sector_weights.json, 2026-Q2 近似值)",
        f"\n**4 指数**: DIA / QQQ / RSP / QQQE",
        f"\n**归因方法**: 直接 sector weight × sector return,残差 = actual - predicted",
        f"\n---\n",
    ]
    md_lines.append(render_console_table(daily_results))
    for r in daily_results:
        md_lines.append(render_one_index_detail(r))
    md_lines.append(f"\n## 5 日累计归因\n")
    md_lines.append(render_console_table(weekly_results))
    md_lines.append(f"\n---\n\n*图: sector 贡献 stacked bar 见 `output/attribution_{daily_results[0]['date']}.png`*\n")

    md_path = output_dir / f"attribution_{daily_results[0]['date']}.md"
    md_path.write_text("\n".join(md_lines), encoding="utf-8")

    elapsed = time.time() - t0
    print(f"\n{'=' * 72}")
    print(f"完成! 耗时 {elapsed:.1f}s")
    print(f"  报告: {md_path}")
    print(f"  图表: {chart_path}")
    print(f"{'=' * 72}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
