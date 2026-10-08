import numpy as np
import pandas as pd
import pytest


def test_simple_returns_do_not_invent_missing_quotes():
    from src.returns import compute_returns
    result=compute_returns(pd.Series([100.,np.nan,110.]),'simple')
    assert result.isna().all()


def test_cumulative_return_rejects_internal_gaps():
    from src.returns import cumulative_return
    with pytest.raises(ValueError): cumulative_return(pd.Series([.01,np.nan,.02]),'simple')


@pytest.mark.parametrize('exit_code',[1,7,'provider failed'])
def test_daily_fetch_preserves_failure_exit_code(monkeypatch,exit_code):
    from examples import fetch_all,daily_report
    def fail(): raise SystemExit(exit_code)
    monkeypatch.setattr(fetch_all,'main',fail)
    assert daily_report.step_fetch()['ok'] is False


def test_daily_fetch_preserves_nonzero_return(monkeypatch):
    from examples import fetch_all,daily_report
    monkeypatch.setattr(fetch_all,'main',lambda:2)
    assert daily_report.step_fetch()['ok'] is False


def test_attribution_rejects_missing_constituent_return(monkeypatch):
    from src import attribution as a
    dates=pd.bdate_range('2026-01-02',periods=5)
    returns=pd.DataFrame({'QQQ':.01,'XLK':[.01,np.nan,.01,.01,.01]},index=dates)
    monkeypatch.setattr(a,'load_sector_weights',lambda **kwargs:{'QQQ':{'XLK':1.}})
    monkeypatch.setattr(a,'get_sector_returns',lambda *args,**kwargs:returns)
    with pytest.raises(ValueError): a.attribute_index('QQQ',date=str(dates[-1].date()),lookback_days=5)


def test_attribution_rejects_short_window(monkeypatch):
    from src import attribution as a
    returns=pd.DataFrame({'QQQ':[.01,.02],'XLK':[.01,.02]},index=pd.bdate_range('2026-01-02',periods=2))
    monkeypatch.setattr(a,'load_sector_weights',lambda **kwargs:{'QQQ':{'XLK':1.}})
    monkeypatch.setattr(a,'get_sector_returns',lambda *args,**kwargs:returns)
    with pytest.raises(ValueError): a.attribute_index('QQQ',lookback_days=5)


def test_attribution_simple_method_is_not_mislabeled_log(monkeypatch):
    from src import attribution as a
    returns=pd.DataFrame({'QQQ':[np.log(1.1)],'XLK':[np.log(1.1)]},index=pd.to_datetime(['2026-01-02']))
    monkeypatch.setattr(a,'load_sector_weights',lambda **kwargs:{'QQQ':{'XLK':1.}})
    monkeypatch.setattr(a,'get_sector_returns',lambda *args,**kwargs:returns)
    assert a.attribute_index('QQQ',method='simple')['actual_return_pct']==pytest.approx(10.)


def test_market_segment_refuses_partial_five_day_value(monkeypatch):
    from src import report
    df=pd.DataFrame({'close':[100.,101.,np.nan,103.,104.,105.]},index=pd.bdate_range('2026-01-02',periods=6))
    monkeypatch.setattr(report,'load_prices',lambda *args:df)
    assert '无法完整计算' in report._segment_1_market('QQQ','indices',5)


def test_official_xlsx_xml_rejects_entity_and_dtd_declarations():
    from src.asset_sources import _safe_xml
    raw=b'<!DOCTYPE workbook [<!ENTITY test "invented">]><workbook>&test;</workbook>'
    with pytest.raises(ValueError,match='Unsafe issuer XML'):
        _safe_xml(raw)


