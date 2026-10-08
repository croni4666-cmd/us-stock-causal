"""Immutable provider-normalized daily histories. Network is explicit and lazy."""
from __future__ import annotations

from datetime import date, datetime, time, timezone
import hashlib
import json
from pathlib import Path
from urllib.parse import quote
import uuid
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pandas_market_calendars as mcal

from src.asset_models import ASSET_KINDS
from src.asset_sources import _atomic_write, _timestamp


def _symbol(value):
    if not isinstance(value, str) or not value or value in ('.', '..') or len(value) > 32 or any(
            c not in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789^=._-' for c in value):
        raise ValueError('invalid market symbol')
    return quote(value, safe='').replace('.', '%2E')


def _bounds(start, end):
    if date.fromisoformat(start) >= date.fromisoformat(end):
        raise ValueError('market query requires start < exclusive end')


def _validate(data, symbol, start, end, at):
    _bounds(start, end)
    if not isinstance(data, pd.DataFrame) or data.empty or 'close' not in data:
        raise ValueError('empty market frame or close missing')
    if not isinstance(data.index, pd.DatetimeIndex) or data.index.tz is not None:
        raise ValueError('expected naive daily date index')
    days = data.index
    if days.hasnans or days.has_duplicates or not days.is_monotonic_increasing or not days.equals(days.normalize()):
        raise ValueError('market dates must be unique increasing daily dates')
    if days[0].date() < date.fromisoformat(start) or days[-1].date() >= date.fromisoformat(end):
        raise ValueError('market observations outside requested bounds')
    if days[-1].date() > datetime.fromisoformat(at).date():
        raise ValueError('market observation after capture')
    captured = datetime.fromisoformat(at)
    last_day = days[-1].date()
    if ASSET_KINDS.get(symbol) == 'continuous_futures_quote':
        close = datetime.combine(last_day, time(17), ZoneInfo('America/New_York'))
    else:
        schedule = mcal.get_calendar('NASDAQ').schedule(start_date=last_day, end_date=last_day)
        if schedule.empty:
            raise ValueError('market observation is not a US session')
        close = schedule.iloc[0]['market_close']
    if captured < close:
        raise ValueError('capture before session close; incomplete daily bar')
    if data.columns.has_duplicates or any(not isinstance(c, str) for c in data.columns):
        raise ValueError('invalid market fields')
    for field in data.columns:
        if not pd.api.types.is_numeric_dtype(data[field]):
            raise ValueError('market fields must be numeric')
        values = data[field].to_numpy(dtype=float)
        if np.isinf(values).any():
            raise ValueError('nonfinite market value')
        if field == 'close' and (np.isnan(values).any() or
                (ASSET_KINDS.get(symbol) != 'yield_quote' and (values <= 0).any())):
            raise ValueError('invalid close values')


def _facts(data):
    return {'row_count': len(data), 'first_date': data.index[0].date().isoformat(),
            'last_date': data.index[-1].date().isoformat(), 'fields': list(data.columns)}


def store_market(symbol, data, root, start, end, *, retrieved_at=None):
    directory = Path(root) / _symbol(symbol)
    at = _timestamp(retrieved_at or datetime.now(timezone.utc).isoformat()).isoformat()
    _validate(data, symbol, start, end, at)
    # Preserve values and event fields, but never copy caller attrs into evidence.
    clean = data.copy()
    clean.attrs = {}
    raw = clean.to_parquet(index=True)
    digest = hashlib.sha256(raw).hexdigest()
    # Digest is in metadata; short UUID filenames also work under Windows MAX_PATH.
    path = directory / f'{uuid.uuid4().hex}.json'
    document = {'schema_version': 1, 'symbol': symbol, 'provider': 'Yahoo Finance via yfinance',
                'source_url': f'https://finance.yahoo.com/quote/{_symbol(symbol)}/history/',
                'representation': 'provider-normalized daily history, not raw HTTP response',
                'query_start': start, 'query_end_exclusive': end, 'auto_adjust': False,
                'retrieved_at': at, 'available_at': at, 'sha256': digest, **_facts(clean)}
    directory.mkdir(parents=True, exist_ok=True)
    _atomic_write(path.with_suffix('.parquet'), raw)
    _atomic_write(path, json.dumps(document, allow_nan=False).encode('utf-8'))
    return path


def load_market_snapshots(symbol, root):
    docs = []
    for path in sorted((Path(root) / _symbol(symbol)).glob('*.json')):
        try:
            doc = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(doc, dict) or doc.get('schema_version') != 1 or doc.get('symbol') != symbol:
                raise ValueError('invalid market metadata identity')
            if doc['provider'] != 'Yahoo Finance via yfinance' or doc['source_url'] != f'https://finance.yahoo.com/quote/{_symbol(symbol)}/history/' or doc['auto_adjust'] is not False:
                raise ValueError('invalid market metadata provider')
            at = _timestamp(doc['retrieved_at']).isoformat()
            if doc['available_at'] != at:
                raise ValueError('invalid market metadata availability')
            raw = path.with_suffix('.parquet').read_bytes()
            if hashlib.sha256(raw).hexdigest() != doc['sha256']:
                raise ValueError('market hash mismatch')
            data = pd.read_parquet(path.with_suffix('.parquet'))
            _validate(data, symbol, doc['query_start'], doc['query_end_exclusive'], at)
            if any(doc.get(key) != value for key, value in _facts(data).items()):
                raise ValueError('market metadata does not match observations')
            docs.append({**doc, 'path': str(path.with_suffix('.parquet')), 'metadata_path': str(path)})
        except (KeyError, TypeError, OSError, ValueError) as exc:
            raise ValueError(f'invalid market evidence {path.name}: {exc}') from exc
    return docs


def select_market(symbol, root, start, end, *, mode='point_in_time', availability_end=None):
    if mode not in ('point_in_time', 'retrospective') or date.fromisoformat(start) > date.fromisoformat(end):
        raise ValueError('invalid market selection period/mode')
    cutoff_day = date.fromisoformat(availability_end or end)
    if cutoff_day < date.fromisoformat(end):
        raise ValueError('availability cutoff cannot precede interval end')
    cutoff = datetime.combine(cutoff_day, time(16, 30), ZoneInfo('America/New_York'))
    eligible = []
    for doc in load_market_snapshots(symbol, root):
        if mode == 'point_in_time' and datetime.fromisoformat(doc['available_at']) > cutoff:
            continue
        data = pd.read_parquet(doc['path'])
        days = set(data.index.strftime('%Y-%m-%d'))
        if start in days and end in days:
            eligible.append((doc, data))
    if not eligible:
        raise ValueError(f'no eligible market snapshot with exact endpoints: {symbol}')
    doc, data = max(eligible, key=lambda pair: (pair[0]['available_at'], pair[0]['metadata_path']))
    data.attrs['market_source'] = {**doc, 'availability_status':
        'capture time verified; original publication and revision times unverified'}
    return data


def capture_market(symbol, start, end, root, *, fetcher=None):
    _symbol(symbol)
    _bounds(start, end)
    if fetcher is None:
        # Neither offline selection nor report imports networking/proxy setup.
        import yfinance as yf
        from src.data import fetch
        cache = Path(root) / '_provider_cache'
        cache.mkdir(parents=True, exist_ok=True)
        yf.set_tz_cache_location(str(cache))
        fetcher = fetch
    data = fetcher(symbol, start, end)
    return store_market(symbol, data, root, start, end)


def action_summary(data, start, end):
    if date.fromisoformat(start) > date.fromisoformat(end):
        raise ValueError('invalid action window')
    window = data.loc[(data.index > pd.Timestamp(start)) & (data.index <= pd.Timestamp(end))]
    expected = mcal.get_calendar('NASDAQ').schedule(start_date=start, end_date=end).index
    missing_days = [day.date().isoformat() for day in expected
                    if day > pd.Timestamp(start) and day not in window.index]
    fields = ('dividends', 'capital gains', 'stock splits')
    missing = [field for field in fields if field not in window or window[field].isna().any()]
    events = []
    for day, row in window.iterrows():
        for field in fields:
            value = row.get(field)
            if value is not None and pd.notna(value):
                number = float(value)
                if not np.isfinite(number) or number < 0:
                    raise ValueError('invalid corporate action value')
                if number:
                    events.append({'date': day.date().isoformat(), 'field': field, 'value': number})
    return {'events': events, 'missing_fields': missing, 'missing_market_dates': missing_days,
            'dividend_per_share': None if 'dividends' in missing or missing_days else float(window['dividends'].sum()),
            'capital_gain_per_share': None if 'capital gains' in missing or missing_days else float(window['capital gains'].sum()),
            'limitations': ['provider close already reflects splits; split ratios are not reapplied',
                            'per-share cash events do not certify historical share basis or official total return']}
