import math
import pandas as pd
import pytest

from src.treasury_curve import NODES
from src.treasury_pricing import bootstrap, bond_price, curve_repricing, parse_bond_terms


def flat(rate=4.): return {n: rate for n in NODES}
def bond(**changes):
    result={'id':'ABC','weight':.9,'coupon_pct':4.,'maturity':'2030-10-01','accrual_date':'2020-10-01'}
    result.update(changes); return result


def test_flat_curve_recovers_par_and_zero_coupon_discount():
    discounts=bootstrap(flat())
    assert discounts[-1] == pytest.approx(1.02**-60)
    assert bond_price(bond(), '2026-10-01', discounts) == pytest.approx(100.)
    assert bond_price(bond(coupon_pct=0), '2026-10-01', discounts) == pytest.approx(100/1.02**8)


def test_off_coupon_actual_actual_fraction_matches_flat_yield_formula():
    valuation=pd.Timestamp('2026-11-01'); previous=pd.Timestamp('2026-10-01'); following=pd.Timestamp('2027-04-01')
    fraction=(following-valuation).days/(following-previous).days
    expected=sum((2 + (100 if k==7 else 0))/1.02**(fraction+k) for k in range(8))
    assert bond_price(bond(),str(valuation.date()),bootstrap(flat()))==pytest.approx(expected)


@pytest.mark.parametrize('terms', [bond(maturity='2026-09-30'),bond(maturity='2060-10-01'),
                                  bond(coupon_pct=None),bond(coupon_pct=math.nan),
                                  bond(accrual_date='2026-11-01')])
def test_unpriceable_terms_rejected(terms):
    with pytest.raises(ValueError): bond_price(terms,'2026-10-01',bootstrap(flat()))


def test_parallel_and_nonparallel_shocks_are_actual_repricing_not_maturity_buckets():
    result=curve_repricing([bond()], '2026-10-01', flat(), flat(4.1))
    assert result['covered_weight']==.9 and result['weight_gap_from_one']==pytest.approx(.1)
    assert result['estimated_price_effect'] < 0
    assert result['key_rate_durations']['5 Yr'] > result['key_rate_durations']['30 Yr']
    assert abs(result['nonlinear_remainder']) < .0001
    unchanged=curve_repricing([bond()],'2026-10-01',flat(),flat())
    assert unchanged['estimated_price_effect']==pytest.approx(0.)
    steep=flat(); steep['30 Yr']=5.
    assert curve_repricing([bond()],'2026-10-01',flat(),steep)['estimated_price_effect']==pytest.approx(0.)


def test_bad_terms_are_uncovered_without_weight_renormalization():
    result=curve_repricing([bond(weight=.6),bond(id='MISSING',weight=.3,coupon_pct=None)],'2026-10-01',flat(),flat(4.1))
    assert result['covered_weight']==.6
    assert result['missing_ids']==['MISSING']
    assert result['weight_gap_from_one']==pytest.approx(.4)


def test_incomplete_and_impossible_par_curves_refused():
    missing=flat(); missing['10 Yr']=None
    with pytest.raises(ValueError): bootstrap(missing)
    impossible=flat(); impossible['30 Yr']=99.
    with pytest.raises(ValueError): bootstrap(impossible)


def test_terms_read_same_official_raw_and_reject_tips():
    raw=(b'iShares 7-10 Year Treasury Bond ETF\nFund Holdings as of,"Oct 01, 2026"\n'
        b'Name,Sector,Asset Class,Weight (%),CUSIP,Duration,YTM (%),Maturity,Coupon (%),Accrual Date,Currency\n'
        b'TREASURY NOTE,Treasuries,Fixed Income,60,ABC,7,4,"Oct 01, 2030",4.13,"Oct 01, 2020",USD\n'
        b'TREASURY CPI NOTE,Treasuries,Fixed Income,40,DEF,7,4,"Oct 01, 2030",2,"Oct 01, 2020",USD\n')
    result=parse_bond_terms(raw,'IEF')
    assert result[0]['coupon_pct']==4.13
    assert result[1]['coupon_pct'] is None


def test_end_month_coupon_schedule_handles_february_and_leap_year():
    term=bond(maturity='2030-02-28',accrual_date='2020-02-29')
    assert bond_price(term,'2026-08-31',bootstrap(flat()))==pytest.approx(100.)


def test_reported_weight_gap_keeps_rounding_and_is_not_labeled_unknown_cash():
    result=curve_repricing([bond(weight=1.0001)],'2026-10-01',flat(),flat())
    assert result['weight_gap_from_one']==pytest.approx(-.0001)
    assert 'uncovered_weight' not in result


def test_uncertain_upcoming_long_first_coupon_is_not_given_regular_payment():
    term=bond(accrual_date='2026-03-15')
    with pytest.raises(ValueError, match='coupon'):
        bond_price(term,'2026-04-02',bootstrap(flat()))
    result=curve_repricing([term],'2026-04-02',flat(),flat())
    assert result['status']=='unavailable' and result['covered_weight']==0
