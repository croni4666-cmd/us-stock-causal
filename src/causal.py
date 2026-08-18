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

# P9-1.3: DoWhy gcm InvertibleSCM fit cache
# 第一次 build + fit ~5ms, 重复 query < 0.001s lookup
# key = (n_nodes, n_edges, n_obs, sorted_node_names) — DAG 变或数据窗口变 invalidate
_SCM_CACHE: dict[tuple, "gcm.InvertibleStructuralCausalModel"] = {}  # type: ignore[name-defined]

# P9-1.5.5: L2 refutation cache (random_common_cause 等)
# 每重 ~10s, 默认 1 重省 ~18s vs 旧 3 重
# key = (T, O, n_obs, n_refutations)
_REFUTE_CACHE: dict[tuple, dict] = {}

# v0.9.5 RC1 prep (P10-1 性能优化): causal_query 函数级 cache
# 缓存整次查询结果 (ATE + refutation + estimand), 跨调用复用
# 1st call ~0.94s (OLS + DoWhy build), 2nd call < 5ms
# key = (treatment, outcome, n_refutations, refute_method, n_obs)
_QUERY_CACHE: dict[tuple, "CausalEffect"] = {}  # type: ignore[name-defined]

# v0.9.5 RC1 prep (P10-1 性能优化): cate_heterogeneity 函数级 cache
# 缓存整次异质性结果, 跨调用复用 (1st ~1.7s, 2nd < 5ms)
# key = (treatment, outcome, heterogeneity_var, n_quantiles, n_obs)
_CATE_CACHE: dict[tuple, list[dict]] = {}


def clear_caches() -> dict:
    """清空 module-level caches (tests 用)."""
    n_data = len(_DATA_CACHE)
    n_fit = len(_FIT_CACHE)
    n_scm = len(_SCM_CACHE)
    n_refute = len(_REFUTE_CACHE)
    n_query = len(_QUERY_CACHE)
    n_cate = len(_CATE_CACHE)
    n_pc = len(_PC_CACHE)
    n_graph = len(_GRAPH_CACHE)
    _DATA_CACHE.clear()
    _FIT_CACHE.clear()
    _SCM_CACHE.clear()
    _REFUTE_CACHE.clear()
    _QUERY_CACHE.clear()
    _CATE_CACHE.clear()
    _PC_CACHE.clear()
    _GRAPH_CACHE.clear()
    return {"data_cleared": n_data, "fit_cleared": n_fit, "scm_cleared": n_scm, "refute_cleared": n_refute,
            "query_cleared": n_query, "cate_cleared": n_cate, "pc_cleared": n_pc, "graph_cleared": n_graph}


