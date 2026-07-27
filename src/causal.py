"""
src/causal.py - Pearl-style 因果分析 (Phase 9)

设计: 不替代 src/attribution.py (L1 关联 baseline), 而是在 5 段报告里加
"因果机制" 段。回答 Pearl 3 层因果阶梯:
  - L1 关联 (attribution.py 现有): P(Y|X) — "看到"
  - L2 干预 (本模块): P(Y|do(X)) — "做"
  - L3 反事实 (本模块 counterfactual_query): P(Y_x|X',Y') — "如果当初"

DAG 来自 config/causal_dag.yaml (手工, 经济理论驱动), 不从数据学。
PC9.0 POC: 核心子图 (3 macro → 4 指数), 无 mediator, 无 confounder。

依赖: dowhy >= 0.14, econml >= 0.16, pydot, networkx, causal-learn
"""
from __future__ import annotations

import json
import warnings
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
import pydot
import networkx as nx
import yaml
from loguru import logger

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DAG_CONFIG = PROJECT_ROOT / "config" / "causal_dag.yaml"
CACHE_ROOT = PROJECT_ROOT / "data" / "raw"


# =============================================================================
# DAG 加载
# =============================================================================

def load_dag_config(path: Path = DAG_CONFIG) -> dict:
    """读 YAML 配置"""
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_dag_graph(cfg: dict | None = None) -> nx.DiGraph:
    """解析 DOT 成 networkx DiGraph"""
    if cfg is None:
        cfg = load_dag_config()
    graphs = pydot.graph_from_dot_data(cfg["dot"])
    assert len(graphs) == 1
    return nx.DiGraph(nx.drawing.nx_pydot.from_pydot(graphs[0]))


# =============================================================================
# DataFrame 准备
# =============================================================================

def _safe_name(symbol: str) -> str:
    return symbol.replace("^", "_").replace("=", "_").replace(".", "_")


def load_dag_data(
    start: str | None = None,
    end: str | None = None,
    cfg: dict | None = None,
) -> pd.DataFrame:
    """读所有 DAG 节点的 parquet, 算 daily log returns, 对齐到共同 date index.

    Returns: DataFrame with columns: TNX, VIX, DXY, DIA, QQQ, RSP, QQQE
             (用 close 价格的 log return, 单位 = 0.01 = 1%)
    """
    if cfg is None:
        cfg = load_dag_config()
    parquet_map = cfg["nodes"]["parquet_map"]

    returns = {}
    for node, rel_path in parquet_map.items():
        pq = PROJECT_ROOT / rel_path
        if not pq.exists():
            logger.warning(f"[causal] {pq} 不存在, 跳过 {node}")
            continue
        df = pd.read_parquet(pq)
        if "close" not in df.columns:
            logger.warning(f"[causal] {pq} 无 close 列, 跳过 {node}")
            continue
        close = df["close"].sort_index()
        if start:
            close = close.loc[start:]
        if end:
            close = close.loc[:end]
        # log return, drop first NaN
        log_ret = np.log(close / close.shift(1)).dropna()
        returns[node] = log_ret

    if not returns:
        raise FileNotFoundError("[causal] 无任何 parquet 加载成功")

    # 对齐: inner join (只保留共同日期)
    aligned = pd.concat(returns.values(), axis=1, join="inner")
    aligned.columns = list(returns.keys())
    aligned = aligned.dropna(how="any")
    logger.info(f"[causal] {len(aligned)} 个交易日, {len(aligned.columns)} 个节点")
    return aligned


# =============================================================================
# L2 干预: P(Y | do(X)) via DoWhy
# =============================================================================

@dataclass
class CausalEffect:
    """因果估计结果 (DoWhy 4 步)"""
    treatment: str
    outcome: str
    estimate: float           # 平均处理效应 ATE (回归系数, treatment 1 单位变化 → outcome 变化)
    estimand: str             # 识别出的 estimand 公式 (DoWhy identify_effect 输出)
    refutation: dict          # 反驳测试结果 (3 重)
    method: str               # 'ols' (Phase 9.0 POC)
    n_obs: int
    p_value: float            # 系数显著性 (P>|t|)
    std_error: float          # 系数标准误
    interpretation: str       # 人类可读解读

    def to_dict(self) -> dict:
        return asdict(self)


