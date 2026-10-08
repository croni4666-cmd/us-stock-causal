import importlib
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest


def panel():
    rng = np.random.default_rng(88)
    data = pd.DataFrame(rng.normal(0, .01, (100, 8)),
                        index=pd.bdate_range('2026-01-02', periods=100),
                        columns=['TNX', 'VIX', 'OIL', 'AMD', 'SMH', 'TSM', 'AAPL', 'NVDA'])
    data['NVDA'] = 2 * data['VIX'] + data['AMD'] + rng.normal(0, .001, len(data))
    return data


def test_demo_numeric_units_and_assessment_are_conditional(monkeypatch, capsys):
    from examples import causal_demo as demo
    data = panel()
    assessment = {'dag_trust': 'low_hypothesis_only', 'causal_status': 'not_established'}
    effect = SimpleNamespace(estimate=-.2, method='test', n_obs=100, refutation={},
                             to_dict=lambda: {'epistemic_assessment': assessment})
    cf = SimpleNamespace(actual_outcome=.01, counterfactual_outcome=.02, delta=.01,
                         to_dict=lambda: {'epistemic_assessment': assessment})
    monkeypatch.setattr(demo, 'load_dag_config', lambda: {'dag_name': 'synthetic', 'dot': 'digraph { VIX -> QQQ; TNX -> QQQ; }'})
    monkeypatch.setattr(demo, 'load_dag_data', lambda **kw: data)
    monkeypatch.setattr(demo, 'causal_query', lambda **kw: effect)
    monkeypatch.setattr(demo, 'counterfactual_query', lambda **kw: cf)
    assert demo.main() == 0
    text = capsys.readouterr().out
    assert 'not_established' in text and 'low_hypothesis_only' in text
    assert '-0.20 个对数百分点' in text and '-20.00%' not in text
    assert '应为负' not in text and 'L2 干预 query' not in text
    assert '模型情景' in text


def test_invalid_residual_is_error_alert_without_numeric_placeholder(monkeypatch):
    from src.checks import residual
    monkeypatch.setattr(residual, 'capture_residuals', lambda d: {'residuals': {}})
    monkeypatch.setattr(residual, 'load_baseline', lambda: {'residuals': {}})
    alerts = residual.check('2026-10-01')
    assert alerts and all(a['severity'] == 'error' for a in alerts)
    assert all('validation_error' in a['details'] for a in alerts)
    assert all('0.000%' not in a['message'] for a in alerts)


def test_lite_never_replaces_missing_target_with_last_observation():
    from examples import nvda_cf_lite as lite
    with pytest.raises(ValueError, match='exact'):
        lite.counterfactual_linear('2025-01-01', 'VIX', 'NVDA', 0., panel())


def test_exploratory_scenario_ignores_future_data_and_retains_assessment():
    from examples import nvda_cf_lite as lite
    data = panel(); target = str(data.index[60].date())
    first = lite.counterfactual_linear(target, 'VIX', 'NVDA', 0., data)
    data.iloc[61:] *= 100000
    second = lite.counterfactual_linear(target, 'VIX', 'NVDA', 0., data)
    assert first == second
    assert first['epistemic_assessment']['causal_status'] == 'not_established'
    assert first['epistemic_assessment']['falsification_status'] == 'not_evaluated'


@pytest.mark.parametrize('module', ['nvda_cf_lite', 'nvda_counterfactual'])
def test_nvda_cli_is_offline_and_refuses_missing_target(tmp_path, monkeypatch, capsys, module):
    example = importlib.import_module('examples.' + module)
    from examples import nvda_cf_lite as lite
    data = panel()
    monkeypatch.setattr(lite, 'load_data', lambda *a, **kw: data)
    assert example.main(['--date', '2025-01-01', '--output', str(tmp_path/'report.txt')]) == 1
    assert not (tmp_path/'report.txt').exists()
    text = capsys.readouterr().out
    assert 'not_established' in text and 'exact' in text

@pytest.mark.parametrize('module', ['nvda_cf_lite', 'nvda_counterfactual'])
def test_nvda_cli_writes_exploratory_report_without_additive_attribution(tmp_path, monkeypatch, module):
    from examples import nvda_cf_lite as lite
    example = importlib.import_module('examples.' + module)
    data = panel(); target = str(data.index[60].date())
    monkeypatch.setattr(lite, 'load_data', lambda *a, **kw: data)
    output = tmp_path/'scenario.txt'
    assert example.main(['--date', target, '--output', str(output)]) == 0
    text = output.read_text(encoding='utf-8')
    assert 'not_established' in text and 'not_evaluated' in text
    assert f'training_end={target}; n=61' in text
    assert 'conditional coefficient=' in text and 'model delta=' in text
    assert '解释力合计' not in text and 'L2 ATE' not in text


def test_nvda_cache_never_fills_missing_returns_or_accepts_unknown_price_column(tmp_path):
    from examples import nvda_cf_lite as lite
    data = panel()
    for node in lite.TICKERS:
        data[[node]].rename(columns={node:'log_ret'}).to_parquet(tmp_path/f'{node}.parquet')
    loaded = lite.load_data(cache_root=tmp_path)
    pd.testing.assert_frame_equal(loaded, data, check_freq=False)
    missing = data[['VIX']].rename(columns={'VIX':'log_ret'})
    missing.iloc[10, 0] = np.nan
    missing.to_parquet(tmp_path/'VIX.parquet')
    with pytest.raises(ValueError, match='finite'):
        lite.load_data(cache_root=tmp_path)
    data[['VIX']].rename(columns={'VIX':'close'}).to_parquet(tmp_path/'VIX.parquet')
    with pytest.raises(ValueError, match='log_ret'):
        lite.load_data(cache_root=tmp_path)
