"""Workflow regressions for the remaining audit defects."""
import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from src import attribution, cache, causal, report, sector_weights_live as weights


@pytest.mark.parametrize('ref, expected', [
    ('2026-04-03T17:00:00-04:00', date(2026, 4, 2)),  # Good Friday
    ('2026-10-12T17:00:00-04:00', date(2026, 10, 12)),  # Federal holiday, NYSE open
    ('2026-11-27T13:14:00-05:00', date(2026, 11, 25)),  # early close + delay
    ('2026-11-27T13:15:00-05:00', date(2026, 11, 27)),
    ('2026-12-01T05:14:00+08:00', date(2026, 11, 27)),  # winter UTC offset
    ('2026-12-01T05:15:00+08:00', date(2026, 11, 30)),
])
def test_completed_session_uses_exchange_calendar(ref, expected):
    assert cache.get_expected_last_trading_day(ref) == expected


@pytest.fixture
def weight_store(tmp_path, monkeypatch):
    config = tmp_path / 'config' / 'sector_weights.json'
    config.parent.mkdir()
    config.write_text(json.dumps({'_meta': {'as_of': '2026-07-23'}, 'QQQ': {'XLK': .7}}))
    snapshots = tmp_path / 'data' / 'cache'
    snapshots.mkdir(parents=True)
    monkeypatch.setattr(weights, 'PROJECT_ROOT', tmp_path)
    monkeypatch.setattr(weights, 'WEIGHTS_PATH', config)
    monkeypatch.setattr(weights, 'CACHE_DIR', snapshots)
    monkeypatch.setattr(attribution, 'WEIGHTS_PATH', config)
    return config, snapshots


def test_history_requires_explicit_opt_in_for_future_weights(weight_store):
    with pytest.raises(FileNotFoundError, match='历史'):
        weights.load_live_or_static('2026-06-01')


def test_force_cannot_bypass_historical_weight_validation(weight_store):
    with pytest.raises(FileNotFoundError, match='历史'):
        attribution.attribute_index('QQQ', date='2026-06-01', force=True)


def test_weight_selection_uses_effective_date_not_cache_filename(weight_store):
    _, snapshots = weight_store
    (snapshots / 'sector_weights_live_2026-08-01.json').write_text(json.dumps({
        'as_of': '2026-08-01',
        'data': {'_meta': {'as_of': '2026-05-01'}, 'QQQ': {'XLK': .2}},
    }))
    # A cached copy of May weights must not beat the effective July version.
    assert weights.load_live_or_static('2026-08-01')['QQQ']['XLK'] == .7


def test_cleanup_preserves_last_copy_of_each_historical_version(weight_store):
    _, snapshots = weight_store
    old = snapshots / 'sector_weights_live_2025-05-01.json'
    old.write_text(json.dumps({'as_of': '2025-05-01', 'data': {
        '_meta': {'as_of': '2025-05-01'}, 'QQQ': {'XLK': .2},
    }}))
    weights.clear_old_caches(keep_days=7)
    assert weights.load_live_or_static('2025-06-01', allow_future_fallback=False)['QQQ']['XLK'] == .2


def test_missing_historical_weights_are_visible_in_report(weight_store):
    rendered = report._segment_2_attribution('QQQ', 5, as_of='2026-06-01')
    assert '历史权重不可用' in rendered
    assert '残差' not in rendered


@pytest.mark.parametrize('relative_path', [
    'data/raw/commodities_futures/GC_F.parquet',
    'data/raw/indices/DIA.parquet',
    'data/cache/sector_weights_live_2026-07-23.json',
])
def test_report_invalidates_for_every_input_layer(tmp_path, monkeypatch, relative_path):
    # Keep real report caching and filesystem reads; replace slow analytical segments.
    monkeypatch.setattr(report, 'PROJECT_ROOT', tmp_path)
    path = tmp_path / relative_path
    path.parent.mkdir(parents=True)
    path.write_text('old')
    monkeypatch.setattr(report, 'macro_topline', lambda **kw: path.read_text())
    monkeypatch.setattr(report, 'render_causal_section', lambda **kw: '')
    monkeypatch.setattr(report, 'five_segment_report', lambda *args, **kw: {})
    monkeypatch.setattr(report, 'render_markdown', lambda r: '')
    report.clear_report_cache()
    assert 'old' in report.render_full_report(['QQQ'], as_of='2026-08-01')
    path.write_text('updated dependency')
    assert 'updated dependency' in report.render_full_report(['QQQ'], as_of='2026-08-01')


def test_saved_snapshots_keep_the_real_effective_date(weight_store):
    weights.save_live_cache(weights.pull_live_weights(), date='2026-08-01')
    assert weights.load_live_or_static('2026-08-01')['_meta']['as_of'] == '2026-07-23'


def test_concurrent_weight_readers_do_not_corrupt_cache(weight_store):
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: weights.load_live_or_static('2026-08-01'), range(32)))
    assert all(r['QQQ']['XLK'] == .7 for r in results)
    path = weight_store[1] / 'sector_weights_live_2026-08-01.json'
    initial_mtime = path.stat().st_mtime_ns
    weights.load_live_or_static('2026-08-01')
    assert path.stat().st_mtime_ns == initial_mtime  # reads cannot invalidate report caches


def test_approximate_counterfactual_keeps_mediated_total_effect():
    import numpy as np
    rng = np.random.default_rng(123)
    z = rng.normal(size=1200)
    t = z + rng.normal(size=1200)
    m = 2 * t + rng.normal(0, .2, 1200)
    y = 3 * m + 4 * z + rng.normal(0, .2, 1200)
    data = pd.DataFrame({'Z': z, 'T': t, 'M': m, 'Y': y},
                        index=pd.date_range('2020-01-01', periods=1200, freq='B'))
    cfg = {'dot': 'digraph { Z -> T; Z -> Y; T -> M; M -> Y; }',
           'nodes': {'treatments': ['T', 'M', 'Z']}}
    # The total effect is 2 * 3 = 6. Controlling the mediator erases it.
    result = causal.counterfactual_query(str(data.index[-1].date()), 'T', 'Y',
                                        t[-1] - 1, data=data, cfg=cfg, method='econml')
    assert result.delta == pytest.approx(-6., abs=1.)
    grouped = causal.cate_heterogeneity('T', 'Y', 'Z', data=data, cfg=cfg, n_quantiles=2)
    assert all(r['cate'] == pytest.approx(6., abs=1.) for r in grouped)


def test_unconfounded_approximation_needs_no_extra_columns():
    import numpy as np
    rng = np.random.default_rng(99)
    t = rng.normal(size=600)
    data = pd.DataFrame({'T': t, 'Y': 6 * t + rng.normal(0, .1, len(t))},
                        index=pd.date_range('2024-01-01', periods=600, freq='B'))
    cfg = {'dot': 'digraph { T -> Y; }', 'nodes': {}}
    result = causal.counterfactual_query(str(data.index[-1].date()), 'T', 'Y',
                                        t[-1] - 1, data=data, cfg=cfg, method='econml')
    assert result.delta == pytest.approx(-6., abs=.5)
    # Changing the DAG to require an unavailable confounder must invalidate CATE.
    causal.cate_heterogeneity('T', 'Y', 'T', data=data, cfg=cfg, n_quantiles=2)
    cfg['dot'] = 'digraph { Z -> T; Z -> Y; T -> Y; }'
    with pytest.raises(ValueError, match='unidentifiable'):
        causal.cate_heterogeneity('T', 'Y', 'T', data=data, cfg=cfg, n_quantiles=2)
