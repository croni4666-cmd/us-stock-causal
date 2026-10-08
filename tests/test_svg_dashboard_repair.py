import json
import re
import numpy as np
import pandas as pd
import pytest


def frame(level=100.,doji=False):
    return pd.DataFrame({'open':[level,level+1],'high':[level+2,level+3],
        'low':[level-1,level], 'close':[level if doji else level+1,level+2],
        'volume':[np.nan,12345.]},index=pd.to_datetime(['2026-10-01','2026-10-02']))


def svg_fixture(tmp_path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from src.kline import plot_single,savefig_multi_format
    fig,axes=plt.subplots(1,2)
    for ax,symbol,data in zip(axes,('QQQ','GLD'),(frame(100),frame(200,True))):
        plot_single(symbol,ax,data=data,sma_windows=(),show_pivots=False,ma_review=False)
    path=tmp_path/'multi.svg'
    savefig_multi_format(fig,path,formats=('svg',))
    return fig,path


def test_svg_ids_and_local_references_are_unique_and_resolvable(tmp_path):
    from lxml import etree
    import matplotlib.pyplot as plt
    fig,path=svg_fixture(tmp_path)
    try:
        tree=etree.parse(str(path)); ids=[e.get('id') for e in tree.iter() if e.get('id')]
        assert len(ids)==len(set(ids))
        for element in tree.iter():
            for key,value in element.attrib.items():
                refs=re.findall(r'url\(#([^)]+)\)',value)
                if key.endswith('href') and value.startswith('#'): refs.append(value[1:])
                assert all(ref in ids for ref in refs)
    finally: plt.close(fig)


def test_each_candle_including_doji_has_source_ohlcv_and_its_own_unit(tmp_path):
    from lxml import etree
    import matplotlib.pyplot as plt
    fig,path=svg_fixture(tmp_path)
    try:
        tree=etree.parse(str(path)); checked=0
        for element in tree.iter():
            raw=element.get('data-ohlcv')
            if not raw: continue
            source=json.loads(raw)
            expected=frame(100) if source['symbol']=='QQQ' else frame(200,True)
            row=expected.loc[source['date']]
            assert all(source[field]==row[field] for field in ('open','high','low','close'))
            assert source['volume'] is None if pd.isna(row['volume']) else source['volume']==row['volume']
            assert source['unit']=='USD/share'
            title=element.find('{http://www.w3.org/2000/svg}title').text
            assert source['symbol'] in title and 'Open' in title and 'Close' in title
            checked+=1
        assert checked==8  # body and wick for both observations in both panels
    finally: plt.close(fig)


def test_repeated_svg_embedding_does_not_duplicate_ids(tmp_path):
    from lxml import html
    from src.report_html import render_html_report
    import matplotlib.pyplot as plt
    fig,path=svg_fixture(tmp_path)
    try:
        doc=html.fromstring(render_html_report('review',[path,path]))
        ids=doc.xpath('//@id')
        assert len(ids)==len(set(ids))
    finally: plt.close(fig)


@pytest.mark.parametrize('symbol,layer,levels,unit,delta',[
    ('^TNX','macro',[4.,4.03],'bp',3.),('^VIX','macro',[20.,25.],'VIX points',5.),
    ('DXY','macro',[100.,101.],'index points',1.),('QQQ','indices',[100.,101.],'%',1.)])
def test_dashboard_reports_declared_metric_instead_of_mixed_price_returns(monkeypatch,symbol,layer,levels,unit,delta):
    from src import performance_dashboard as dashboard
    data=frame(); data['close']=levels
    monkeypatch.setattr(dashboard,'load_prices',lambda *args:data)
    result=dashboard.compute_1d_change(symbol,layer)
    assert result['change_unit']==unit and result['change_value']==pytest.approx(delta)
    assert result['date']=='2026-10-02' and result['previous_date']=='2026-10-01'
    text=dashboard.render_performance_table([(layer,symbol)])
    assert unit in text and '现价 (USD)' not in text


def test_macro_outlier_is_separate_from_price_bar_scale(monkeypatch):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from src import performance_dashboard as dashboard
    def load(symbol,layer):
        data=frame(); data['close']=[100.,101.] if symbol=='QQQ' else [20.,40.]
        return data
    monkeypatch.setattr(dashboard,'load_prices',load)
    fig,ax=plt.subplots()
    try:
        dashboard.plot_performance_dashboard(ax,symbols=[('indices','QQQ'),('macro','^VIX')])
        prices=ax._performance_panels['prices']
        assert len(prices.patches)==1 and prices.patches[0].get_width()==pytest.approx(1.)
        assert prices.get_xlim()[1]<5
        assert len(ax._performance_panels['macro'])==1
    finally: plt.close(fig)

def test_svg_reinjection_replaces_titles_and_keeps_raw_observations(tmp_path):
    from lxml import etree
    from src.kline import _inject_ohlcv_hover
    import matplotlib.pyplot as plt
    fig,path=svg_fixture(tmp_path)
    try:
        assert _inject_ohlcv_hover(path,fig)==8
        tree=etree.parse(str(path))
        candles=[e for e in tree.iter() if e.get('data-ohlcv')]
        assert len(candles)==8
        assert all(len(e.findall('{http://www.w3.org/2000/svg}title'))==1 for e in candles)
        assert fig._svg_export_status[str(path.resolve())]['source_metadata_verified']
    finally: plt.close(fig)


def test_zero_yield_level_has_basis_point_change_without_relative_return(monkeypatch):
    from src import performance_dashboard as dashboard
    data=frame(); data['close']=[0.,.01]
    monkeypatch.setattr(dashboard,'load_prices',lambda *args:data)
    row=dashboard.compute_1d_change('^TNX','macro')
    assert row['change_value']==pytest.approx(1.) and row['change_pct'] is None
    assert '+1.00 bp' in dashboard.render_performance_table([('macro','^TNX')])


def test_dashboard_rejects_ambiguous_dates_and_nonfinite_quotes(monkeypatch):
    from src import performance_dashboard as dashboard
    for data in (frame().set_axis(pd.to_datetime(['2026-10-02','2026-10-02'])),frame().assign(close=[100.,np.nan])):
        monkeypatch.setattr(dashboard,'load_prices',lambda *args:data)
        assert dashboard.compute_1d_change('QQQ','indices') is None
