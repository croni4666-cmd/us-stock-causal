"""Official nominal par yield observations, with immutable capture evidence."""
from datetime import date, datetime, time, timezone
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import uuid
from zoneinfo import ZoneInfo

from src.asset_sources import MAX_BYTES, _atomic_write, _timestamp

NODES = {'6 Mo': .5, '1 Yr': 1., '2 Yr': 2., '3 Yr': 3., '5 Yr': 5.,
         '7 Yr': 7., '10 Yr': 10., '20 Yr': 20., '30 Yr': 30.}


def curve_url(year):
    if type(year) is not int or not 1990 <= year <= 2099:
        raise ValueError('invalid Treasury year')
    return (f'https://home.treasury.gov/resource-center/data-chart-center/interest-rates/'
            f'daily-treasury-rates.csv/{year}/all?_format=csv&field_tdr_date_value={year}&page=&type=daily_treasury_yield_curve')


def parse_curve(raw, year):
    curve_url(year)
    if not raw or len(raw) > MAX_BYTES:
        raise ValueError('invalid curve bytes')
    reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
    if not reader.fieldnames or not {'Date', *NODES}.issubset(reader.fieldnames) or len(set(reader.fieldnames)) != len(reader.fieldnames):
        raise ValueError('invalid nominal par curve columns')
    rows, days = [], set()
    for record in reader:
        if None in record or any(v is None for v in record.values()):
            raise ValueError('truncated Treasury CSV')
        day = datetime.strptime(record['Date'], '%m/%d/%Y').date()
        if day.year != year or day.isoformat() in days:
            raise ValueError('wrong year or duplicate curve date')
        rates = {}
        for node in NODES:
            value = record[node].strip()
            number = None if value in ('', 'N/A', '-') else float(value)
            if number is not None and (not math.isfinite(number) or abs(number) > 100):
                raise ValueError('invalid par rate')
            rates[node] = number
        days.add(day.isoformat())
        rows.append({'date': day.isoformat(), 'rates_pct': rates})
    if not rows:
        raise ValueError('empty curve CSV')
    return {'kind': 'nominal_par_curve', 'year': year, 'rows': sorted(rows, key=lambda r: r['date'])}


def store_curve(raw, year, root, *, retrieved_at=None):
    parsed = parse_curve(raw, year)
    at = _timestamp(retrieved_at or datetime.now(timezone.utc).isoformat())
    if parsed['rows'][-1]['date'] > at.date().isoformat():
        raise ValueError('curve observation after capture')
    folder = Path(root) / str(year)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f'{uuid.uuid4().hex}.json'
    doc = {**parsed, 'schema_version': 1, 'provider': 'U.S. Treasury', 'source_url': curve_url(year),
           'sha256': hashlib.sha256(raw).hexdigest(), 'retrieved_at': at.isoformat(), 'available_at': at.isoformat()}
    _atomic_write(path.with_suffix('.raw'), raw)
    _atomic_write(path, json.dumps(doc, allow_nan=False).encode('utf-8'))
    return path


def select_curve(root, start, end, *, mode='point_in_time'):
    if mode not in ('point_in_time', 'retrospective') or date.fromisoformat(start) > date.fromisoformat(end):
        raise ValueError('invalid curve period/mode')
    cutoff = datetime.combine(date.fromisoformat(end), time(16, 30), ZoneInfo('America/New_York'))
    selected, evidence = {}, []
    for year in sorted({date.fromisoformat(start).year, date.fromisoformat(end).year}):
        candidates = []
        required_days = {d for d in (start, end) if date.fromisoformat(d).year == year}
        for path in sorted((Path(root) / str(year)).glob('*.json')):
            try:
                doc = json.loads(path.read_text(encoding='utf-8'))
                if not isinstance(doc, dict) or doc.get('schema_version') != 1 or doc.get('source_url') != curve_url(year) or doc.get('provider') != 'U.S. Treasury':
                    raise ValueError('invalid curve metadata')
                raw = path.with_suffix('.raw').read_bytes()
                if hashlib.sha256(raw).hexdigest() != doc['sha256']:
                    raise ValueError('curve hash mismatch')
                parsed = parse_curve(raw, year)
                if any(doc.get(k) != v for k, v in parsed.items()):
                    raise ValueError('curve metadata differs from raw')
                at = _timestamp(doc['retrieved_at'])
                if doc['available_at'] != at.isoformat() or parsed['rows'][-1]['date'] > at.date().isoformat():
                    raise ValueError('invalid curve availability')
                if mode == 'point_in_time' and at > cutoff:
                    continue
                values = {r['date']: r['rates_pct'] for r in doc['rows']}
                if required_days.issubset(values):
                    candidates.append((at, doc, values))
            except (ValueError, KeyError, TypeError, OSError) as exc:
                raise ValueError(f'invalid curve evidence: {exc}') from exc
        if not candidates:
            raise ValueError('no eligible official curve with exact dates')
        _, doc, values = max(candidates, key=lambda c: c[0])
        for day in required_days:
            if any(values[day][n] is None for n in NODES):
                raise ValueError('complete curve nodes unavailable; no node filling')
            selected[day] = values[day]
        evidence.append({k: doc[k] for k in ('source_url', 'sha256', 'retrieved_at', 'available_at', 'year')})
    return {'start': selected[start], 'end': selected[end],
            'changes_bp': {n: (selected[end][n]-selected[start][n])*100 for n in NODES},
            'sources': evidence, 'kind': 'nominal_par_curve', 'causal_status': 'not_identified'}


def capture_curve(year, root, *, session=None):
    url = curve_url(year)
    from src import proxy  # explicit network action only
    import requests
    client = session or requests.Session()
    try:
        with client.get(url, timeout=(10, 40), stream=True) as response:
            response.raise_for_status()
            parts, size = [], 0
            for part in response.iter_content(chunk_size=65536):
                size += len(part)
                if size > MAX_BYTES:
                    raise ValueError('curve response too large')
                parts.append(part)
        return store_curve(b''.join(parts), year, root)
    finally:
        if session is None:
            client.close()
