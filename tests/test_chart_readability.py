import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pytest

from src import kline,thresholds


def test_price_chart_never_loads_or_overlays_macro_calendar(monkeypatch):
    def forbidden(*args,**kwargs):
        raise AssertionError('macro events must not appear on price charts')
    monkeypatch.setattr(kline,'_draw_events',forbidden)
    fig,ax=plt.subplots()
    try:
        kline.plot_single('GC=F',ax,layer='commodities_futures')
        assert not any('event' in line.get_label() for line in ax.lines)
    finally:
        plt.close(fig)


@pytest.mark.parametrize('symbol,layer,unit',[
    ('GC=F','commodities_futures','USD/oz'),('GLD','commodities_spot_etf','USD/share')])
def test_latest_close_label_matches_price_date_and_instrument(symbol,layer,unit):
    data=thresholds.load_prices(symbol,layer)
    fig,ax=plt.subplots()
    try:
        kline.plot_single(symbol,ax,layer=layer)
        labels=[t.get_text() for t in ax.texts if (t.get_gid() or '').startswith('latest-close-label-')]
        assert len(labels)==1
        label=labels[0]
        assert f"{data['close'].iloc[-1]:,.2f}" in label
        assert str(data.index[-1].date()) in label
        assert symbol in label and unit in label and 'Last close' in label
        assert unit in ax.get_ylabel()
        assert 'SMA' not in ax.get_title()
    finally:
        plt.close(fig)


def test_long_window_price_extremes_are_not_clipped(monkeypatch):
    data=thresholds.load_prices('GC=F','commodities_futures').copy()
    # Earlier part of the displayed 500-row window lies below recent 252 rows.
    data.iloc[:-252,data.columns.get_indexer(['open','high','low','close'])]*=.1
    monkeypatch.setattr(kline,'load_prices',lambda *args:data)
    fig,ax=plt.subplots()
    try:
        kline.plot_single('GC=F',ax,layer='commodities_futures',lookback_days=500)
        low,high=ax.get_ylim()
        visible=data.iloc[-500:]
        assert low<=visible['low'].min() and high>=visible['high'].max()
    finally:
        plt.close(fig)


def test_gold_example_has_one_title_and_preserves_price_label(monkeypatch,tmp_path):
    from examples import gold_chart
    captured=[]
    def capture(fig,*args,**kwargs):
        captured.append(fig)
        return []
    monkeypatch.setattr(gold_chart,'savefig_multi_format',capture)
    monkeypatch.setattr(gold_chart,'__file__',str(tmp_path/'examples'/'gold_chart.py'))
    gold_chart.main()
    ax=captured[0].axes[0]
    assert not ax.get_title(loc='left')
    assert ax.get_title()
    assert any((t.get_gid() or '').startswith('latest-close-label-') for t in ax.texts)
