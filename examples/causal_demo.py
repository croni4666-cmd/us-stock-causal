#!/usr/bin/env python3
"""
examples/causal_demo.py - Phase 9.0 POC demo

跑 1 个 do-calculus query + 1 个反事实 + 打印结果。

用法: python examples/causal_demo.py
"""
from __future__ import annotations

import sys
import warnings
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)
from pathlib import Path

# 让脚本能 import src/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.causal import (
    load_dag_config,
    load_dag_data,
    causal_query,
    counterfactual_query,
)


def main():
    print("=" * 70)
    print("Phase 9.0 POC: Pearl-style 因果分析")
    print("=" * 70)

    # 1. 加载 DAG + 数据
    cfg = load_dag_config()
    data = load_dag_data(cfg=cfg)
    print(f"\n数据: {len(data)} 个交易日, 范围 {data.index[0].date()} ~ {data.index[-1].date()}")
    print(f"节点: {list(data.columns)}")
    print(f"\nDAG: {cfg['dag_name']}")
    print(f"  7 节点 (3 macro + 4 指数), 12 边 (3 macro × 4 指数 direct edges)")

    # 2. L2 干预 query 1: TNX → QQQ
    print("\n" + "=" * 70)
    print("L2 干预 query #1: P(QQQ | do(TNX=实际+1%))")
    print("  问: 如果今天 10Y 国债 +1%, QQQ 涨多少?")
    print("=" * 70)
    eff1 = causal_query(treatment="TNX", outcome="QQQ", data=data, cfg=cfg)
    print(f"\nATE = {eff1.estimate:+.4f} (~{eff1.estimate*100:+.2f}% QQQ 日变化 / +1% TNX 日变化)")
    print(f"方法: {eff1.method}")
    print(f"样本: {eff1.n_obs} 个交易日")
    print(f"\n反驳测试:")
    for k, v in eff1.refutation.items():
        new = v.get("new_effect", v.get("error", "?"))
        print(f"  - {k}: new_effect={new}")

    # 3. L2 干预 query 2: VIX → QQQ (应该强负相关)
    print("\n" + "=" * 70)
    print("L2 干预 query #2: P(QQQ | do(VIX=实际+1%))")
    print("  问: 如果今天恐慌指数 +1%, QQQ 涨多少? (经济理论: 应为负)")
    print("=" * 70)
    eff2 = causal_query(treatment="VIX", outcome="QQQ", data=data, cfg=cfg)
    print(f"\nATE = {eff2.estimate:+.4f} (~{eff2.estimate*100:+.2f}% QQQ 日变化 / +1% VIX 日变化)")
    print(f"\n反驳测试:")
    for k, v in eff2.refutation.items():
        new = v.get("new_effect", v.get("error", "?"))
        print(f"  - {k}: new_effect={new}")

    # 4. L3 反事实: 选最近一个交易日
    print("\n" + "=" * 70)
    print("L3 反事实 query: 假设最近一天 VIX 不是实际值")
    print("=" * 70)
    last_date = str(data.index[-1].date())
    actual_vix = float(data.iloc[-1]["VIX"])
    # 假设 VIX 比实际低 5% (恐慌小, 应该利好 QQQ)
    cf_vix = actual_vix - 0.05  # -5% log return
    print(f"日期: {last_date}")
    print(f"实际 VIX log return: {actual_vix:+.4f} ({actual_vix*100:+.2f}%)")
    print(f"假设 VIX log return: {cf_vix:+.4f} ({cf_vix*100:+.2f}%)")
    print(f"  问: 如果 VIX 比实际低 5%, QQQ 会涨多少?")
    cf = counterfactual_query(
        date=last_date,
        treatment="VIX",
        outcome="QQQ",
        counterfactual_value=cf_vix,
        data=data,
        cfg=cfg,
    )
    print(f"\n实际 QQQ log return: {cf.actual_outcome:+.4f} ({cf.actual_outcome*100:+.2f}%)")
    print(f"反事实 QQQ log return: {cf.counterfactual_outcome:+.4f} ({cf.counterfactual_outcome*100:+.2f}%)")
    print(f"差值 (CF - actual): {cf.delta:+.4f} ({cf.delta*100:+.2f}%)")

    print("\n" + "=" * 70)
    print("Phase 9.0 POC done")
    print("=" * 70)


if __name__ == "__main__":
    main()