def test_historical_cache_request_does_not_return_future_quotes(tmp_path):
    from src.cache import update_or_fetch,cache_path
    data=pd.DataFrame({'close':[100.,101.,102.]},index=pd.to_datetime(['2026-10-01','2026-10-02','2026-10-05']))
    path=cache_path('QQQ','indices',tmp_path);data.to_parquet(path)
    calls=[]
    def fetch(*args,**kwargs): calls.append(kwargs);return pd.DataFrame()
    result,status=update_or_fetch('QQQ','indices',fetch,tmp_path,end='2026-10-03')
    assert result.index[-1]==pd.Timestamp('2026-10-02')
    assert not calls and status=='cached'
    pd.testing.assert_frame_equal(pd.read_parquet(path),data)


def test_cache_without_end_fetches_and_writes_full_history(tmp_path):
    from src.cache import update_or_fetch,cache_path
    data=pd.DataFrame({'close':[100.,101.]},index=pd.to_datetime(['2026-01-02','2026-01-05']))
    result,status=update_or_fetch('QQQ','indices',lambda *a,**k:data,tmp_path)
    assert status=='full'
    pd.testing.assert_frame_equal(result,data)
    pd.testing.assert_frame_equal(pd.read_parquet(cache_path('QQQ','indices',tmp_path)),data)


def test_cache_empty_provider_result_is_not_full_success(tmp_path):
    from src.cache import update_or_fetch
    result,status=update_or_fetch('QQQ','indices',lambda *a,**k:pd.DataFrame(),tmp_path)
    assert result.empty and status=='empty'


def test_pc_cache_does_not_reuse_other_node_names_or_test_protocol(monkeypatch):
    from src import causal
    import importlib
    from types import SimpleNamespace
    pc_module=importlib.import_module('causallearn.search.ConstraintBased.PC')
    calls=[]
    def pc(values,**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(G=SimpleNamespace(graph=np.zeros((2,2))))
    monkeypatch.setattr(pc_module,'pc',pc);causal.clear_caches()
    data=pd.DataFrame({'T':[1.,2.,3.],'Y':[2.,3.,4.]})
    causal.discover_dag_pc(data)
    renamed=data.rename(columns={'T':'X','Y':'Z'})
    assert set(causal.discover_dag_pc(renamed).nodes())=={'X','Z'}
    causal.discover_dag_pc(renamed,indep_test='gsq')
    assert len(calls)==3


def test_daily_cate_labels_actual_log_change_unit(monkeypatch,capsys):
    from src import causal
    from examples import daily_report
    from types import SimpleNamespace
    import networkx as nx
    monkeypatch.setenv('US_STOCK_CAUSAL_FAST','1')
    data=pd.DataFrame({'VIX':[-.02,.03],'QQQ':[.01,-.01]},index=pd.to_datetime(['2026-01-02','2026-01-05']))
    monkeypatch.setattr(causal,'load_dag_config',lambda:{})
    monkeypatch.setattr(causal,'load_dag_data',lambda **kwargs:data)
    monkeypatch.setattr(causal,'discover_dag_pc',lambda *a,**k:nx.DiGraph())
    monkeypatch.setattr(causal,'load_dag_graph',lambda *a,**k:nx.DiGraph())
    monkeypatch.setattr(causal,'compare_dags',lambda *a:{'summary':'unverified','overlap':[],'pc_only':[]})
    effect=SimpleNamespace(estimate=-.2,p_value=.1,n_obs=2,refutation={},identification_status='identified',
        treatment='VIX',outcome='QQQ',interpretation='conditional',to_dict=lambda:{'epistemic_assessment':{'causal_status':'not_established'}})
    monkeypatch.setattr(causal,'causal_query',lambda **kwargs:effect)
    monkeypatch.setattr(causal,'cate_heterogeneity',lambda **kwargs:[{'cate':-.2,'quantile':1,'label':'low','n_obs':2,'range':[-.02,.03]}])
    result=daily_report.step_causal('2026-01-05');text=capsys.readouterr().out
    assert result['ok'] is True
    assert '日对数变化' in text and 'VIX 水平' not in text
    assert 'VIX log-change range [-0.0200, +0.0300]' in text
