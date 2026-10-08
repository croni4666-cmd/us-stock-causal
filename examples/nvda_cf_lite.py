#!/usr/bin/env python3
"""Offline exploratory NVDA conditional OLS associations and linear scenarios.

Reads explicit cached daily log returns. No identified causal effect, registered
falsification protocol, forecast probability or additive catalyst attribution.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np
import pandas as pd
import statsmodels.api as sm

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CACHE = PROJECT_ROOT / 'data/raw/nvda_cf_cache'
OUT = PROJECT_ROOT / 'output'
TICKERS = {'TNX':'^TNX', 'VIX':'^VIX', 'OIL':'CL=F', 'AMD':'AMD',
           'SMH':'SMH', 'TSM':'TSM', 'AAPL':'AAPL', 'NVDA':'NVDA'}


def assessment():
    return {'dag_trust':'low_hypothesis_only', 'causal_status':'not_established',
            'falsification_status':'not_evaluated', 'support_tendency':'insufficient',
            'causal_probability':None, 'scope':'exploratory_conditional_association'}


def _validate(data):
    if not isinstance(data, pd.DataFrame) or data.empty or not isinstance(data.index, pd.DatetimeIndex):
        raise ValueError('nonempty daily log-return frame required')
    if data.index.hasnans or data.index.has_duplicates or not data.index.is_monotonic_increasing:
        raise ValueError('unique increasing dates required')
    if data.index.tz is not None or not data.index.equals(data.index.normalize()):
        raise ValueError('naive daily dates required')
    if not all(pd.api.types.is_numeric_dtype(data[c]) for c in data):
        raise ValueError('numeric daily log returns required')
    if not np.isfinite(data.to_numpy()).all():
        raise ValueError('finite observed daily log returns required; no filling')
    return data


def load_data(period='2y', cache_root=None):
    """Read all eight cached log_ret columns, align exact dates, never fill returns.

    period is retained for callers; the cache's actual available interval is used.
    Cached values are local inputs whose provider provenance is unverified.
    """
    root = CACHE if cache_root is None else Path(cache_root)
    raw = {}
    for node in TICKERS:
        path = root / f'{node}.parquet'
        if not path.is_file():
            raise ValueError(f'missing cached log returns: {node}')
        frame = pd.read_parquet(path)
        if not isinstance(frame, pd.DataFrame) or 'log_ret' not in frame:
            raise ValueError(f'{node}: explicit log_ret column required; prices cannot substitute')
        series = frame['log_ret'].copy()
        if not isinstance(series.index, pd.DatetimeIndex):
            raise ValueError(f'{node}: daily date index required')
        series.index = series.index.tz_localize(None)
        _validate(series.to_frame())
        raw[node] = series
    return _validate(pd.concat(raw, axis=1, join='inner'))


def causal_ate_ols(treatment, outcome, data, controls=None):
    """Legacy function name; estimate an exploratory conditional association only."""
    data = _validate(data)
    selected = [c for c in data if c not in (treatment, outcome)] if controls is None else list(controls)
    if len(data) < 30 or len(selected) != len(set(selected)) or treatment in selected or outcome in selected:
        raise ValueError('at least 30 observations and distinct controls required')
    if any(c not in data for c in [treatment, outcome, *selected]):
        raise ValueError('requested model columns missing')
    design = sm.add_constant(data[[treatment, *selected]], has_constant='add')
    if np.linalg.matrix_rank(design.to_numpy()) < design.shape[1]:
        raise ValueError('rank-deficient conditional regression')
    result = sm.OLS(data[outcome], design).fit()
    return {'ate':float(result.params[treatment]), 'p_value':float(result.pvalues[treatment]),
            'std_err':float(result.bse[treatment]), 'r2':float(result.rsquared),
            'n_obs':int(result.nobs), 'controls':selected, 'epistemic_assessment':assessment(),
            'method':'exploratory_conditional_ols', 'input_provenance':'unverified_local_log_returns'}


def counterfactual_linear(date, treatment, outcome, cf_value, data, controls=None):
    """Legacy function name; a linear model scenario, never a verified counterfactual."""
    target = pd.Timestamp(date)
    if target.tz is not None or target != target.normalize() or target not in data.index:
        raise ValueError('exact observed target date required; no nearest or future fallback')
    historical = _validate(data.loc[data.index <= target].copy())
    if not np.isfinite(cf_value):
        raise ValueError('finite scenario input required')
    fitted = causal_ate_ols(treatment, outcome, historical, controls)
    actual_t = float(historical.loc[target, treatment]); actual_y = float(historical.loc[target, outcome])
    delta = fitted['ate'] * (cf_value-actual_t)
    return {'actual_t':actual_t, 'actual_y':actual_y, 'cf_t':float(cf_value),
            'cf_y':actual_y+delta, 'delta':delta, 'ate':fitted['ate'], 'p_value':fitted['p_value'],
            'training_end':str(target.date()), 'n_obs':fitted['n_obs'],
            'controls':fitted['controls'], 'epistemic_assessment':assessment()}


def main(argv=None):
    parser = argparse.ArgumentParser(description='Offline exploratory NVDA association/model scenarios; causal status not established')
    parser.add_argument('--date', default='2026-07-27')
    parser.add_argument('--cache-root', type=Path, default=CACHE)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    status = json.dumps(assessment(), ensure_ascii=False)
    print(status)
    try:
        data = load_data(cache_root=args.cache_root)
        target = pd.Timestamp(args.date)
        if target.tz is not None or target != target.normalize() or target not in data.index:
            raise ValueError('exact observed target date required; no nearest or future fallback')
        lines = [status, f'Date: {target.date()}; local cache provenance unverified',
                 '探索性条件关联 / 模型情景；控制变量未经因果认证；尚无登记的可证伪检验。',
                 '单位: daily log return；乘100为对数百分点，不是简单收益百分比。',
                 '各情景不能相加解释当日涨跌；没有观察证据支持具体新闻或AI资本支出叙事。']
        for treatment in TICKERS:
            if treatment == 'NVDA':
                continue
            row = counterfactual_linear(args.date, treatment, 'NVDA', 0., data)
            lines.append(f"{treatment}: conditional coefficient={row['ate']:+.4f}; exploratory p={row['p_value']:.4f}; "
                         f"model scenario input=0; observed NVDA={row['actual_y']:+.4f}; scenario={row['cf_y']:+.4f}; "
                         f"model delta={row['delta']:+.4f}; training_end={row['training_end']}; n={row['n_obs']}")
        output = args.output or OUT / f'nvda_exploratory_{target.date()}.txt'
        output.parent.mkdir(parents=True, exist_ok=True)
        text = '\n'.join(lines)+'\n'
        output.write_text(text, encoding='utf-8')
        print(text)
        print(f'[report] {output}')
    except (ValueError, FileNotFoundError, KeyError) as error:
        print(f'[unavailable] {error}')
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