def get_cache_stats() -> dict:
    """看 cache 当前状态 (debug / tests 用)."""
    return {
        "data_cache_size": len(_DATA_CACHE),
        "fit_cache_size": len(_FIT_CACHE),
        "scm_cache_size": len(_SCM_CACHE),
        "refute_cache_size": len(_REFUTE_CACHE),
        "query_cache_size": len(_QUERY_CACHE),
        "cate_cache_size": len(_CATE_CACHE),
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
    """解析 DOT 成 networkx DiGraph

    v0.7.5: 加 module-level cache (Pydot 解析 35 节点 ~375ms, cache hit ~0ms)
    - key = yaml mtime + dot 串前 100 chars (cfg 改时 invalidate)
    - 跨 function 共享 (load_dag_data / causal_query / counterfactual_query / discover_dag_pc 同一 process 都用)
    """
    if cfg is None:
        cfg = load_dag_config()
    # v0.7.5 cache key: 用 mtime (DAG config 改时 invalidate)
    import hashlib
    cache_key = hashlib.md5(cfg["dot"].encode("utf-8")).hexdigest()[:16]
    if cache_key in _GRAPH_CACHE:
        return _GRAPH_CACHE[cache_key]
    graphs = pydot.graph_from_dot_data(cfg["dot"])
    assert len(graphs) == 1
    g = nx.DiGraph(nx.drawing.nx_pydot.from_pydot(graphs[0]))
    _GRAPH_CACHE[cache_key] = g
    return g


# v0.7.5: load_dag_graph cache (Pydot 解析慢)
_GRAPH_CACHE: dict[str, nx.DiGraph] = {}


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

    # v0.8.0: date-based cache (P9-1.1 PC algorithm 47 节点 ~1.5s 慢, 同一天 re-run 直接返)
    # key = (date, alpha, data shape, data mtime hash) — data 改时 invalidate
    import hashlib
    from datetime import date as _date
    data_hash = hashlib.md5(pd.util.hash_pandas_object(data, index=True).values.tobytes()).hexdigest()[:16]
    cache_key = (_date.today(), alpha, data.shape, data_hash)
    if cache_key in _PC_CACHE:
        logger.debug(f"[causal] PC algorithm cache hit (key={cache_key})")
        return _PC_CACHE[cache_key]

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

    # v0.8.0: 写 PC cache (date-based, 同一天 re-run 0s)
    _PC_CACHE[cache_key] = g
    return g


# v0.8.0: PC algorithm date-based cache (47 节点 ~1.5s, cache hit 0s)
_PC_CACHE: dict[tuple, nx.DiGraph] = {}


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


# v0.6.9l: P9-1.5.5 升级 — statsmodels OLS 路径 (替代 DoWhy refutation, 5-10x 更快)
# DoWhy refutation 跑 N 次 full causal model (~10s/重, 21 节点 175s)
# statsmodels OLS refutation: 用 OLS 重算 ATE (5-50ms/重, 21 节点 < 5s 总)
# 3 重覆盖 (跟 DoWhy 一致):
#   - random_common_cause: 加 unobserved confounder noise → 重算 OLS
#   - placebo_treatment_refuter: 把 treatment shuffle → OLS ATE 应 ≈ 0
#   - data_subset_refuter: 80% sub-sample → OLS ATE 应跟原 ATE 接近
def _refute_with_ols(
    treatment: str,
    outcome: str,
    data: pd.DataFrame,
    g: "nx.DiGraph",  # type: ignore[name-defined]
    original_ate: float,
    n_refutations: int,
    rng_seed: int = 42,
) -> dict:
    """v0.6.9l (P9-1.5.5 升级): statsmodels OLS 路径替代 DoWhy refutation.

    实测 21 节点 135 边: ~50ms 总 (vs DoWhy 175s, 3500x 加速)
    跟 DoWhy 3 重一一对应 (random_common_cause / placebo / data_subset)
    用 OLS 简单回归重算 ATE, 不跑 full causal model
    """
    import statsmodels.api as sm
    import numpy as np
    rng = np.random.default_rng(rng_seed)
    refuter_priority = {
        1: ["random_common_cause"],
        2: ["random_common_cause", "placebo_treatment_refuter"],
        3: ["random_common_cause", "placebo_treatment_refuter", "data_subset_refuter"],
    }
    refuter_names = refuter_priority.get(n_refutations, refuter_priority[3])
    result = {}

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for refuter_name in refuter_names:
            try:
                if refuter_name == "random_common_cause":
                    # 加 unobserved confounder noise (Gaussian N(0, σ)) 跟 T/Y 都相关
                    # 重算 OLS (T, confounder) → Y
                    confounder = rng.standard_normal(len(data)) * 0.5
                    X = sm.add_constant(data[[treatment]].assign(confounder=confounder))
                    ols_res = sm.OLS(data[outcome], X).fit()
                    new_ate = float(ols_res.params[treatment])
                elif refuter_name == "placebo_treatment_refuter":
                    # 把 treatment 随机化 (shuffle) → ATE 应 ≈ 0
                    placebo_t = rng.permutation(data[treatment].values)
                    X = sm.add_constant(pd.Series(placebo_t, index=data.index, name=treatment))
                    ols_res = sm.OLS(data[outcome], X).fit()
                    new_ate = float(ols_res.params[treatment])
                elif refuter_name == "data_subset_refuter":
                    # 80% sub-sample → ATE 应跟原 ATE 接近
                    subset = data.sample(frac=0.8, random_state=rng_seed)
                    X = sm.add_constant(subset[[treatment]])
                    ols_res = sm.OLS(subset[outcome], X).fit()
                    new_ate = float(ols_res.params[treatment])
                else:
                    continue
                result[refuter_name] = {"new_effect": new_ate}
            except Exception as e:
                result[refuter_name] = {"error": str(e)}

    return result


def _get_refutation_cached(
    treatment: str,
    outcome: str,
    data: pd.DataFrame,
    g: "nx.DiGraph",  # type: ignore[name-defined]
    n_refutations: int,
) -> dict:
    """P9-1.5.5 (L2 性能优化): 缓存 refutation 结果.

    实测每重 ~10s (random_common_cause 10.47s + placebo 8.55s + data_subset 8.90s),
    3 重 = 28s. 默认降到 1 重 (random_common_cause) 省 ~18s.

    Cache key = (T, O, n_obs, n_refutations): 同 T, O 数据不变 → cache hit.

    v0.6.9k (P9-1.5.5 升级): n_refutations=0 直接返空 dict (跳过 refutation).
    """
    if n_refutations == 0:
        # v0.6.9k: 大 DAG auto-fallback 0 重, 跳过 refutation
        return {}
    key = (treatment, outcome, len(data), n_refutations)
    if key in _REFUTE_CACHE:
        logger.debug(f"[causal] refutation cache hit T={treatment} O={outcome} (n_refutations={n_refutations}, cache size={len(_REFUTE_CACHE)})")
        return _REFUTE_CACHE[key]

    from dowhy import CausalModel
    model = CausalModel(
        data=data, treatment=treatment, outcome=outcome,
        graph=g, common_causes=None, instruments=None,
    )
    identified = model.identify_effect(proceed_when_unidentifiable=True)
    try:
        do_estimate = model.estimate_effect(identified, method_name="backdoor.linear_regression")
    except Exception:
        do_estimate = None

    if do_estimate is None:
        result = {}
    else:
        # P9-1.5.5: 默认 1 重 (random_common_cause); 3 重全跑传 n_refutations=3
        # 按耗时排序 (从快到慢) 让最短的先跑, 失败时已跑的仍记录
        refuter_priority = {
            1: ["random_common_cause"],
            2: ["random_common_cause", "placebo_treatment_refuter"],
            3: ["random_common_cause", "placebo_treatment_refuter", "data_subset_refuter"],
        }
        refuter_names = refuter_priority.get(n_refutations, refuter_priority[3])

        result = {}
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            for refuter_name in refuter_names:
                try:
                    refute = model.refute_estimate(identified, do_estimate, method_name=refuter_name)
                    result[refuter_name] = {"new_effect": float(refute.new_effect)}
                except Exception as e:
                    result[refuter_name] = {"error": str(e)}

    _REFUTE_CACHE[key] = result
    logger.info(f"[causal] refutation cached T={treatment} O={outcome} n_refutations={n_refutations} ({len(result)} refutations done, cache size={len(_REFUTE_CACHE)})")
    return result


# v0.6.9k: P9-1.5.5 升级 — 节点数 ≥ 20 触发 L2 refutation 自动 fallback 到 0 重
# 21 节点 1 重 refutation 实测 175s 性能爆降 30x (vs 18 节点 ~6s), 远超 60s daily cron budget.
# 0 重 fallback: 跳过 refutation, 但 OLS ATE 仍算 (P9-1.5.5 默认 1 重降级 0 重, ~6s 总).
# - hobbyist 1-2 次手补 OK, daily cron 不能再 60s+
# - 严格审稿场景传 causal_query(..., n_refutations=3) 仍跑全 3 重
LARGE_DAG_THRESHOLD = 20


def causal_query(
    treatment: str,
    outcome: str,
    data: pd.DataFrame | None = None,
    cfg: dict | None = None,
    n_refutations: int = 1,
    auto_reduce: bool = True,
    refute_method: str = "auto",
) -> CausalEffect:
    """跑 Pearl 4 步: model → identify → estimate → refute.

    实操:
      1. DoWhy 建 CausalModel + identify_effect 算 estimand (DAG 验证)
      2. 自己用 statsmodels 跑 OLS 算 ATE (避免 DoWhy estimator 已知 bug)
      3. 跑 n_refutations 重 refutation (默认 OLS 路径, 大 DAG auto-fallback 0 重)

    P9-1.5.5 性能优化 (v0.6.9k/l 实测):
      - L2 实际瓶颈 = DoWhy 3 重 refutation = 28s (18 节点, random 10.5s + placebo 8.5s + data_subset 8.9s)
      - 21 节点 DoWhy 1 重 = 175s 性能爆降 30x, 不实用
      - v0.6.9k: 节点 ≥ LARGE_DAG_THRESHOLD=20 auto-fallback 0 重, 21 节点 ~3.3s
      - v0.6.9l: OLS 路径 (refute_method='ols') 21 节点 1 重 ~50ms, 3 重 ~150ms
        (3500x 加速 vs DoWhy 175s), 保留 1 重 / 3 重 refutation 验证
      - 加 _REFUTE_CACHE: 重复 query (T, O) 走 cache hit, 0s

    refute_method 选型:
      - 'auto' (默认): < 20 节点用 DoWhy (P9-1.5.5 默认行为), ≥ 20 节点用 OLS (新路径, 3500x 加速)
      - 'ols': 强制 statsmodels OLS 路径 (~50ms/重, 3 重 < 200ms, 任意节点数)
      - 'dowhy': 强制 DoWhy refutation (审稿场景, 慢但标准化)

    Phase 9.0 POC 简化: 用 OLS 当 estimate, 不做异质性 (CATE 是后续 EconML 阶段)
    DAG 假设: 无 confounder, backdoor set = 空, 所以 ATE = 简单回归系数 (与多变量回归系数相同)

    Args:
        treatment: e.g. "TNX" (要做 do 的变量)
        outcome: e.g. "QQQ" (target 变量)
        data: load_dag_data() 出来的 DataFrame, None = 自动加载
        cfg: DAG config dict, None = 自动加载
        n_refutations: 跑几重 refutation. P9-1.5.5 默认 1 (只 random_common_cause);
                     3 是 v0.6.9 老默认 (3 重全跑); 0 是 v0.6.9k 跳过 refutation
        auto_reduce: True (默认) 节点数 ≥ LARGE_DAG_THRESHOLD 自动 fallback n_refutations=0
        refute_method: 'auto' / 'ols' / 'dowhy'

    Returns:
        CausalEffect dataclass
    """
    if cfg is None:
        cfg = load_dag_config()
    if data is None:
        data = load_dag_data(cfg=cfg)

    # v0.9.5 RC1 prep (P10-1 性能优化): function-level _QUERY_CACHE
    # 缓存整次查询结果 (ATE + refutation + estimand), 跨调用复用
    # 1st call ~0.94s (OLS + DoWhy build), 2nd call < 5ms
    # key = (treatment, outcome, n_refutations, refute_method, len(data))
    _qk = (treatment, outcome, n_refutations, refute_method, len(data))
    if _qk in _QUERY_CACHE:
        logger.debug(f"[causal] causal_query cache hit T={treatment} O={outcome} (cache size={len(_QUERY_CACHE)})")
        return _QUERY_CACHE[_qk]

    # Sanity check
    g = load_dag_graph(cfg)
    if not nx.is_directed_acyclic_graph(g):
        raise ValueError("[causal] DAG 有环, 不合法")
    if treatment not in g.nodes or outcome not in g.nodes:
        raise ValueError(f"[causal] treatment={treatment} 或 outcome={outcome} 不在 DAG 里")
    if treatment not in data.columns or outcome not in data.columns:
        raise ValueError(f"[causal] data 缺 {treatment} 或 {outcome}")

    n_nodes = g.number_of_nodes()
    # v0.6.9l: auto 选型 — 大 DAG 默认用 OLS (3500x 加速), 保留 1 重 / 3 重 refutation 验证
    if refute_method == "auto":
        if n_nodes >= LARGE_DAG_THRESHOLD:
            refute_method = "ols"  # 大 DAG: OLS 路径 (跟 n_refutations=0 一样快)
        else:
            refute_method = "dowhy"  # 小 DAG: DoWhy (默认行为, 标准化)
    if refute_method not in ("ols", "dowhy"):
        raise ValueError(f"[causal] refute_method={refute_method!r} 不支持, 用 'auto' / 'ols' / 'dowhy'")

    # v0.6.9k: 大 DAG + DoWhy auto-fallback 0 重 (DoWhy 路径 21 节点 175s 不可用)
    if auto_reduce and refute_method == "dowhy" and n_nodes >= LARGE_DAG_THRESHOLD and n_refutations > 0:
        logger.warning(
            f"[causal] DAG {n_nodes} 节点 + DoWhy refutation, auto-fallback n_refutations {n_refutations} → 0. "
            f"传 refute_method='ols' 保留 refutation 验证 (推荐) 或 auto_reduce=False 强制跑 (审稿场景)"
        )
        n_refutations = 0

    # Step 1+2: OLS (快, 0.001s) + Step 3: refutation (P9-1.5.5 加 cache)
    import statsmodels.api as sm
    X = sm.add_constant(data[[treatment]])
    y = data[outcome]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ols_result = sm.OLS(y, X).fit()
    ate = float(ols_result.params[treatment])
    p_value = float(ols_result.pvalues[treatment])
    std_err = float(ols_result.bse[treatment])

    # Refutation
    estimand_str = ""
    refutation_results = {}
    if n_refutations > 0:
        if refute_method == "ols":
            # v0.6.9l: OLS 路径, 21 节点 3 重 < 200ms, 保留 1 重 / 3 重 refutation 验证
            # 完全跳过 DoWhy (不需 identify estimand_str, 节省 1.4s build time)
            refutation_results = _refute_with_ols(treatment, outcome, data, g, ate, n_refutations)
            estimand_str = f"Pearl L2 (OLS refutation, {n_refutations} 重)"
        else:
            # DoWhy 路径 (跟 v0.6.9f 一致, cache)
            from dowhy import CausalModel
            model = CausalModel(
                data=data, treatment=treatment, outcome=outcome,
                graph=g, common_causes=None, instruments=None,
            )
            identified = model.identify_effect(proceed_when_unidentifiable=True)
            estimand_str = str(identified)
            refutation_results = _get_refutation_cached(treatment, outcome, data, g, n_refutations)

    # 人类可读解读
    direction = "↑" if ate > 0 else "↓"
    sig = "显著" if p_value < 0.05 else "不显著"
    interpretation = (
        f"{treatment} 上升 1 单位 (~1% log return), {outcome} 预期{direction} {abs(ate):.4f} "
        f"(~{abs(ate)*100:.2f}%); p={p_value:.3f} ({sig}); "
        f"基于 {len(data)} 个交易日, std_err={std_err:.4f}"
    )

    result = CausalEffect(
        treatment=treatment,
        outcome=outcome,
        estimate=ate,
        estimand=estimand_str,
        refutation=refutation_results,
        method=f"ols_refute_{refute_method}" if n_refutations > 0 else "ols",
        n_obs=len(data),
        p_value=p_value,
        std_error=std_err,
        interpretation=interpretation,
    )
    _QUERY_CACHE[_qk] = result
    return result


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


def _get_scm_cached(
    g: "nx.DiGraph",  # type: ignore[name-defined]
    data: pd.DataFrame,
) -> "gcm.InvertibleStructuralCausalModel":  # type: ignore[name-defined]
    """P9-1.3: 缓存 dowhy.gcm.InvertibleStructuralCausalModel fit 结果.

    第一次 build + fit ~5ms, 重复 query < 0.001s lookup.
    key = (n_nodes, n_edges, n_obs) — 当 DAG 变化或数据窗口变化时 invalidate.
    """
    key = (g.number_of_nodes(), g.number_of_edges(), len(data), tuple(sorted(g.nodes())))
    if key in _SCM_CACHE:
        logger.debug(f"[causal] SCM cache hit (cache size={len(_SCM_CACHE)})")
        return _SCM_CACHE[key]

    import dowhy.gcm as gcm
    from sklearn.linear_model import LinearRegression

    scm = gcm.InvertibleStructuralCausalModel(g)
    for node in g.nodes:
        parents = list(g.predecessors(node))
        if parents:
            # 有 parent: AdditiveNoiseModel + LinearRegression (Y = f(X) + N)
            scm.set_causal_mechanism(node, gcm.AdditiveNoiseModel(
                prediction_model=gcm.ml.SklearnRegressionModel(LinearRegression()),
            ))
        else:
            # Root node: 用 EmpiricalDistribution 当 noise distribution
            scm.set_causal_mechanism(node, gcm.EmpiricalDistribution())

    gcm.fit(scm, data)
    _SCM_CACHE[key] = scm
    logger.info(f"[causal] SCM fit cached (n_nodes={g.number_of_nodes()}, n_obs={len(data)}, cache size={len(_SCM_CACHE)})")
    return scm


def _counterfactual_query_econml(
    date_ts: pd.Timestamp,
    treatment: str,
    outcome: str,
    counterfactual_value: float,
    data: pd.DataFrame,
    cfg: dict,
) -> CounterfactualResult:
    """P9-1.5: EconML CausalForestDML 近似 L3 (保留作对照, 当前不在主路径用).

    数值含义: CATE (在 X=z 条件下, 改变 1 单位 treatment 的预期 Y 变化) × (cf - actual).
    不是严格 Pearl L3, 是 linear approximation.
    """
    actual_treatment = float(data.loc[date_ts, treatment])
    actual_outcome = float(data.loc[date_ts, outcome])

    treatments = cfg["nodes"]["treatments"]
    controls = [c for c in treatments if c != treatment]

    est = _get_cfdml_cached(treatment, outcome, data, controls)

    x_query = data.loc[[date_ts], controls].values
    cate = float(est.effect(x_query))
    delta = cate * (counterfactual_value - actual_treatment)
    counterfactual_outcome = actual_outcome + delta

    return CounterfactualResult(
        date=str(date_ts.date()),
        treatment=treatment,
        outcome=outcome,
        actual_outcome=actual_outcome,
        counterfactual_treatment=counterfactual_value,
        counterfactual_outcome=counterfactual_outcome,
        delta=delta,
    )


def _counterfactual_query_scm(
    date_ts: pd.Timestamp,
    treatment: str,
    outcome: str,
    counterfactual_value: float,
    data: pd.DataFrame,
    cfg: dict,
) -> CounterfactualResult:
    """P9-1.3: 严格 Pearl L3 用 DoWhy gcm InvertibleStructuralCausalModel.

    Pearl 3-step:
      1. Abduction: 从 observed 推断 noise
      2. Action: do(X=counterfactual_value)
      3. Prediction: 预测反事实 outcome

    比 econml CATE 严格:
      - 用 DAG 结构 (每个节点只从 parents 学习)
      - 推断 exogenous noise (explanatory)
      - 不是线性近似, 是 Pearl 反事实

    性能: SCM fit ~5ms, query ~3ms, 重复 query 0.001s (cache)
    """
    import dowhy.gcm as gcm

    g = load_dag_graph(cfg)
    scm = _get_scm_cached(g, data)

    actual_treatment = float(data.loc[date_ts, treatment])
    actual_outcome = float(data.loc[date_ts, outcome])

    observed_row = data.loc[[date_ts]]
    # Counterfactual intervention: treatment 设为 counterfactual_value (绝对值, log return 单位)
    cf_samples = gcm.counterfactual_samples(
        causal_model=scm,
        interventions={treatment: (lambda x, val=counterfactual_value: val)},
        observed_data=observed_row,
    )

    counterfactual_outcome = float(cf_samples.iloc[0][outcome])
    delta = counterfactual_outcome - actual_outcome

    return CounterfactualResult(
        date=str(date_ts.date()),
        treatment=treatment,
        outcome=outcome,
        actual_outcome=actual_outcome,
        counterfactual_treatment=counterfactual_value,
        counterfactual_outcome=counterfactual_outcome,
        delta=delta,
    )


def counterfactual_query(
    date: str,
    treatment: str,
    outcome: str,
    counterfactual_value: float,
    data: pd.DataFrame | None = None,
    cfg: dict | None = None,
    method: str = "scm",
) -> CounterfactualResult:
    """P9-1.3: 严格 Pearl L3 反事实 (用 DoWhy gcm InvertibleStructuralCausalModel).

    Pearl 3-step 反事实:
      1. Abduction: 从 observed data 推断 exogenous noise (P(U | observed))
      2. Action: do(treatment=counterfactual_value), 修改 structural equation
      3. Prediction: 用新 treatment + 推断的 noise 算 outcome

    Args:
        date: 'YYYY-MM-DD', 选一天看反事实
        treatment: e.g. "VIX"
        outcome: e.g. "QQQ"
        counterfactual_value: **绝对值** (不是 delta), 单位 = 0.01 = 1% (跟 log return 一致)
                            e.g. 想 "VIX 比实际低 5%", 传 actual_vix - 0.05
        data, cfg: 可选, None = 自动 load
        method: "scm" (P9-1.3, 严格 Pearl L3, 默认) / "econml" (P9-1.5, CATE 近似, 保留作对照)

    Returns:
        CounterfactualResult

    性能 (实测 7 节点 512 交易日):
      - SCM: build + fit ~5ms, query ~3ms, 重复 query < 1ms (cache)
      - EconML: fit ~130ms (cached 重复 < 1ms), query ~15ms
      - **SCM 严格更快更准**, 是 P9-1.3 后的默认

    数值示例 (VIX 跌 5%, 即 intervention = actual - 0.05, 2026-07-31):
      - QQQ 实际 +0.65%, 反事实 +1.26% (delta +0.61%, 利好)
      - 符合经济理论: VIX 跌 → 风险偏好上升 → 指数涨
    """
    if cfg is None:
        cfg = load_dag_config()
    if data is None:
        data = load_dag_data(cfg=cfg)

    if date not in data.index:
        idx = data.index.get_indexer([pd.Timestamp(date)], method="ffill")[0]
        if idx < 0:
            raise ValueError(f"[causal] {date} 找不到最近交易日, 数据范围 {data.index[0]} ~ {data.index[-1]}")
        date_ts = data.index[idx]
    else:
        date_ts = pd.Timestamp(date)

    if method == "scm":
        return _counterfactual_query_scm(date_ts, treatment, outcome, counterfactual_value, data, cfg)
    elif method == "econml":
        return _counterfactual_query_econml(date_ts, treatment, outcome, counterfactual_value, data, cfg)
    else:
        raise ValueError(f"[causal] method={method!r} 不支持, 用 'scm' (默认, P9-1.3 严格 Pearl L3) 或 'econml' (P9-1.5 CATE 近似)")


def cate_heterogeneity(
    treatment: str,
    outcome: str,
    heterogeneity_var: str,
    n_quantiles: int = 3,
    data: pd.DataFrame | None = None,
    cfg: dict | None = None,
) -> list[dict]:
    """P9-1.4: 跨 sub-population 评估 CATE (treatment effect 异质性).

    经典用法: "VIX 跌 1% 对 QQQ 影响, 在牛市 (VIX 低) vs 熊市 (VIX 高) 不同"
    → 用 VIX 当 heterogeneity_var, 切 3 群 (low/mid/high), 每群算 CATE

    Args:
        treatment: e.g. "VIX"
        outcome: e.g. "QQQ"
        heterogeneity_var: e.g. "VIX" (按当前 VIX 水平分群, 评估 VIX 跌在不同 regime 下效果)
                          或 "DXY" / "TNX" / 任何 7 节点变量
        n_quantiles: 切 N 群 (default 3 = tertiles, 5 = quintiles)
        data, cfg: 可选, None = 自动 load

    Returns:
        list of {
            "quantile": int (0..n_quantiles-1, 0 = lowest),
            "label": "low_VIX" / "mid_VIX" / "high_VIX",
            "range": [low, high] (heterogeneity_var 实际范围),
            "cate": float (treatment effect on outcome, 在此 sub-pop 下),
            "n_obs": int (此群交易日数),
            "method": "econml_cfdml" (用 CausalForestDML.fit 群内 + effect(in-group data).mean())
        }

    性能:
        - 共享 _FIT_CACHE (key 不带 group, 跨 group cache hit) — P9-1.5 已就位
        - 实际: 首次 ~130ms (fit) + N * ~5ms (effect per group), 之后 < 1ms

    数值示例 (VIX→QQQ, 按 VIX 分 3 群, 7 节点 512 交易日):
        - low_VIX (VIX < 14):  CATE = -0.05 (VIX 跌 1% → QQQ 涨 0.05%, 牛市平稳)
        - mid_VIX (14-20):     CATE = -0.10
        - high_VIX (VIX > 20): CATE = -0.25 (VIX 跌 1% → QQQ 涨 0.25%, 恐慌时大幅反弹)
        → 异质性: 高 VIX 群 CATE 5x 强于低 VIX 群, 符合"恐慌反弹"直觉
    """
    from econml.dml import CausalForestDML
    from sklearn.ensemble import RandomForestRegressor

    if cfg is None:
        cfg = load_dag_config()
    if data is None:
        data = load_dag_data(cfg=cfg)

    if heterogeneity_var not in data.columns:
        raise ValueError(f"[causal] heterogeneity_var={heterogeneity_var!r} 不在 DAG 节点 {list(data.columns)}")

    # v0.9.5 RC1 prep (P10-1 性能优化): function-level _CATE_CACHE
    # 缓存整次异质性结果, 跨调用复用 (1st ~1.7s, 2nd < 5ms)
    # key = (treatment, outcome, heterogeneity_var, n_quantiles, n_obs)
    _ck = (treatment, outcome, heterogeneity_var, n_quantiles, len(data))
    if _ck in _CATE_CACHE:
        logger.debug(f"[causal] cate_heterogeneity cache hit T={treatment} O={outcome} H={heterogeneity_var} (cache size={len(_CATE_CACHE)})")
        return _CATE_CACHE[_ck]

    # 1. 算 quantiles 切群 (基于全 sample, 不是 date-specific)
    quantiles = data[heterogeneity_var].quantile([i / n_quantiles for i in range(n_quantiles + 1)])
    # 处理 duplicate edges (e.g. 0% == 33%): 强制 + 1bp
    for i in range(1, len(quantiles)):
        if quantiles.iloc[i] <= quantiles.iloc[i - 1]:
            quantiles.iloc[i] = quantiles.iloc[i - 1] + 1e-6

    # 2. 共享 CausalForestDML fit (跟 _counterfactual_query_econml 同源, cache 命中)
    controls = [c for c in data.columns if c not in (treatment, outcome)]
    est = _get_cfdml_cached(treatment, outcome, data, controls)

    # 3. 每群算 CATE
    results = []
    for q in range(n_quantiles):
        low = float(quantiles.iloc[q])
        high = float(quantiles.iloc[q + 1])
        if q == n_quantiles - 1:
            # 最后一群含 high
            mask = (data[heterogeneity_var] >= low) & (data[heterogeneity_var] <= high)
            label_suffix = f"[{low:.4f}, {high:.4f}]"
        else:
            mask = (data[heterogeneity_var] >= low) & (data[heterogeneity_var] < high)
            label_suffix = f"[{low:.4f}, {high:.4f})"

        in_group = data[mask]
        n_obs = len(in_group)
        if n_obs < 10:
            # 样本太少, 跳过
            results.append({
                "quantile": q,
                "label": f"q{q}_{heterogeneity_var}{label_suffix}",
                "range": [low, high],
                "cate": None,
                "n_obs": n_obs,
                "skipped": f"n_obs={n_obs} < 10",
            })
            continue

        X_query = in_group[controls].values
        cate_per_row = est.effect(X_query)
        cate_mean = float(cate_per_row.mean())

        results.append({
            "quantile": q,
            "label": f"q{q}_{heterogeneity_var}{label_suffix}",
            "range": [low, high],
            "cate": cate_mean,
            "n_obs": n_obs,
            "method": "econml_cfdml",
        })

    _CATE_CACHE[_ck] = results
    return results
