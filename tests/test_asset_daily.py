import pandas as pd
import pytest

from src.asset_daily import daily_equity_attribution


def prices(values):
    return pd.DataFrame({'close': values}, index=pd.to_datetime(['2026-09-30', '2026-10-01', '2026-10-02']))


def holding(day, weight=.6, at='2026-09-30T12:00:00+00:00'):
    return {'symbol': 'QQQ', 'kind': 'holdings', 'as_of': day, 'available_at': at,
            'sha256': 'synthetic_' + day, 'rows': [
                {'id': 'AAA', 'ticker': 'AAA', 'asset_class': 'Equity', 'weight': weight},
                {'id': 'USD', 'ticker': 'USD', 'asset_class': 'Currency', 'weight': 1-weight}]}


def run(docs, stocks=None, etf=None, mode='retrospective'):
    return daily_equity_attribution(docs, prices([100., 110., 99.]) if etf is None else etf,
        {'AAA': prices([100., 120., 108.])} if stocks is None else stocks,
        '2026-09-30', '2026-10-02', mode=mode)


def test_daily_weights_and_wealth_link_reconcile_to_actual_etf_return():
    result = run([holding('2026-09-30'), holding('2026-10-01', .5)])
    assert result['status'] == 'ok'
    assert result['linked_contribution'] == pytest.approx(.6 * .2 + 1.1 * .5 * -.1)
    assert result['linked_contribution'] + result['linked_residual'] == pytest.approx(-.01)
    assert result['etf_price_return'] == pytest.approx(-.01)
    assert result['days'][1]['wealth_before'] == pytest.approx(1.1)


def test_missing_daily_holdings_never_reuse_older_or_future_snapshot():
    result = run([holding('2026-09-30'), holding('2026-10-02')])
    assert result['status'] == 'unavailable'
    assert result['missing_weight_dates'] == ['2026-10-01']
    assert result['linked_contribution'] is None
    assert result['days'][0]['covered_weight'] == .6


def test_future_availability_is_blocked_in_strict_mode():
    result = run([holding('2026-09-30', at='2026-10-03T12:00:00+00:00'),
                  holding('2026-10-01', at='2026-10-03T12:00:00+00:00')], mode='point_in_time')
    assert result['missing_weight_dates'] == ['2026-09-30', '2026-10-01']


def test_missing_stock_return_stays_in_residual_without_renormalizing():
    result = run([holding('2026-09-30'), holding('2026-10-01')], stocks={})
    assert result['status'] == 'partial'
    assert result['days'][0]['covered_weight'] == 0
    assert result['linked_contribution'] == 0
    assert result['linked_residual'] == pytest.approx(-.01)


def test_missing_etf_session_cannot_be_disguised_as_single_multiday_interval():
    result = run([holding('2026-09-30'), holding('2026-10-01')], etf=prices([100., 110., 99.]).iloc[[0, 2]])
    assert result['status'] == 'unavailable'
    assert result['missing_market_dates'] == ['2026-10-01']
    assert result['linked_contribution'] is None


def test_duplicate_or_intraday_dates_rejected():
    with pytest.raises(ValueError):
        run([], etf=pd.concat([prices([100., 110., 99.]), prices([100., 110., 99.])]))
