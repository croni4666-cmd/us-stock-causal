"""Experimental fixed cashflow/par-node mechanics; not official ETF valuation."""
import calendar
import csv
from datetime import date, datetime
import hashlib
import io
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from src.asset_sources import parse_ishares, load_sources
from src.treasury_curve import NODES


def bootstrap(rates):
    values = np.array([float(rates[node]) if rates.get(node) is not None else np.nan for node in NODES])
    if not np.isfinite(values).all() or (abs(values) > 100).any():
        raise ValueError('complete finite par nodes required')
    grid = np.arange(.5, 30.01, .5)
    coupons = np.interp(grid, list(NODES.values()), values) / 200
    discounts = [1.]
    for coupon in coupons:
        df = (1 - coupon * sum(discounts[1:])) / (1 + coupon)
        if not math.isfinite(df) or df <= 0:
            raise ValueError('par bootstrap produced nonpositive discount factor')
        discounts.append(df)
    return np.asarray(discounts)


def bond_price(terms, valuation, discounts):
    at, maturity = pd.Timestamp(date.fromisoformat(valuation)), pd.Timestamp(date.fromisoformat(terms['maturity']))
    coupon = terms.get('coupon_pct')
    if coupon is None or not math.isfinite(float(coupon)) or not 0 <= float(coupon) <= 100 or maturity <= at:
        raise ValueError('unsupported coupon or maturity')
    if len(discounts) != 61 or not np.isfinite(discounts).all() or (np.asarray(discounts) <= 0).any() or discounts[0] != 1:
        raise ValueError('invalid discount curve')
    end_of_month = maturity.day == calendar.monthrange(maturity.year, maturity.month)[1]
    dates, k = [], 0
    while True:
        payment = maturity - pd.DateOffset(months=6*k)
        if end_of_month:
            payment += pd.offsets.MonthEnd(0)
        if payment <= at:
            previous = payment
            break
        dates.append(payment)
        k += 1
        if k > 62:
            raise ValueError('cashflows exceed30-year modeled range')
    dates.reverse()
    accrual = terms.get('accrual_date')
    if not accrual or pd.Timestamp(date.fromisoformat(accrual)) > previous:
        raise ValueError('missing accrual date or unsupported irregular first coupon')
    accrual_day = pd.Timestamp(date.fromisoformat(accrual))
    months = (maturity.year-accrual_day.year)*12 + maturity.month-accrual_day.month
    expected_accrual = maturity-pd.DateOffset(months=months)
    if end_of_month:
        expected_accrual += pd.offsets.MonthEnd(0)
    # Without first-payment evidence an off-cycle dated date may still describe
    # an upcoming long coupon; do not invent the previous payment boundary.
    if months < 0 or months % 6 or accrual_day != expected_accrual:
        raise ValueError('unverified irregular coupon schedule')
    fraction = (dates[0]-at).days/(dates[0]-previous).days
    times = .5*(fraction+np.arange(len(dates)))
    if times[-1] > 30:
        raise ValueError('cashflow beyond modeled curve; no extrapolation')
    factors = np.exp(np.interp(times, np.arange(0,30.01,.5), np.log(discounts)))
    amounts = np.full(len(times), float(coupon)/2)
    amounts[-1] += 100
    return float(np.dot(amounts, factors))


def parse_bond_terms(raw, symbol):
    base = parse_ishares(raw, symbol)  # preserve old source schema and identity checks
    records = list(csv.reader(io.StringIO(raw.decode('utf-8-sig'))))
    start = next(i for i,r in enumerate(records) if r and r[0]=='Name' and 'Weight (%)' in r)
    details = {row['id']: row for row in base['rows']}
    terms = []
    for record in records[start+1:]:
        if not record or not any(record): break
        item = dict(zip(records[start],record))
        if item['Asset Class'] != 'Fixed Income': continue
        row = details[item['CUSIP']]
        supported = (item.get('Sector') == 'Treasuries' and item.get('Currency') == 'USD' and
                     item['Name'].startswith(('TREASURY NOTE','TREASURY BOND')) and
                     not any(word in item['Name'] for word in ('CPI','FLOAT','STRIP')))
        def field_day(field):
            value = item.get(field, '-')
            return None if value in ('','-') else datetime.strptime(value,'%b %d, %Y').date().isoformat()
        value = item.get('Coupon (%)','-')
        coupon = None if value in ('','-','N/A') or not supported else float(value)
        if coupon is not None and (not math.isfinite(coupon) or not 0 <= coupon <= 100):
            raise ValueError('invalid issuer coupon')
        terms.append({'id':row['id'], 'weight':row['weight'], 'coupon_pct':coupon,
                      'maturity':field_day('Maturity'), 'accrual_date':field_day('Accrual Date')})
    return terms


def source_bond_terms(symbol, root, doc):
    # The caller's selected source must match an independently validated envelope.
    if doc not in load_sources(symbol, root):
        raise ValueError('selected holdings not in validated source inventory')
    for path in (Path(root)/symbol).glob('*.json'):
        saved=json.loads(path.read_text(encoding='utf-8'))
        if saved == doc:
            raw=path.with_suffix('.raw').read_bytes()
            if hashlib.sha256(raw).hexdigest() != doc['sha256']:
                raise ValueError('bond terms raw hash mismatch')
            return parse_bond_terms(raw,symbol)
    raise ValueError('bond terms source missing')


def curve_repricing(terms, valuation, start_curve, end_curve):
    before, after = bootstrap(start_curve), bootstrap(end_curve)
    bumps = {node: (bootstrap({**start_curve,node:start_curve[node]+.01}),
                    bootstrap({**start_curve,node:start_curve[node]-.01})) for node in NODES}
    covered, effect, missing, rows = 0., 0., [], []
    sensitivities = dict.fromkeys(NODES,0.)
    for term in terms:
        try:
            weight=term['weight']
            if weight is None or not math.isfinite(weight) or weight < 0:
                raise ValueError('invalid bond weight')
            price = bond_price(term,valuation,before)
            change = bond_price(term,valuation,after)/price-1
            key_rates = {node: -(bond_price(term,valuation,up)-bond_price(term,valuation,down))/(2*.0001*price)
                         for node,(up,down) in bumps.items()}
        except (ValueError, KeyError, TypeError):
            missing.append(term.get('id','unknown')); continue
        covered += weight
        effect += weight*change
        for node,value in key_rates.items(): sensitivities[node]+=weight*value
        rows.append({'id':term['id'],'weight':weight,'model_dirty_price_per100':price,
                     'model_price_change':change,'contribution':weight*change})
    linear = -sum(sensitivities[n]*(end_curve[n]-start_curve[n])/100 for n in NODES)
    return {'status':'approximation' if rows else 'unavailable', 'method':'fixed-date cashflow repricing on experimental par-bootstrap curve',
            'valuation_date':valuation,'covered_weight':covered,'weight_gap_from_one':1-covered,
            'missing_ids':missing,'bonds':rows,'estimated_price_effect':effect if rows else None,
            'key_rate_durations':sensitivities,'linear_curve_effect':linear if rows else None,
            'nonlinear_remainder':effect-linear if rows else None,'causal_status':'not_identified',
            'limitations':['linear par interpolation on semiannual grid; log discount interpolation; not official Treasury zero curve',
                          'issuer displayed coupons are rounded; security terms not independently certified',
                          'fixed date excludes carry/rolldown, cash, fees, distributions, rebalancing and payment-date shifts',
                          'uncovered weights are not renormalized; this is a covered-portfolio sensitivity, not official ETF total return']}
