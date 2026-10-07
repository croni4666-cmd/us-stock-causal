import json
import numpy as np
import pandas as pd
import pytest


def prices(previous=100.,latest=100.,n=202):
    values=np.full(n,100.)
    values[-2:]=[previous,latest]
    return pd.DataFrame({'close':values},index=pd.bdate_range('2025-01-02',periods=n))


@pytest.mark.parametrize('previous,latest,event',[(90,110,'crossed_above'),(110,90,'crossed_below'),
                                                (101,102,'none'),(100,100,'touch')])
def test_latest_cross_uses_price_against_each_dates_own_unrounded_mean(previous,latest,event):
    from src.chart_review import analyze_ma_crossings
    data=prices(previous,latest)
    result=analyze_ma_crossings(data,'GC=F','USD/oz')
    assert [r['window'] for r in result['moving_averages']]==[50,100,200]
    for row in result['moving_averages']:
        assert row['latest_event']==event
        assert row['previous_sma']==pytest.approx(data['close'].iloc[:-1].tail(row['window']).mean())
        assert row['sma']==pytest.approx(data['close'].tail(row['window']).mean())


def test_above_mean_is_not_reported_as_a_new_breakout():
    from src.chart_review import analyze_ma_crossings,render_ma_review
    result=analyze_ma_crossings(prices(101,102),'QQQ','USD/share')
    assert all(r['position']=='above' and r['latest_event']=='none' for r in result['moving_averages'])
    report=render_ma_review([result])
    assert '上方' in report and '未发生收盘穿越' in report


def test_just_enough_current_history_does_not_invent_previous_mean():
    from src.chart_review import analyze_ma_crossings
    result=analyze_ma_crossings(prices(n=50),'GLD','USD/share')
    first=result['moving_averages'][0]
    assert first['sma']==100 and first['previous_sma'] is None
    assert first['latest_event']=='unavailable'
    assert result['moving_averages'][1]['sma'] is None
    assert result['moving_averages'][1]['recent_pairs_evaluated']==0
    json.dumps(result,allow_nan=False)


def test_touching_then_leaving_line_is_not_a_confirmed_cross():
    from src.chart_review import analyze_ma_crossings
    result=analyze_ma_crossings(prices(100,101),'GC=F','USD/oz')
    assert all(r['latest_event']=='departed_above' for r in result['moving_averages'])


def test_as_of_ignores_future_prices_and_reports_recent_cross_date():
    from src.chart_review import analyze_ma_crossings
    data=prices(90,110)
    cutoff=str(data.index[-2].date())
    before=analyze_ma_crossings(data,'GC=F','USD/oz',as_of=cutoff)
    data.loc[data.index[-1],'close']=9999
    assert before==analyze_ma_crossings(data,'GC=F','USD/oz',as_of=cutoff)
    data.loc[data.index[-1],'close']=110
    result=analyze_ma_crossings(data,'GC=F','USD/oz')
    for row in result['moving_averages']:
        assert row['recent_crossings'][-1]['date']==str(data.index[-1].date())
        assert row['recent_crossings'][-1]['previous_date']==str(data.index[-2].date())


@pytest.mark.parametrize('mutation',[lambda d:d.iloc[::-1],lambda d:pd.concat([d,d.iloc[-1:]]),
                                     lambda d:d.assign(close=np.inf)])
def test_invalid_observations_become_explicit_diagnostic(mutation):
    from src.chart_review import analyze_ma_crossings
    result=analyze_ma_crossings(mutation(prices()),'QQQ','USD/share')
    assert result['status']=='unavailable' and result['reason']
    json.dumps(result,allow_nan=False)


def test_missing_close_not_filled_to_claim_a_cross():
    from src.chart_review import analyze_ma_crossings
    data=prices(90,110); data.iloc[-3,0]=np.nan
    result=analyze_ma_crossings(data,'GLD','USD/share')
    assert all(r['latest_event']=='unavailable' for r in result['moving_averages'])
    # Valid observations before the missing row still count; no gap is filled.
    assert [r['recent_pairs_evaluated'] for r in result['moving_averages']]==[2,2,0]


def test_saving_chart_writes_separate_report_without_added_image_annotations(tmp_path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from src.kline import plot_single,savefig_multi_format
    fig,ax=plt.subplots()
    try:
        plot_single('GC=F',ax,layer='commodities_futures')
        before=len(ax.texts)
        images=savefig_multi_format(fig,tmp_path/'gold.png',formats=('png',),png_dpi=60)
        assert len(images)==1
        assert (tmp_path/'gold.ma-review.md').exists()
        result=json.loads((tmp_path/'gold.ma-review.json').read_text(encoding='utf-8'))
        assert result['instruments'][0]['symbol']=='GC=F'
        assert len(ax.texts)==before
    finally:
        plt.close(fig)
