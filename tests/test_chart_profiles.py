import json
import numpy as np
import pandas as pd
import pytest


def cache(tmp_path):
    root=tmp_path/'cache'
    data=pd.DataFrame({'open':100.,'high':101.,'low':99.,'close':100.,'volume':1000},
                      index=pd.bdate_range('2025-01-02',periods=240))
    for symbol,layer in [('GC_F','commodities_futures'),('GLD','commodities_spot_etf'),
                         ('QQQ','indices'),('TLT','indices')]:
        dest=root/layer/(symbol+'.parquet'); dest.parent.mkdir(parents=True,exist_ok=True)
        data.to_parquet(dest)
    return root


def test_profile_defaults_and_explicit_overrides_do_not_mutate_presets():
    from src.chart_profiles import resolve_chart_options
    pure=resolve_chart_options('price')
    assert not pure.review and pure.sma_windows==() and not pure.pivots
    changed=resolve_chart_options('price',review=True,sma_windows=(50,200))
    assert changed.review and changed.sma_windows==(50,200)
    assert resolve_chart_options('price')==pure
    assert resolve_chart_options('comparison').layout=='grid'


@pytest.mark.parametrize('options',[{'lookback':0},{'recent_observations':101},
                                    {'sma_windows':(50,50)},{'symbols':('^TNX',)},
                                    {'layout':'single','symbols':('GC=F','GLD')}])
def test_invalid_options_fail_explicitly(options):
    from src.chart_profiles import resolve_chart_options
    with pytest.raises(ValueError): resolve_chart_options('ma-review',**options)


def test_price_only_cli_produces_no_indicator_or_review_artifacts(tmp_path):
    from examples.chart import main
    output=tmp_path/'pure.png'
    assert main(['--profile','price','--cache-root',str(cache(tmp_path)),
                 '--output',str(output),'--dpi','60'])==0
    assert output.exists() and not output.with_suffix('.ma-review.md').exists()
    manifest=json.loads(output.with_suffix('.manifest.json').read_text(encoding='utf-8'))
    assert manifest['options']['sma_windows']==[] and not manifest['options']['review']
    assert manifest['macro_event_overlays'] is False


def test_selected_ma_and_historical_cutoff_use_only_supplied_data():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from src.kline import plot_single
    data=pd.DataFrame({'open':100.,'high':101.,'low':99.,'close':100.},
                      index=pd.bdate_range('2025-01-02',periods=240))
    data.iloc[-1]=[200.,201.,199.,200.]
    cutoff=str(data.index[-2].date())
    fig,ax=plt.subplots()
    try:
        plot_single('GC=F',ax,layer='commodities_futures',data=data,as_of=cutoff,
                    sma_windows=(50,200),show_pivots=False,ma_review=True)
        labels=ax.get_legend_handles_labels()[1]
        assert labels==['50 SMA（50日简单均线）','200 SMA（200日简单均线）']
        assert ax._ma_review['date']==cutoff and ax._ma_review['close']==100
    finally: plt.close(fig)


def test_comparison_profile_separates_each_instrument_review(tmp_path):
    from examples.chart import main
    output=tmp_path/'comparison.png'
    assert main(['--profile','comparison','--cache-root',str(cache(tmp_path)),
                 '--output',str(output),'--dpi','60'])==0
    result=json.loads(output.with_suffix('.ma-review.json').read_text(encoding='utf-8'))
    assert [r['symbol'] for r in result['instruments']]==['GC=F','GLD','QQQ','TLT']


def test_profile_list_needs_no_market_files(capsys):
    from examples.chart import main
    assert main(['--list-profiles'])==0
    assert 'ma-review' in capsys.readouterr().out


def test_pure_price_same_output_rejects_stale_review_instead_of_mislabeling_it(tmp_path):
    from examples.chart import main
    output=tmp_path/'stale.png'
    prior=output.with_suffix('.ma-review.json')
    prior.write_text('{"old": true}',encoding='utf-8')
    assert main(['--profile','price','--cache-root',str(cache(tmp_path)),
                 '--output',str(output),'--dpi','60'])==1
    assert not output.exists() and json.loads(prior.read_text())=={'old':True}


def test_historical_pivot_does_not_use_later_quotes():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from src.kline import plot_single
    data=pd.DataFrame({'open':100.,'high':101.,'low':99.,'close':100.},
                      index=pd.bdate_range('2025-01-02',periods=240))
    data.iloc[-2:]=[200.,201.,199.,200.]
    fig,ax=plt.subplots()
    try:
        plot_single('GC=F',ax,layer='commodities_futures',data=data,
                    as_of=str(data.index[-3].date()),sma_windows=(),show_pivots=True)
        assert ax.get_legend_handles_labels()[1]==['R1（一级阻力） 101.00','S1（一级支撑） 99.00']
    finally: plt.close(fig)


def test_manifest_retains_explicit_defaults_and_all_history_override(tmp_path):
    from examples.chart import main
    output=tmp_path/'explicit.png'
    assert main(['--profile','ma-review','--cache-root',str(cache(tmp_path)),
        '--output',str(output),'--dpi','60','--smas','50,100,200','--recent','5',
        '--cross-history','all'])==0
    manifest=json.loads(output.with_suffix('.manifest.json').read_text(encoding='utf-8'))
    assert manifest['explicit_overrides']['sma_windows']==[50,100,200]
    assert manifest['explicit_overrides']['recent_observations']==5
    assert 'history_search_observations' in manifest['explicit_overrides']
    assert manifest['explicit_overrides']['history_search_observations'] is None
