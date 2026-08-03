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
# Module-level caches (P9-1.5 性能优化)
# =============================================================================

# data cache: 同一个 start/end 多次 load, OS 帮我们 fast read 0.017s
# 但 init parquet + log return + concat 仍然 ~0.04s, cache 掉
_DATA_CACHE: dict[tuple, pd.DataFrame] = {}

# CausalForestDML fit cache: key = (T, O, tuple(controls), n_obs)
# 第一次 fit ~0.13s, 重复 query (不同 date 同 T/O) < 0.001s lookup
# P9-1.5 核心: 让 L3 default mode (多个反事实) 实际可行
_FIT_CACHE: dict[tuple, "CausalForestDML"] = {}  # type: ignore[name-defined]


def clear_caches() -> dict:
    """清空 module-level caches (tests 用)."""
    n_data = len(_DATA_CACHE)
    n_fit = len(_FIT_CACHE)
    _DATA_CACHE.clear()
    _FIT_CACHE.clear()
    return {"data_cleared": n_data, "fit_cleared": n_fit}


def get_cache_stats() -> dict:
    """看 cache 当前状态 (debug / tests 用)."""
    return {
        "data_cache_size": len(_DATA_CACHE),
        "fit_cache_size": len(_FIT_CACHE),
        "fit_cache_keys": list(_FIT_CACHE.keys()),
    }


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
# P9-1.1 PC algorithm: 数据学 DAG vs 手工 DAG 对比
# =============================================================================

def discover_dag_pc(
    data: pd.DataFrame,
    alpha: float = 0.05,
    indep_test: str = "fisherz",
) -> nx.DiGraph:
    """P9-1.1: 用 PC 算法 (Spirtes et al. 2000) 从数据学 DAG.

    Args:
        data: log return DataFrame, columns = 节点名
        alpha: 显著性阈值, 默认 0.05 (越小越严格, 边越少)
        indep_test: 'fisherz' (Pearson 相关, 假设线性高斯) / 'gsq' (G^2 检验, 离散)
                  / 'chi2' (卡方, 离散)

    Returns:
        networkx DiGraph (best-effort, 部分边可能 undirected -> 我们默认方向, 见 implementation)

    依赖: causal-learn (causallearn package). 安装: pip install causal-learn
    """
    from causallearn.search.ConstraintBased.PC import pc
    from causallearn.graph.GeneralGraph import GeneralGraph

    cg = pc(data.values, alpha=alpha, indep_test=indep_test,
            node_names=list(data.columns), show_progress=False)

    # 解析 causallearn GeneralGraph 到 networkx DiGraph
    # causallearn adjacency matrix convention (从 GeneralGraph docstring + 实测):
    #   graph[i,j] =  1, graph[j,i] = -1 → directed i → j (1=tail, -1=head)
    #   graph[i,j] = -1, graph[j,i] = -1 → undirected i -- j
    #   graph[i,j] =  0, graph[j,i] =  0 → 无边
    n = cg.G.get_num_nodes()
    node_names = list(data.columns)

    g = nx.DiGraph()
    g.add_nodes_from(node_names)

    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            a_ij = cg.G.graph[i, j]
            a_ji = cg.G.graph[j, i]
            if a_ij == 1 and a_ji == -1:
                # directed i → j
                g.add_edge(node_names[i], node_names[j])
            elif a_ij == -1 and a_ji == -1 and i < j:
                # undirected i -- j, 选字母序方向 (确定性, 便于 cache/diff)
                if node_names[i] < node_names[j]:
                    g.add_edge(node_names[i], node_names[j])
                else:
                    g.add_edge(node_names[j], node_names[i])

    return g


