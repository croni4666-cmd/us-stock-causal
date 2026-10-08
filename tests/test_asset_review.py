"""Regressions reproduced by the gold/Treasury/Nasdaq live audit."""
from pathlib import Path
import shutil
import numpy as np
import pandas as pd
import pytest
from src import causal, patterns, report, signals, thresholds

@pytest.mark.parametrize('symbol,layer', [('GC=F','commodities_futures'),('GLD','commodities_spot'),('IEF','indices'),('TLT','indices'),('^IXIC','indices'),('^NDX','indices'),('^TNX','macro'),('XLK','sectors')])
def test_reports_follow_each_assets_actual_cache_layer(market_root,symbol,layer):
    path=market_root/'data/raw'/layer/f'{thresholds.safe_name(symbol)}.parquet'
    if not path.exists():
        path.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(market_root/'data/raw/indices/QQQ.parquet',path)
    result=report.five_segment_report(symbol,as_of='2026-07-24')
    assert result['symbol']==symbol
    assert all(isinstance(result[f'segment_{n}_{name}'],str) for n,name in [(1,'market'),(2,'attribution'),(3,'thresholds'),(4,'patterns'),(5,'risk')])
    assert '不适用' in result['segment_2_attribution']
    if symbol!='^TNX':
        assert patterns.find_similar_patterns(symbol)['n_matches']>0
        assert signals.aggregate_signals(symbol).symbol==symbol


def test_treasury_report_uses_yield_and_basis_points(market_root,tmp_path,monkeypatch):
    path=market_root/'data/raw/macro/_TNX.parquet'
    df=pd.read_parquet(path)
    df['close']=np.linspace(3.8,4.1,len(df))
    df.loc[df.index[-6:],'close']=[4.0,4.01,4.02,4.03,4.04,4.1]
    df['open']=df.close;df['high']=df.close+.01;df['low']=df.close-.01
    isolated=tmp_path/'macro/_TNX.parquet'
    isolated.parent.mkdir()
    df.to_parquet(isolated)
    monkeypatch.setattr(thresholds,'CACHE_ROOT',tmp_path)
    result=report.five_segment_report('^TNX',layer='macro',as_of='2026-07-24')
    assert '+10.00bp' in result['segment_1_market']
    assert '4.10%' in result['segment_3_thresholds']
    assert '$' not in result['segment_3_thresholds']
    assert 'win ' not in result['segment_4_patterns']
    assert 'IEF / TLT' in result['segment_4_patterns']
    assert '收益率' in result['segment_5_risk']


@pytest.mark.parametrize('method',['l2','econml'])
def test_no_directed_path_cannot_be_reported_as_causal_effect(method):
    rng=np.random.default_rng(84);t=rng.normal(size=400)
    data=pd.DataFrame({'T':t,'Y':2*t+rng.normal(scale=.01,size=400)},index=pd.bdate_range('2024-01-01',periods=400))
    cfg={'dot':'digraph { T; Y; }'}
    with pytest.raises(ValueError,match='有向路径'):
        if method=='l2':causal.causal_query('T','Y',data=data,cfg=cfg,n_refutations=0)
        else:causal.counterfactual_query(str(data.index[-1].date()),'T','Y',.01,data=data,cfg=cfg,method='econml')


@pytest.mark.parametrize('avg,win',[(.1,.9),(-.1,.1)])
def test_pattern_signal_respects_half_percent_threshold(avg,win):
    signal=signals._classify_pattern({'avg_forward_return':avg,'win_rate':win,'n_matches':10})
    assert signal.direction=='neutral'


def test_full_report_can_mix_stock_gold_and_treasury_layers():
    text = report.render_full_report(['QQQ', 'GLD', '^TNX'], as_of='2026-07-24')
    assert '## QQQ' in text
    assert '## GLD' in text
    assert '## ^TNX' in text
    assert 'bp' in text


def test_l3_report_names_its_actual_scm_method():
    text = report.render_causal_section(include_l3=True, as_of='2026-07-24')
    assert 'DoWhy SCM' in text
    assert '用 econml CATE' not in text


def test_causal_report_describes_loaded_graph_and_return_quantiles():
    text = report.render_causal_section(as_of='2026-07-24')
    assert '47 个节点' in text
    assert '172 条边' in text
    assert 'VIX 日对数变化' in text
    assert '跨 VIX 水平' not in text
    assert '不能验证因果方向' in text
