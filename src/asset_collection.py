"""Repeatable manual collection and offline evidence inventory."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import uuid

import pandas as pd

from src.asset_market import _bounds, capture_market, load_market_snapshots
from src.asset_models import ASSET_KINDS
from src.asset_sources import SOURCE_SPECS, _atomic_write, capture_source, load_sources


def collect_assets(start, end, source_root, market_store, manifest_root, *,
                   with_constituents=False, source_capture=None, market_capture=None):
    _bounds(start, end)  # reject bad queries before the first network request
    source_capture = source_capture or capture_source
    market_capture = market_capture or capture_market
    source_root, market_store = Path(source_root), Path(market_store)
    result = {'schema_version': 1, 'started_at': datetime.now(timezone.utc).isoformat(),
              'query_start': start, 'query_end_exclusive': end, 'with_constituents': with_constituents,
              'source_root': str(source_root), 'market_store': str(market_store),
              'sources': [], 'markets': [], 'errors': [], 'historical_trade_backtest_ready': False}
    qqq = None
    for symbol in SOURCE_SPECS:
        try:
            path = source_capture(symbol, source_root)
            doc = json.loads(path.read_text(encoding='utf-8'))
            result['sources'].append({'symbol': symbol, 'status': 'saved', 'path': str(path),
                **{key: doc.get(key) for key in ('sha256', 'as_of', 'available_at')}})
            if symbol == 'QQQ':
                qqq = doc
        except Exception as exc:
            result['sources'].append({'symbol': symbol, 'status': 'failed', 'error': str(exc)})
    symbols = list(ASSET_KINDS)
    if with_constituents:
        if qqq is None:
            result['errors'].append('QQQ current capture failed; constituents not substituted from an older snapshot')
        else:
            symbols.extend(sorted({row['ticker'] for row in qqq['rows']
                                   if row['asset_class'] == 'Equity' and row.get('ticker')} - set(symbols)))
    for symbol in symbols:
        try:
            path = market_capture(symbol, start, end, market_store)
            doc = json.loads(path.read_text(encoding='utf-8'))
            result['markets'].append({'symbol': symbol, 'status': 'saved', 'path': str(path),
                **{key: doc.get(key) for key in ('sha256', 'available_at', 'row_count', 'first_date', 'last_date')}})
        except Exception as exc:
            result['markets'].append({'symbol': symbol, 'status': 'failed', 'error': str(exc)})
    failed = result['errors'] or any(item['status'] == 'failed' for group in ('sources', 'markets') for item in result[group])
    result['status'] = 'partial_failure' if failed else 'complete'
    result['completed_at'] = datetime.now(timezone.utc).isoformat()
    root = Path(manifest_root)
    root.mkdir(parents=True, exist_ok=True)
    path = root / f'{uuid.uuid4().hex}.json'
    result['manifest_path'] = str(path)
    _atomic_write(path, json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False).encode('utf-8'))
    return result


def inventory(source_root, market_store):
    result = {'schema_version': 1, 'generated_at': datetime.now(timezone.utc).isoformat(),
              'sources': {}, 'markets': {}, 'errors': [], 'historical_trade_backtest_ready': False,
              'limitations': ['repeated same-day captures are versions, not additional historical holdings days',
                              'capture timestamps do not certify original publication/revision timestamps']}
    symbols = set(ASSET_KINDS)
    for symbol in SOURCE_SPECS:
        try:
            docs = load_sources(symbol, source_root)
            result['sources'][symbol] = {'snapshot_count': len(docs),
                'as_of_days': sorted({doc['as_of'] for doc in docs}),
                'availability_times': sorted({doc['available_at'] for doc in docs})}
            if symbol == 'QQQ':
                symbols.update(row['ticker'] for doc in docs for row in doc['rows']
                               if row['asset_class'] == 'Equity' and row.get('ticker'))
        except (ValueError, OSError) as exc:
            result['sources'][symbol] = {'status': 'invalid', 'error': str(exc)}
            result['errors'].append(f'{symbol}: {exc}')
    for symbol in sorted(symbols):
        try:
            docs = load_market_snapshots(symbol, market_store)
            days = {day for doc in docs for day in pd.read_parquet(doc['path']).index.strftime('%Y-%m-%d')}
            result['markets'][symbol] = {'snapshot_count': len(docs), 'observation_days': sorted(days),
                                        'availability_times': sorted({doc['available_at'] for doc in docs})}
        except (ValueError, OSError) as exc:
            result['markets'][symbol] = {'status': 'invalid', 'error': str(exc)}
            result['errors'].append(f'{symbol}: {exc}')
    return result