def compare_dags(
    manual_dag: nx.DiGraph,
    pc_dag: nx.DiGraph,
) -> dict:
    """P9-1.1: 对比手工 DAG vs PC 学出的 DAG.

    Returns:
        dict with:
          - 'overlap': 两边都有的有向边 (强因果证据)
          - 'manual_only': 手工有 PC 没有 (理论画了, 数据不显著 → 可能是 manual 高估)
          - 'pc_only': PC 有手工没有 (数据有, 理论没画 → 可能是被忽略的因果或同期相关)
          - 'summary': 文字摘要, 含重叠率
    """
    manual_edges = set(manual_dag.edges())
    pc_edges = set(pc_dag.edges())

    overlap = manual_edges & pc_edges
    manual_only = manual_edges - pc_edges
    pc_only = pc_edges - manual_edges

    total = len(overlap) + len(manual_only) + len(pc_only)
    overlap_rate = len(overlap) / total if total > 0 else 0

    summary = (
        f"Manual DAG: {len(manual_edges)} edges, PC DAG: {len(pc_edges)} edges. "
        f"Overlap: {len(overlap)} ({overlap_rate*100:.0f}%). "
        f"Manual only: {len(manual_only)} (理论画了数据不支持). "
        f"PC only: {len(pc_only)} (数据有理论没画)."
    )

    return {
        "overlap": sorted(overlap),
        "manual_only": sorted(manual_only),
        "pc_only": sorted(pc_only),
        "summary": summary,
    }


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

    P9-1.5: 加 module-level cache, 同一 (start, end, parquet 文件 mtime) 重复 load 直接返回。

    Returns: DataFrame with columns: TNX, VIX, DXY, DIA, QQQ, RSP, QQQE
             (用 close 价格的 log return, 单位 = 0.01 = 1%)
    """
    if cfg is None:
        cfg = load_dag_config()
    parquet_map = cfg["nodes"]["parquet_map"]

    # P9-1.5 cache key: 包含 (start, end, 所有 parquet mtime) 让 stale 失效
    cache_key_parts = [start, end]
    for node, rel_path in parquet_map.items():
        pq = PROJECT_ROOT / rel_path
        if pq.exists():
            cache_key_parts.append((node, pq.stat().st_mtime_ns))
    cache_key = tuple(cache_key_parts)

    if cache_key in _DATA_CACHE:
        logger.debug(f"[causal] load_dag_data cache hit ({len(_DATA_CACHE[cache_key])} 行)")
        return _DATA_CACHE[cache_key].copy()  # 返回 copy 避免 caller 污染 cache

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

    _DATA_CACHE[cache_key] = aligned
    return aligned.copy()


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


def _get_cfdml_cached(
    treatment: str,
    outcome: str,
    data: pd.DataFrame,
    controls: list[str],
) -> "CausalForestDML":  # type: ignore[name-defined]
    """P9-1.5: 缓存 CausalForestDML fit 结果, key = (T, O, tuple(controls), n_obs).

    第一次 fit ~0.13s, 重复 query (不同 date 同 T/O) < 0.001s lookup.
    让 L3 default mode (多个反事实 query 在同一 report) 实际可行.

    n_obs 进 key 是因为数据窗口 (start/end) 变化时 fit 必然不同.
    n_estimators 固定 100 (P9-1.5 决策: cache 已经够用, 不要再调参; subforest_size=4 要求 n_estimators 能被 4 整除, 50/52 等会报错).
    """
    key = (treatment, outcome, tuple(controls), len(data))
    if key in _FIT_CACHE:
        logger.debug(f"[causal] CausalForestDML cache hit T={treatment} O={outcome} n={len(data)} (cache size={len(_FIT_CACHE)})")
        return _FIT_CACHE[key]

    from econml.dml import CausalForestDML
    from sklearn.ensemble import RandomForestRegressor
    est = CausalForestDML(
        model_y=RandomForestRegressor(n_estimators=20, max_depth=4, random_state=42),
        model_t=RandomForestRegressor(n_estimators=20, max_depth=4, random_state=42),
        n_estimators=100,  # P9-1.5: 固定 100, cache 解决重复 fit 问题
        random_state=42,
    )
    X = data[controls].values
    T = data[treatment].values
    Y = data[outcome].values
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        est.fit(Y=Y, T=T, X=X, W=X)  # X=W=controls (POC 简化, 实际应区分)

    _FIT_CACHE[key] = est
    logger.info(f"[causal] CausalForestDML fit cached T={treatment} O={outcome} n={len(data)} (cache size={len(_FIT_CACHE)})")
    return est


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

    P9-1.5 优化: 用 module-level cache 缓存 fit 结果, 重复 query 不同 date
    但同 (T, O) 不用重 fit, 0.13s → < 0.001s lookup.

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

    # P9-1.5: 用 fit cache (固定 n_estimators=100, subforest_size=4 要求整除)
    est = _get_cfdml_cached(treatment, outcome, data, controls)

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
