"""Exact-day QQQ weight mechanics with wealth-linked residual reconciliation."""
from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import pandas_market_calendars as mcal

from src.asset_models import equity_contributions, period_return
from src.asset_sources import eligible_snapshot


def daily_equity_attribution(docs, etf_prices, stock_prices, start, end, *, mode='point_in_time'):
    if mode not in ('point_in_time', 'retrospective') or date.fromisoformat(start) > date.fromisoformat(end):
        raise ValueError('invalid daily period/mode')
    if any(doc.get('symbol') != 'QQQ' or doc.get('kind') != 'holdings' for doc in docs):
        raise ValueError('daily model requires QQQ fund holdings')
    etf_return = period_return(etf_prices['close'], start, end)
    index = etf_prices.index
    if not isinstance(index, pd.DatetimeIndex) or index.tz is not None or not index.equals(index.normalize()):
        raise ValueError('expected daily ETF observations')
    sessions = list(mcal.get_calendar('NASDAQ').schedule(start_date=start, end_date=end).index.strftime('%Y-%m-%d'))
    available_days = set(index.strftime('%Y-%m-%d'))
    missing_market = [day for day in sessions if day not in available_days]
    result = {'status': 'unavailable', 'method': 'exact-day beginning fund weights; wealth-linked price contributions',
              'mode': mode, 'days': [], 'missing_weight_dates': [], 'missing_market_dates': missing_market,
              'linked_contribution': None, 'linked_residual': None, 'linked_stock_contributions': [],
              'etf_price_return': etf_return, 'causal_status': 'not_identified',
              'historical_trade_backtest_ready': False,
              'limitations': ['QQQ fund weights are not official Nasdaq index weights',
                              'uncovered holdings, cash, derivatives, dividends, fees and trading remain in residual',
                              'capture availability does not certify tradable historical execution or original market publication']}
    if missing_market or len(sessions) < 2 or sessions[0] != start or sessions[-1] != end:
        result['reason'] = 'exact daily session endpoints unavailable'
        return result
    wealth, linked, residual, stocks_linked, partial = 1., 0., 0., {}, False
    for first, last in zip(sessions, sessions[1:]):
        etf_daily = period_return(etf_prices['close'], first, last)
        candidates = [doc for doc in docs if doc['as_of'] == first and eligible_snapshot(doc, first, mode)]
        beginning = max(candidates, key=lambda d: datetime.fromisoformat(d['available_at']), default=None)
        if beginning is None:
            result['missing_weight_dates'].append(first)
            result['days'].append({'start': first, 'end': last, 'status': 'unavailable',
                'reason': 'exact-day beginning holdings/availability missing', 'wealth_before': wealth,
                'etf_price_return': etf_daily})
        else:
            returns, sources = {}, {}
            for row in beginning['rows']:
                ticker = row.get('ticker')
                if row['asset_class'] != 'Equity' or not ticker:
                    continue
                try:
                    stock = (stock_prices(ticker, first, last) if callable(stock_prices)
                             else stock_prices[ticker])
                    returns[ticker] = period_return(stock['close'], first, last)
                    sources[ticker] = stock.attrs.get('market_source', {})
                except (ValueError, KeyError, OSError):
                    continue
            daily = equity_contributions(beginning, returns, etf_daily, first, mode)
            daily.update(start=first, end=last, wealth_before=wealth, market_sources=sources,
                         beginning_source={key: beginning.get(key) for key in
                             ('as_of', 'sha256', 'source_url', 'available_at', 'retrieved_at')})
            daily['limitations'] = result['limitations']
            result['days'].append(daily)
            linked += wealth * daily['contribution']
            residual += wealth * daily['residual']
            for row in daily['contributions']:
                stocks_linked[row['ticker']] = stocks_linked.get(row['ticker'], 0.) + wealth * row['contribution']
            partial = partial or bool(daily['missing_tickers']) or bool(daily['unknown_weight_count'])
        wealth *= 1 + etf_daily
    if result['missing_weight_dates']:
        result['reason'] = 'one or more exact-day holdings snapshots missing; no complete period attribution'
    else:
        result.update(status='partial' if partial else 'ok', linked_contribution=linked,
                      linked_residual=residual, linked_stock_contributions=[
                          {'ticker': ticker, 'contribution': value} for ticker, value in
                          sorted(stocks_linked.items(), key=lambda p: abs(p[1]), reverse=True)])
    return result
