#!/usr/bin/env python3
"""Offline examples of associations and scenarios under a low-trust candidate DAG."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.causal import load_dag_config, load_dag_data, causal_query, counterfactual_query, load_dag_graph


def main():
    print('候选 DAG 默认低可信；因果尚未建立；模型数字不代表预测或命题为真的概率。')
    try:
        cfg = load_dag_config()
        data = load_dag_data(cfg=cfg)
        if data.empty:
            raise ValueError('no aligned observations')
        graph = load_dag_graph(cfg)
        print(f"DAG: {cfg.get('dag_name', 'candidate')}, {graph.number_of_nodes()} 节点, {graph.number_of_edges()} 边")
        print(f'数据: {len(data)} 行, {data.index[0].date()} ~ {data.index[-1].date()}')
        for treatment in ('TNX', 'VIX'):
            effect = causal_query(treatment=treatment, outcome='QQQ', data=data, cfg=cfg)
            print(f'\n候选图下的条件关联: {treatment} 与 QQQ；方向由数据估计')
            print(f'系数 = {effect.estimate:+.4f}；方法={effect.method}；样本={effect.n_obs}')
            # Both input and outcome are daily log returns: beta * .01 * 100 = beta.
            print(f'输入增量 +0.01 log return (+1 个对数百分点) 对应模型变化 {effect.estimate:+.2f} 个对数百分点')
            print(json.dumps(effect.to_dict()['epistemic_assessment'], ensure_ascii=False))
            print(f'稳健性诊断（不认证因果方向）: {effect.refutation}')
        target = str(data.index[-1].date())
        actual = float(data.iloc[-1]['VIX'])
        result = counterfactual_query(date=target, treatment='VIX', outcome='QQQ',
                                      counterfactual_value=actual-.05, data=data, cfg=cfg)
        print(f'\n模型情景: {target}，VIX 日对数变化相对观察值减去 .05；其他结构假设固定')
        print(f'观察 QQQ log return={result.actual_outcome:+.4f}；模型情景={result.counterfactual_outcome:+.4f}')
        print(f'模型差值={result.delta:+.4f} log return ({result.delta*100:+.2f} 个对数百分点)')
        print(json.dumps(result.to_dict()['epistemic_assessment'], ensure_ascii=False))
    except (ValueError, KeyError, FileNotFoundError) as error:
        print(f'[unavailable] {error}')
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
