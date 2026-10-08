import pandas as pd
import pytest

from examples.asset_report import main
from src.asset_report import build_asset_report, render_asset_report
from src.asset_sources import parse_ishares, store_source
from src.treasury_curve import NODES, store_curve


def inputs(tmp_path):
    raw=(b'iShares 7-10 Year Treasury Bond ETF\nFund Holdings as of,"Oct 01, 2026"\n'
        b'Name,Sector,Asset Class,Weight (%),CUSIP,Duration,YTM (%),Maturity,Coupon (%),Accrual Date,Currency\n'
        b'TREASURY NOTE,Treasuries,Fixed Income,100,ABC,7,4,"Oct 01, 2030",4,"Oct 01, 2020",USD\n')
    store_source('IEF',raw,parse_ishares(raw,'IEF'),tmp_path/'s',retrieved_at='2026-10-03T12:00:00+00:00')
    csv=','.join(['Date']+list(NODES))+'\n10/01/2026,'+','.join(['4']*len(NODES))+'\n10/02/2026,'+','.join(['4.1']*len(NODES))+'\n'
    store_curve(csv.encode(),2026,tmp_path/'c',retrieved_at='2026-10-03T12:00:00+00:00')
    (tmp_path/'m').mkdir()
    for symbol,values in [('IEF',[100,99]),('_TNX',[4,4.1])]:
        pd.DataFrame({'close':values},index=pd.to_datetime(['2026-10-01','2026-10-02'])).to_parquet(tmp_path/'m'/f'{symbol}.parquet')


def test_report_retains_proxy_and_adds_distinct_experimental_curve_model(tmp_path):
    inputs(tmp_path)
    result=build_asset_report(['IEF'],'2026-10-01','2026-10-02',tmp_path/'m',tmp_path/'s',mode='retrospective',curve_root=tmp_path/'c')
    asset=result['assets'][0]
    assert asset['attribution']['yield_proxy']=='^TNX'
    assert asset['curve_model']['estimated_price_effect'] < 0
    assert asset['curve_model']['covered_weight']==1.
    assert asset['curve_model']['residual']==pytest.approx(-.01-asset['curve_model']['estimated_price_effect'])
    assert '现金流' in render_asset_report(result)
    assert result['historical_trade_backtest_ready'] is False


def test_missing_curve_does_not_erase_proxy_model(tmp_path):
    inputs(tmp_path)
    result=build_asset_report(['IEF'],'2026-10-01','2026-10-02',tmp_path/'m',tmp_path/'s',mode='retrospective',curve_root=tmp_path/'missing')
    assert result['assets'][0]['curve_model']['status']=='unavailable'
    assert result['assets'][0]['attribution']['status']=='approximation'


def test_curve_model_does_not_require_single_tenor_yahoo_proxy(tmp_path):
    inputs(tmp_path); (tmp_path/'m'/'_TNX.parquet').unlink()
    result=build_asset_report(['IEF'],'2026-10-01','2026-10-02',tmp_path/'m',tmp_path/'s',mode='retrospective',curve_root=tmp_path/'c')
    assert result['assets'][0]['curve_model']['status']=='approximation'


def test_cli_curve_sync_and_report_option(tmp_path,monkeypatch):
    from examples import asset_report
    monkeypatch.setattr(asset_report,'capture_curve',lambda *a,**k: tmp_path/'curve.json')
    assert main(['curve-sync','--years','2026','--curve-root',str(tmp_path/'c')])==0
    inputs(tmp_path)
    assert main(['report','--symbols','IEF','--start','2026-10-01','--end','2026-10-02','--mode','retrospective',
                 '--market-root',str(tmp_path/'m'),'--source-root',str(tmp_path/'s'),'--curve-root',str(tmp_path/'c'),
                 '--output',str(tmp_path/'report.md')])==0
