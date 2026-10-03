import math

import pandas as pd
import pytest

from src.asset_models import (period_return, return_summary, equity_contributions,
                              treasury_profile, duration_effect, gold_archive_metrics)


def frame(close=(100, 101), adj=(100, 102)):
    data = {'close': close}
    if adj is not None:
        data['adj close'] = adj
    return pd.DataFrame(data, index=pd.to_datetime(['2026-10-01', '2026-10-02']))


def doc(rows=None, **changes):
    result = {'symbol': 'QQQ', 'kind': 'holdings', 'as_of': '2026-10-01',
              'available_at': '2026-10-01T12:00:00+00:00', 'rows': rows or [
                  {'id': 'AAA', 'ticker': 'AAA', 'asset_class': 'Equity', 'weight': .6},
                  {'id': 'BBB', 'ticker': 'BBB', 'asset_class': 'Equity', 'weight': .3},
                  {'id': 'USD', 'ticker': 'USD', 'asset_class': 'Currency', 'weight': .1}]}
    result.update(changes)
    return result


def test_price_and_adjusted_proxy_are_separate():
    result = return_summary('IEF', frame(), '2026-10-01', '2026-10-02')
    assert result['price_return'] == pytest.approx(.01)
    assert result['adjusted_return_proxy'] == pytest.approx(.02)
    assert result['adjustment_gap'] == pytest.approx(.01)


def test_absent_adjusted_prices_never_fall_back_to_price_return():
    result = return_summary('TLT', frame(adj=None), '2026-10-01', '2026-10-02')
    assert result['adjusted_return_proxy'] is None


@pytest.mark.parametrize('data', [frame(close=(100, math.nan)), frame(close=(0, 101)),
                                frame(close=(100, math.inf)), frame().iloc[::-1],
                                pd.concat([frame(), frame()])])
def test_returns_reject_invalid_or_duplicate_or_unordered_endpoints(data):
    with pytest.raises(ValueError):
        period_return(data['close'], '2026-10-01', '2026-10-02')


def test_exact_dates_required_no_asof_forward_fill():
    with pytest.raises(ValueError):
        period_return(frame()['close'], '2026-09-30', '2026-10-02')


def test_yield_changes_are_bp_and_not_investment_returns():
    result = return_summary('^TNX', frame(close=(5, 5.1)), '2026-10-01', '2026-10-02')
    assert result['yield_delta_bp'] == pytest.approx(10)
    assert 'price_return' not in result


@pytest.mark.parametrize('symbol', ['GC=F', '^IXIC', '^NDX'])
def test_futures_and_price_indices_do_not_claim_total_return(symbol):
    result = return_summary(symbol, frame(), '2026-10-01', '2026-10-02')
    assert result['adjusted_return_proxy'] is None
    assert result['limitations']


def test_unsupported_asset_fails_explicitly():
    with pytest.raises(ValueError):
        return_summary('UNKNOWN', frame(), '2026-10-01', '2026-10-02')


def test_equity_contributions_preserve_uncovered_weight_and_residual():
    result = equity_contributions(doc(), {'AAA': .1}, .05, '2026-10-01', 'point_in_time')
    assert result['covered_weight'] == .6
    assert result['contribution'] == pytest.approx(.06)
    assert result['residual'] == pytest.approx(-.01)
    assert result['missing_tickers'] == ['BBB']
    assert result['non_equity_weight'] == pytest.approx(.1)


def test_end_weights_and_late_download_cannot_explain_start_date():
    future = equity_contributions(doc(as_of='2026-10-02'), {'AAA': .1}, .05,
                                  '2026-10-01', 'retrospective')
    late = equity_contributions(doc(available_at='2026-10-03T12:00:00+00:00'),
                                {'AAA': .1}, .05, '2026-10-01', 'point_in_time')
    assert future['status'] == late['status'] == 'unavailable'


def test_qqq_holdings_do_not_impersonate_official_index_weights():
    with pytest.raises(ValueError):
        equity_contributions(doc(symbol='^NDX'), {'AAA': .1}, .05, '2026-10-01', 'retrospective')


def test_duration_uses_portfolio_weights_and_reports_uncovered_bonds():
    source = doc(symbol='TLT', rows=[
        {'id': 'A', 'asset_class': 'Fixed Income', 'weight': .8, 'duration_years': 15},
        {'id': 'B', 'asset_class': 'Fixed Income', 'weight': .1, 'duration_years': None},
        {'id': 'Cash', 'asset_class': 'Cash', 'weight': .1, 'duration_years': 0}])
    result = treasury_profile(source)
    assert result['weighted_duration_years'] == 12
    assert result['duration_covered_weight'] == .8
    assert result['bond_weight'] == pytest.approx(.9)
    assert result['complete'] is False
    assert duration_effect(12, 10) == pytest.approx(-.012)


@pytest.mark.parametrize('duration,bp', [(-1, 10), (1, math.nan), (math.inf, 10)])
def test_duration_rejects_invalid_units(duration, bp):
    with pytest.raises(ValueError):
        duration_effect(duration, bp)


def test_gold_distinguishes_nav_clock_and_market_premium_clock():
    source = doc(symbol='GLD', kind='gold_archive', as_of='2026-10-02', rows=[
        {'date': '2026-10-01', 'close': 100, 'nav_1030': 101,
         'ounces_per_share': .1, 'premium_pct_1615': .2},
        {'date': '2026-10-02', 'close': 102, 'nav_1030': 100,
         'ounces_per_share': .099, 'premium_pct_1615': -.1}])
    result = gold_archive_metrics(source, '2026-10-01', '2026-10-02', 'retrospective')
    assert result['price_return'] == pytest.approx(.02)
    assert result['nav_return_1030'] == pytest.approx(100 / 101 - 1)
    assert result['backing_change'] == pytest.approx(-.01)
    assert result['premium_pct_1615'] == -.1
    assert result['causal_status'] == 'not_identified'
    assert 'different pricing times' in result['limitations']


def test_gold_missing_date_and_late_point_in_time_data_are_unavailable():
    source = doc(symbol='GLD', kind='gold_archive', as_of='2026-10-01',
                 available_at='2026-10-03T12:00:00+00:00',
                 rows=[{'date': '2026-10-01', 'close': 100}])
    result = gold_archive_metrics(source, '2026-10-01', '2026-10-02', 'retrospective')
    assert result['status'] == 'unavailable'
    result = gold_archive_metrics(source, '2026-10-01', '2026-10-01', 'point_in_time')
    assert result['status'] == 'unavailable'
