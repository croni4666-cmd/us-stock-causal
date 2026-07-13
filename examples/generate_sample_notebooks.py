"""
generate_sample_notebooks.py - 用 nbformat 生成 3 个 sample notebook

为什么用脚本生成而不是手写 .ipynb JSON:
  - nbformat 5.10 提供 nbformat.v4.nbformat_new() + cell 结构,代码安全
  - 3 个 notebook 共 15+ cell,手写 JSON 易错
  - 改 cell 内容时改 Python 字符串即可,不用记 nbformat 字段名

3 个 notebook:
  - 01_load_and_explore.ipynb: 加载 parquet + 基本探索 (5 cells)
  - 02_attribution_custom.ipynb: 用自己的 sector weights 跑归因 (8 cells)
  - 03_pattern_match.ipynb: 历史 pattern 匹配 + 自定义 forward return (6 cells)

跑: python examples/generate_sample_notebooks.py
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import nbformat as nbf
from nbformat.v4 import new_notebook, new_markdown_cell, new_code_cell


def make_nb_01() -> dict:
    """01_load_and_explore.ipynb - 加载 parquet + 探索"""
    cells = [
        new_markdown_cell(
            "# 📓 01 — 加载数据 + 基本探索\n\n"
            "**目标**: 学会用 `load_prices()` 加载 parquet cache,做基本的数据探索。\n\n"
            "**适合**: 第一次用 us-stock-causal 的用户。\n\n"
            "---\n\n"
            "**前置条件**: 已经跑过 `python examples/fetch_all.py`,data/raw/ 里有 parquet 文件。\n\n"
            "如果还没跑,先开一个 terminal:\n"
            "```bash\n"
            "python examples/fetch_all.py\n"
            "```\n"
        ),
        new_code_cell(
            "# 第 1 步: import (含 robust path 修复 — 找含 src/ 的目录)\n"
            "import sys\n"
            "from pathlib import Path\n"
            "\n"
            "def _find_project_root():\n"
            "    cwd = Path.cwd()\n"
            "    for cand in [cwd, *cwd.parents]:\n"
            "        if (cand / 'src').is_dir() and (cand / 'config').is_dir():\n"
            "            return cand\n"
            "    return cwd\n"
            "\n"
            "PROJECT_ROOT = _find_project_root()\n"
            "sys.path.insert(0, str(PROJECT_ROOT))\n"
            "print(f\"Project root: {PROJECT_ROOT}\")\n"
            "\n"
            "import pandas as pd\n"
            "import matplotlib.pyplot as plt\n"
            "\n"
            "from src.thresholds import load_prices"
        ),
        new_code_cell(
            "# 第 2 步: 加载 4 指数的 1 年数据\n"
            "tickers = ['DIA', 'QQQ', 'RSP', 'QQQE']\n"
            "dfs = {sym: load_prices(sym, 'indices') for sym in tickers}\n"
            "\n"
            "for sym, df in dfs.items():\n"
            "    print(f\"{sym:6s}: {len(df):>4d} rows, \"\n"
            "          f\"{df.index[0].date()} → {df.index[-1].date()}, \"\n"
            "          f\"close ${df['close'].iloc[-1]:.2f}\")"
        ),
        new_code_cell(
            "# 第 3 步: 算 1 日简单收益率 + 累计 5 日收益率\n"
            "for sym, df in dfs.items():\n"
            "    rets = df['close'].pct_change()\n"
            "    cum_5d = (df['close'].iloc[-1] / df['close'].iloc[-6] - 1) * 100\n"
            "    print(f\"{sym:6s}: 1d {rets.iloc[-1]*100:+.2f}% | \"\n"
            "          f\"5d cum {cum_5d:+.2f}%\")"
        ),
        new_code_cell(
            "# 第 4 步: 画 4 指数归一化对比 (起点 = 1.0)\n"
            "fig, ax = plt.subplots(figsize=(12, 6))\n"
            "for sym, df in dfs.items():\n"
            "    norm = df['close'] / df['close'].iloc[0]\n"
            "    ax.plot(df.index, norm, label=sym, linewidth=1.5)\n"
            "ax.set_title(\"4 指数归一化对比 (起点 = 1.0)\")\n"
            "ax.set_ylabel(\"Normalized Close\")\n"
            "ax.legend()\n"
            "ax.grid(True, alpha=0.3)\n"
            "plt.tight_layout()\n"
            "plt.show()"
        ),
        new_markdown_cell(
            "## 🎯 练习\n\n"
            "试着自己改代码:\n\n"
            "1. **改 lookback 周期**: 把 5 日累计改成 20 日累计\n"
            "2. **加更多 ticker**: 加 `XLK` (科技) 和 `XLE` (能源),看哪些板块涨得多\n"
            "3. **改 layer**: 把 `'indices'` 改成 `'sectors'`,看 11 GICS 行业\n"
            "4. **加 volume 图**: `ax2 = ax.twinx(); ax2.bar(df.index, df['volume'], alpha=0.3)`\n\n"
            "改完跑一遍,看输出怎么变。**这就是 self-analysis 的核心**: 改参数 → 看结果。"
        ),
    ]
    nb = new_notebook()
    nb["cells"] = cells
    nb["metadata"] = {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
    }
    return nb


def make_nb_02() -> dict:
    """02_attribution_custom.ipynb - 自定义 sector weights 归因"""
    cells = [
        new_markdown_cell(
            "# 📓 02 — 自定义 sector weights 跑归因\n\n"
            "**目标**: 学会用 `attribute_index()` 跑归因,并用自己的 weights 验证。\n\n"
            "**适合**: 想做\"如果我调整权重,归因结果怎么变\"分析的用户。\n\n"
            "---\n\n"
            "**默认 weights** 在 `config/sector_weights.json` 是 2026-Q2 近似值。\n"
            "本 notebook 演示怎么**临时覆盖**做 what-if 分析。"
        ),
        new_code_cell(
            "# 第 0 步: import (含 robust path 修复)\n"
            "import sys\n"
            "from pathlib import Path\n"
            "\n"
            "def _find_project_root():\n"
            "    cwd = Path.cwd()\n"
            "    for cand in [cwd, *cwd.parents]:\n"
            "        if (cand / 'src').is_dir() and (cand / 'config').is_dir():\n"
            "            return cand\n"
            "    return cwd\n"
            "\n"
            "PROJECT_ROOT = _find_project_root()\n"
            "sys.path.insert(0, str(PROJECT_ROOT))\n"
            "print(f\"Project root: {PROJECT_ROOT}\")\n"
            "\n"
            "import json\n"
            "from src.attribution import attribute_index, load_sector_weights, get_sector_returns"
        ),
        new_code_cell(
            "# 第 1 步: 看默认 weights (DIA / QQQ / RSP / QQQE × 11 GICS)\n"
            "# 注意: weights dict 里有 \"note\" (str) 字段,需要过滤\n"
            "default_w = load_sector_weights()\n"
            "for sym, weights in default_w.items():\n"
            "    if sym.startswith('_'):  # 跳过 _meta\n"
            "        continue\n"
            "    print(f\"\\n=== {sym} ===\")\n"
            "    # 只取数字 (sector weights),跳过 \"note\" 字符串\n"
            "    sector_weights = [(k, v) for k, v in weights.items() if isinstance(v, (int, float))]\n"
            "    sorted_w = sorted(sector_weights, key=lambda x: -x[1])\n"
            "    for sector, w in sorted_w[:5]:  # top 5\n"
            "        print(f\"  {sector:25s} {w*100:>5.1f}%\")"
        ),
        new_code_cell(
            "# 第 2 步: 用默认 weights 跑 QQQ 5 日归因\n"
            "r_default = attribute_index('QQQ', lookback_days=5)\n"
            "print(\"=== QQQ 5 日归因 (默认 weights) ===\")\n"
            "print(f\"  实际:    {r_default['actual_return_pct']:+.2f}%\")\n"
            "print(f\"  预测:    {r_default['predicted_return_pct']:+.2f}%\")\n"
            "print(f\"  残差:    {r_default['residual_pct']:+.2f}%\")\n"
            "print(f\"  Top 3 主升: \")\n"
            "sorted_c = sorted(r_default['sector_contributions_pct'].items(), key=lambda x: -x[1])\n"
            "for s, v in sorted_c[:3]:\n"
            "    print(f\"    {s:25s} {v:+.2f}%\")"
        ),
        new_code_cell(
            "# 第 3 步: 改 weights — QQQ 科技集中度假设 (XLK 40% → 50%)\n"
            "# 直接复算: sum(w * sector_return) - 不调 attribute_index (它读 config)\n"
            "# 注意: default_w['QQQ'] 里有 \"note\" 字符串,过滤掉\n"
            "qqq_default = {k: v for k, v in default_w['QQQ'].items() if isinstance(v, (int, float))}\n"
            "modified_w = qqq_default.copy()\n"
            "modified_w['XLK'] = 0.50  # 从默认 52% 提到 50%(看跟默认差不多)\n"
            "modified_w['XLY'] = qqq_default.get('XLY', 0.13) * 0.5  # 削减消费\n"
            "\n"
            "print(\"Modified QQQ weights:\")\n"
            "for s, w in sorted(modified_w.items(), key=lambda x: -x[1])[:5]:\n"
            "    print(f\"  {s:25s} {w*100:>5.1f}%\")"
        ),
        new_code_cell(
            "# 第 4 步: 用 modified weights 复算归因\n"
            "import pandas as pd\n"
            "from src.returns import compute_returns\n"
            "\n"
            "sector_rets = get_sector_returns('2024-07-01', '2026-07-10')\n"
            "qqq_returns = sector_rets['QQQ']\n"
            "sector_only = sector_rets.drop(columns=['DIA', 'QQQ', 'RSP', 'QQQE'])\n"
            "\n"
            "# 5 日窗口\n"
            "last_5d = sector_only.tail(5).sum()  # log returns 可加\n"
            "actual_5d = qqq_returns.tail(5).sum() * 100\n"
            "\n"
            "predicted_default = sum(\n"
            "    qqq_default.get(s, 0) * last_5d[s] for s in sector_only.columns\n"
            ") * 100\n"
            "predicted_modified = sum(\n"
            "    modified_w.get(s, 0) * last_5d[s] for s in sector_only.columns\n"
            ") * 100\n"
            "\n"
            "print(f\"=== QQQ 5 日归因 (XLK 50% what-if) ===\")\n"
            "print(f\"  实际:        {actual_5d:+.2f}%\")\n"
            "print(f\"  预测 (默认): {predicted_default:+.2f}%, 残差 {actual_5d - predicted_default:+.2f}%\")\n"
            "print(f\"  预测 (XLK 50%): {predicted_modified:+.2f}%, 残差 {actual_5d - predicted_modified:+.2f}%\")\n"
            "print(f\"\\n💡 改 weight 后,预测变化 {predicted_modified - predicted_default:+.2f}%\")\n"
            "print(f\"   这就是 what-if 分析: weight 改了,模型认为 QQQ 应该多涨/少涨多少\")"
        ),
        new_markdown_cell(
            "## 💡 为什么 manual 复算\n\n"
            "`attribute_index()` 当前**不接 weights_override 参数**。\n"
            "v0.5.0 Phase 4 完成后,下一个版本会加 `weights_override`,这样一行就能跑 what-if。\n\n"
            "**目前 workaround** (上面 cell 演示):\n"
            "1. 调 `get_sector_returns()` 拿 sector log returns\n"
            "2. 自己用 `sum(w * r)` 算 weighted return\n"
            "3. 对比默认 weights vs 修改 weights 的预测差\n\n"
            "**结果**: 不调 attribute.py,纯用公开函数做 what-if。"
        ),
        new_code_cell(
            "# 第 5 步: 多指数批量归因对比\n"
            "from src.attribution import attribute_all_indices\n"
            "\n"
            "all_r = attribute_all_indices(lookback_days=5)\n"
            "print(f\"{'index':6s} {'actual':>8s} {'predicted':>10s} {'residual':>9s} {'verdict':>12s}\")\n"
            "print(\"-\" * 50)\n"
            "for r in all_r:\n"
            "    abs_res = abs(r['residual_pct'])\n"
            "    verdict = 'ok' if abs_res < 0.5 else ('watch' if abs_res < 1.0 else 'large')\n"
            "    print(f\"{r['index']:6s} {r['actual_return_pct']:>+7.2f}% \"\n"
            "          f\"{r['predicted_return_pct']:>+9.2f}% \"\n"
            "          f\"{r['residual_pct']:>+8.2f}% {verdict:>12s}\")"
        ),
        new_markdown_cell(
            "## 🎯 练习\n\n"
            "1. **改 1 个 sector weight 跑 what-if**: 把 QQQ 的 XLK 从 40% → 35%,XLF 从 8% → 13%\n"
            "2. **加新 sector**: 如果要加 'semiconductor' 行业,怎么加?\n"
            "3. **跟 RSP 等权对比**: RSP 是等权,所有 sector 都是 1/11 = 9.09%。看残差对比"
        ),
    ]
    nb = new_notebook()
    nb["cells"] = cells
    nb["metadata"] = {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
    }
    return nb


def make_nb_03() -> dict:
    """03_pattern_match.ipynb - 自定义 forward return / pattern length"""
    cells = [
        new_markdown_cell(
            "# 📓 03 — 历史 pattern 匹配 + 自定义 forward return\n\n"
            "**目标**: 学会用 `find_similar_patterns()` 找历史相似 K 线,改参数看不同结果。\n\n"
            "**适合**: 想知道\"当前形态历史上后续 5/20/60 日怎么走\"的用户。\n\n"
            "---\n\n"
            "**默认参数**: 20d pattern length, top 10 matches, 5d forward。\n"
            "本 notebook 演示 3 种变体:\n"
            "1. **短 pattern (10d) + 长 forward (60d)**: 看\"最近 2 周形态\"后续 3 个月\n"
            "2. **长 pattern (60d) + 短 forward (5d)**: 看\"最近 3 个月形态\"后续 1 周\n"
            "3. **更严格匹配 (top 5)**: 只看最像的 5 个"
        ),
        new_code_cell(
            "# 第 0 步: import (含 robust path 修复)\n"
            "import sys\n"
            "from pathlib import Path\n"
            "\n"
            "def _find_project_root():\n"
            "    cwd = Path.cwd()\n"
            "    for cand in [cwd, *cwd.parents]:\n"
            "        if (cand / 'src').is_dir() and (cand / 'config').is_dir():\n"
            "            return cand\n"
            "    return cwd\n"
            "\n"
            "PROJECT_ROOT = _find_project_root()\n"
            "sys.path.insert(0, str(PROJECT_ROOT))\n"
            "print(f\"Project root: {PROJECT_ROOT}\")\n"
            "\n"
            "from src.patterns import find_similar_patterns"
        ),
        new_code_cell(
            "# 第 1 步: QQQ 默认 20d pattern × 5d forward\n"
            "r_default = find_similar_patterns('QQQ', pattern_length=20, n_matches=10, forecast_horizon=5)\n"
            "print(\"=== QQQ 默认 (20d × 5d fwd × top 10) ===\")\n"
            "for k, v in r_default.items():\n"
            "    if isinstance(v, (int, float, str)):\n"
            "        print(f\"  {k:25s} {v}\")"
        ),
        new_code_cell(
            "# 第 2 步: 短 pattern 长 forward (10d × 60d fwd × top 10)\n"
            "r_short = find_similar_patterns('QQQ', pattern_length=10, n_matches=10, forecast_horizon=60)\n"
            "print(\"=== QQQ 短 pattern 长 forward (10d × 60d) ===\")\n"
            "print(f\"  avg forward:    {r_short['avg_forward_return']:+.2f}%\")\n"
            "print(f\"  win rate:       {r_short['win_rate']:.0%}\")\n"
            "print(f\"  max forward:    {r_short['max_forward']:+.2f}%\")\n"
            "print(f\"  min forward:    {r_short['min_forward']:+.2f}%\")"
        ),
        new_code_cell(
            "# 第 3 步: 4 指数 × 3 种 pattern 配置 对比\n"
            "configs = [\n"
            "    (\"短 10d × 5d\",  dict(pattern_length=10, n_matches=10, forecast_horizon=5)),\n"
            "    (\"中 20d × 5d\",  dict(pattern_length=20, n_matches=10, forecast_horizon=5)),\n"
            "    (\"长 60d × 20d\", dict(pattern_length=60, n_matches=10, forecast_horizon=20)),\n"
            "]\n"
            "print(f\"{'config':18s} {'symbol':6s} {'avg':>7s} {'win':>6s} {'max':>7s} {'min':>7s}\")\n"
            "print(\"-\" * 60)\n"
            "for name, cfg in configs:\n"
            "    for sym in ['DIA', 'QQQ', 'RSP', 'QQQE']:\n"
            "        r = find_similar_patterns(sym, **cfg)\n"
            "        print(f\"{name:18s} {sym:6s} {r['avg_forward_return']:>+6.2f}% \"\n"
            "              f\"{r['win_rate']:>5.0%} {r['max_forward']:>+6.2f}% {r['min_forward']:>+6.2f}%\")\n"
            "    print()"
        ),
        new_code_cell(
            "# 第 4 步: 严格匹配 (top 5) 看最像的\n"
            "r_top5 = find_similar_patterns('QQQ', pattern_length=20, n_matches=5, forecast_horizon=5)\n"
            "print(\"=== QQQ 严格匹配 (top 5) ===\")\n"
            "print(f\"  avg forward:    {r_top5['avg_forward_return']:+.2f}%\")\n"
            "print(f\"  win rate:       {r_top5['win_rate']:.0%}\")\n"
            "print(f\"\\n  top_matches: \")\n"
            "for i, m in enumerate(r_top5['top_matches'][:5], 1):\n"
            "    print(f\"    {i}. start {m['start_date']}, \"\n"
            "          f\"corr {m['correlation']:.3f}, \"\n"
            "          f\"fwd {m['forward_return']*100:+.2f}%\")"
        ),
        new_markdown_cell(
            "## 🎯 练习\n\n"
            "1. **找矛盾配置**: 哪种配置下 4 指数的 win rate 差距最大?最大多少?\n"
            "2. **layer 切换**: 改 `'indices'` 到 `'sectors'`,看 11 GICS 行业的 pattern 匹配\n"
            "3. **forecast_horizon = 1**: 看明天涨的概率,跟 5d 差多少?\n"
            "4. **threshold 过滤**: 只看相关性 > 0.9 的 matches,样本少但更准"
        ),
    ]
    nb = new_notebook()
    nb["cells"] = cells
    nb["metadata"] = {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
    }
    return nb


def main() -> int:
    nb_dir = PROJECT_ROOT / "notebooks"
    nb_dir.mkdir(parents=True, exist_ok=True)

    notebooks = {
        "01_load_and_explore.ipynb": make_nb_01(),
        "02_attribution_custom.ipynb": make_nb_02(),
        "03_pattern_match.ipynb": make_nb_03(),
    }

    print("=" * 72)
    print(f"us-stock-causal v0.5.0 - sample notebook generator (Phase 4 P4-3)")
    print(f"Output dir: {nb_dir}")
    print("=" * 72)

    for fname, nb in notebooks.items():
        path = nb_dir / fname
        nbf.write(nb, str(path))
        n_cells = len(nb["cells"])
        n_code = sum(1 for c in nb["cells"] if c["cell_type"] == "code")
        n_md = sum(1 for c in nb["cells"] if c["cell_type"] == "markdown")
        size_kb = path.stat().st_size / 1024
        print(f"  ✅ {fname:38s} {n_cells:>2d} cells ({n_code} code + {n_md} md)  {size_kb:.1f} KB")

    print(f"\n  Total: {len(notebooks)} notebooks")
    print(f"  启动: python examples/notebook.py")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