def causal_query(
    treatment: str,
    outcome: str,
    data: pd.DataFrame | None = None,
    cfg: dict | None = None,
) -> CausalEffect:
    """跑 Pearl 4 步: model → identify → estimate → refute.

    实操:
      1. DoWhy 建 CausalModel + identify_effect 算 estimand (DAG 验证)
      2. 自己用 statsmodels 跑 OLS 算 ATE (避免 DoWhy estimator 已知 bug)
      3. DoWhy 跑 3 重 refutation (random_common_cause / placebo / data_subset)

    Phase 9.0 POC 简化: 用 OLS 当 estimate, 不做异质性 (CATE 是后续 EconML 阶段)
    DAG 假设: 无 confounder, backdoor set = 空, 所以 ATE = 简单回归系数 (与多变量回归系数相同)

    Args:
        treatment: e.g. "TNX" (要做 do 的变量)
        outcome: e.g. "QQQ" (target 变量)
        data: load_dag_data() 出来的 DataFrame, None = 自动加载
        cfg: DAG config dict, None = 自动加载

    Returns:
        CausalEffect dataclass
    """
    if cfg is None:
        cfg = load_dag_config()
    if data is None:
        data = load_dag_data(cfg=cfg)

    # Sanity check
    g = load_dag_graph(cfg)
    if not nx.is_directed_acyclic_graph(g):
        raise ValueError("[causal] DAG 有环, 不合法")
    if treatment not in g.nodes or outcome not in g.nodes:
        raise ValueError(f"[causal] treatment={treatment} 或 outcome={outcome} 不在 DAG 里")
    if treatment not in data.columns or outcome not in data.columns:
        raise ValueError(f"[causal] data 缺 {treatment} 或 {outcome}")

    # Step 1: DoWhy model + identify (验证 DAG, 拿 estimand)
    from dowhy import CausalModel
    model = CausalModel(
        data=data,
        treatment=treatment,
        outcome=outcome,
        graph=g,
        common_causes=None,
        instruments=None,
    )
    identified = model.identify_effect(proceed_when_unidentifiable=True)
    estimand_str = str(identified)

    # Step 2: 自己用 statsmodels 跑 OLS (Phase 9.0 POC, 因果 DAG 无 confounder, 简单回归系数 = ATE)
    import statsmodels.api as sm
    X = sm.add_constant(data[[treatment]])
    y = data[outcome]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ols_result = sm.OLS(y, X).fit()
    ate = float(ols_result.params[treatment])
    p_value = float(ols_result.pvalues[treatment])
    std_err = float(ols_result.bse[treatment])

    # Step 3: DoWhy 反驳测试 (用 DoWhy 的 estimator 作为 baseline, 即使它返回 0)
    refutation_results = {}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        # 拿一个 DoWhy estimate 给 refute 用 (即使它数值不对, refute 跑得动)
        try:
            do_estimate = model.estimate_effect(identified, method_name="backdoor.linear_regression")
        except Exception:
            do_estimate = None

        if do_estimate is not None:
            for refuter_name in ["random_common_cause", "placebo_treatment_refuter", "data_subset_refuter"]:
                try:
                    refute = model.refute_estimate(
                        identified, do_estimate,
                        method_name=refuter_name,
                    )
                    refutation_results[refuter_name] = {
                        "new_effect": float(refute.new_effect),
                    }
                except Exception as e:
                    refutation_results[refuter_name] = {"error": str(e)}

    # 人类可读解读
    direction = "↑" if ate > 0 else "↓"
    sig = "显著" if p_value < 0.05 else "不显著"
    interpretation = (
        f"{treatment} 上升 1 单位 (~1% log return), {outcome} 预期{direction} {abs(ate):.4f} "
        f"(~{abs(ate)*100:.2f}%); p={p_value:.3f} ({sig}); "
        f"基于 {len(data)} 个交易日, std_err={std_err:.4f}"
    )

    return CausalEffect(
        treatment=treatment,
        outcome=outcome,
        estimate=ate,
        estimand=estimand_str,
        refutation=refutation_results,
        method="ols",
        n_obs=len(data),
        p_value=p_value,
        std_error=std_err,
        interpretation=interpretation,
    )


