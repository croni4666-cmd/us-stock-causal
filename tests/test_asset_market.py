import json

import pandas as pd
import pytest

from src.asset_market import (action_summary, capture_market, load_market_snapshots,
                              select_market, store_market)


def frame():
    return pd.DataFrame({'close': [100., 99., 101.], 'adj close': [98., 99., 101.],
                         'dividends': [5., 1., 0.], 'stock splits': [0., 0., 2.]},
                        index=pd.to_datetime(['2026-09-30', '2026-10-01', '2026-10-02']))


def store(root, symbol='QQQ', data=None, at='2026-10-03T12:00:00+00:00'):
    return store_market(symbol, frame() if data is None else data, root,
                        '2026-09-30', '2026-10-03', retrieved_at=at)


def test_capture_revisions_are_immutable_and_retrospective_selects_latest(tmp_path):
    first = store(tmp_path)
    changed = frame()
    changed.loc['2026-10-02', 'close'] = 102.
    second = store(tmp_path, data=changed, at='2026-10-04T12:00:00+00:00')
    assert first != second and first.exists()
    docs = load_market_snapshots('QQQ', tmp_path)
    assert len(docs) == 2 and docs[0]['sha256'] != docs[1]['sha256']
    selected = select_market('QQQ', tmp_path, '2026-09-30', '2026-10-02', mode='retrospective')
    assert selected['close'].iloc[-1] == 102.
    assert selected.attrs['market_source']['available_at'].startswith('2026-10-04')


def test_point_in_time_rejects_later_download_and_observes_new_york_cutoff(tmp_path):
    store(tmp_path, at='2026-10-02T20:29:00+00:00')
    store(tmp_path, at='2026-10-02T20:31:00+00:00')
    selected = select_market('QQQ', tmp_path, '2026-09-30', '2026-10-02')
    assert selected.attrs['market_source']['available_at'].startswith('2026-10-02T20:29')
    with pytest.raises(ValueError, match='eligible'):
        select_market('QQQ', tmp_path, '2026-09-30', '2026-10-01')


def test_corrupt_bytes_and_metadata_are_rejected(tmp_path):
    meta = store(tmp_path)
    doc = json.loads(meta.read_text())
    doc['row_count'] = 900
    meta.write_text(json.dumps(doc))
    with pytest.raises(ValueError, match='metadata'):
        load_market_snapshots('QQQ', tmp_path)
    doc['row_count'] = 3
    meta.write_text(json.dumps(doc))
    meta.with_suffix('.parquet').write_bytes(b'broken')
    with pytest.raises(ValueError, match='hash'):
        load_market_snapshots('QQQ', tmp_path)


def test_dates_are_never_filled_and_missing_endpoint_refuses_selection(tmp_path):
    store(tmp_path, data=frame().iloc[[0, 2]])
    with pytest.raises(ValueError, match='eligible'):
        select_market('QQQ', tmp_path, '2026-10-01', '2026-10-02', mode='retrospective')


@pytest.mark.parametrize('mutate', [lambda f: f.iloc[::-1], lambda f: pd.concat([f, f.iloc[:1]]),
                                    lambda f: f.assign(close=float('nan')),
                                    lambda f: f.assign(close=-1)])
def test_invalid_market_frame_is_not_saved(tmp_path, mutate):
    with pytest.raises(ValueError):
        store(tmp_path, data=mutate(frame()))
    assert not list(tmp_path.rglob('*.json'))


def test_yields_can_be_zero_or_negative_and_symbol_paths_do_not_collide(tmp_path):
    store(tmp_path, symbol='^TNX', data=frame().assign(close=-.1))
    store(tmp_path, symbol='BRK.B')
    store(tmp_path, symbol='BRK_B')
    assert len({p.parent.name for p in tmp_path.rglob('*.json')}) == 3
    with pytest.raises(ValueError, match='symbol'):
        store(tmp_path, symbol='../QQQ')


def test_actions_exclude_start_and_keep_provider_split_units():
    events = action_summary(frame(), '2026-09-30', '2026-10-02')
    assert events['dividend_per_share'] == 1.
    assert events['events'] == [{'date': '2026-10-01', 'field': 'dividends', 'value': 1.},
                                {'date': '2026-10-02', 'field': 'stock splits', 'value': 2.}]
    assert events['missing_fields'] == ['capital gains']
    assert 'not reapplied' in events['limitations'][0]


def test_capture_passes_inclusive_exclusive_bounds_and_records_actions(tmp_path):
    calls = []
    def fetch(symbol, start, end):
        calls.append((symbol, start, end))
        return frame()
    path = capture_market('QQQ', '2026-09-30', '2026-10-03', tmp_path, fetcher=fetch)
    assert calls == [('QQQ', '2026-09-30', '2026-10-03')]
    assert json.loads(path.read_text())['fields'] == list(frame().columns)


@pytest.mark.parametrize('at', ['2026-10-03T12:00:00', '2026-09-29T12:00:00+00:00'])
def test_capture_time_must_be_timezone_aware_and_not_before_observations(tmp_path, at):
    with pytest.raises(ValueError):
        store(tmp_path, at=at)


def test_same_session_intraday_quote_is_not_saved_as_completed_daily_bar(tmp_path):
    with pytest.raises(ValueError, match='session close'):
        store(tmp_path, at='2026-10-02T17:00:00+00:00')


def test_missing_event_session_makes_cash_totals_unknown():
    data = frame().assign(dividends=0., **{'capital gains': 0., 'stock splits': 0.}).iloc[[0, 2]]
    result = action_summary(data, '2026-09-30', '2026-10-02')
    assert result['missing_market_dates'] == ['2026-10-01']
    assert result['dividend_per_share'] is None
    assert result['capital_gain_per_share'] is None


def test_daily_selection_can_use_report_cutoff_without_loosening_endpoints(tmp_path):
    store(tmp_path, at='2026-10-02T20:29:00+00:00')
    selected = select_market('QQQ', tmp_path, '2026-09-30', '2026-10-01', availability_end='2026-10-02')
    assert selected.attrs['market_source']['available_at'].startswith('2026-10-02T20:29')
    with pytest.raises(ValueError):
        select_market('QQQ', tmp_path, '2026-09-30', '2026-10-02', availability_end='2026-10-01')


@pytest.mark.parametrize('symbol', ['.', '..'])
def test_symbol_cannot_resolve_to_snapshot_root_or_parent(tmp_path, symbol):
    with pytest.raises(ValueError, match='symbol'):
        store(tmp_path / 'm', symbol=symbol)