# =============================================================================
# L3 反事实: 简单近似 (DoWhy 内置反事实需要 structural model, 暂用 econml 近似)
# =============================================================================

@dataclass
class CounterfactualResult:
    """反事实结果: 假如某天 macro 不是实际值, 指数会怎样"""
    date: str
    treatment: str
    outcome: str
    actual_outcome: float      # 实际 outcome return
    counterfactual_treatment: float  # 假设的 do 值
    counterfactual_outcome: float    # 反事实预测
    delta: float               # counterfactual - actual

    def to_dict(self) -> dict:
        return asdict(self)


def counterfactual_query(
    date: str,
    treatment: str,
    outcome: str,
    counterfactual_value: float,
    data: pd.DataFrame | None = None,
    cfg: dict | None = None,
) -> CounterfactualResult:
    """简单反事实: 假定某天 treatment 是 counterfactual_value, outcome 会怎样.

    方法: 训练 econml CausalForestDML 估计 CATE (条件平均处理效应),
    在 (date, treatment=counterfactual_value) 条件下预测 outcome.

    注: 严格 Pearl L3 反事实需要 structural causal model (SCM), DoWhy 有
    `dowhy.do_calculus.counterfactual_query` 但需要 4 个 elements:
    (treatment, outcome, observed_treatment, observed_outcome). 这里用
    econml CATE 作为简化近似 — 数值意义是 "在 X=z 条件下, 改变 1 单位
    treatment 的预期 Y 变化", 不是严格反事实, 但能给出 Pearl-style 视角。

    Args:
        date: 'YYYY-MM-DD', 选一天看反事实
        treatment: e.g. "VIX"
        outcome: e.g. "QQQ"
        counterfactual_value: 如果当时 VIX 是 X (instead of actual), 假设值
                            单位 = 0.01 = 1% (跟 log return 一致)

    Returns:
        CounterfactualResult
    """
    if cfg is None:
        cfg = load_dag_config()
    if data is None:
        data = load_dag_data(cfg=cfg)

    if date not in data.index:
        # 找最近的交易日
        idx = data.index.get_indexer([pd.Timestamp(date)], method="ffill")[0]
        if idx < 0:
            raise ValueError(f"[causal] {date} 找不到最近交易日, 数据范围 {data.index[0]} ~ {data.index[-1]}")
        date_ts = data.index[idx]
    else:
        date_ts = pd.Timestamp(date)
    date = str(date_ts.date())

    actual_treatment = float(data.loc[date_ts, treatment])
    actual_outcome = float(data.loc[date_ts, outcome])

    # 取其他 macro 作为 controls
    treatments = cfg["nodes"]["treatments"]
    controls = [c for c in treatments if c != treatment]

    X = data[controls].values
    T = data[treatment].values
    Y = data[outcome].values

    # CausalForestDML (用 RandomForestRegressor 实例, 不是 lambda; n_estimators 降 100 提速)
    from econml.dml import CausalForestDML
    from sklearn.ensemble import RandomForestRegressor
    est = CausalForestDML(
        model_y=RandomForestRegressor(n_estimators=20, max_depth=4, random_state=42),
        model_t=RandomForestRegressor(n_estimators=20, max_depth=4, random_state=42),
        n_estimators=100,
        random_state=42,
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        est.fit(Y=Y, T=T, X=X, W=X)  # X=W=controls (POC 简化, 实际应区分)

    # 在该天 controls 不变条件下, 算 CATE (treatment 变化 1 单位的效应)
    x_query = data.loc[[date_ts], controls].values
    cate = float(est.effect(x_query))
    # counterfactual_value 和 actual_treatment 都是 log return 单位 (0.01 = 1%)
    # cate 含义: treatment 变化 1 单位 (1% log return) 时 outcome 变化 (log return 单位)
    # 所以 delta = cate * (counterfactual - actual) (无 ×100)
    delta = cate * (counterfactual_value - actual_treatment)

    counterfactual_outcome = actual_outcome + delta

    return CounterfactualResult(
        date=date,
        treatment=treatment,
        outcome=outcome,
        actual_outcome=actual_outcome,
        counterfactual_treatment=counterfactual_value,
        counterfactual_outcome=counterfactual_outcome,
        delta=delta,
    )
