"""Validated chart presets; explicit options override an immutable resolved preset."""
from dataclasses import dataclass,asdict
from datetime import date

PRICE_ASSETS={
    'GC=F':('commodities_futures','USD/oz'),
    '^IXIC':('indices','index points'),
    **{s:('indices','USD/share') for s in ('DIA','QQQ','RSP','QQQE','IEF','TLT')},
    **{s:('commodities_spot_etf','USD/share') for s in ('GLD','SLV','USO','BNO','UNG','CPER','PALL','PPLT','CORN','SOYB','WEAT','CANE')},
    **{s:('sectors','USD/share') for s in ('XLK','XLF','XLE','XLY','XLP','XLV','XLI','XLU','XLB','XLRE','XLC')},
}
PROFILE_DEFAULTS={
    'price':{'label':'只看价格','sma_windows':(),'review':False},
    'ma-review':{'label':'均线检查'},
    'comparison':{'label':'多资产对比','symbols':('GC=F','GLD','QQQ','TLT'),'layout':'grid','sma_windows':(200,)},
    'technical':{'label':'完整技术图','lookback':500,'sma_windows':(20,50,100,150,200),'pivots':True},
}


@dataclass(frozen=True)
class ChartOptions:
    profile: str='ma-review'
    symbols: tuple=('GC=F',)
    layout: str='single'
    lookback: int=252
    sma_windows: tuple=(50,100,200)
    pivots: bool=False
    review: bool=True
    review_windows: tuple=(50,100,200)
    recent_observations: int=5
    history_search_observations: int|None=None
    as_of: str|None=None

    def to_dict(self): return asdict(self)


def resolve_chart_options(profile='ma-review',**overrides):
    if profile not in PROFILE_DEFAULTS: raise ValueError('unknown chart profile')
    defaults={k:v for k,v in PROFILE_DEFAULTS[profile].items() if k!='label'}
    values={**defaults,**overrides,'profile':profile}
    for key in ('symbols','sma_windows','review_windows'):
        if key in values: values[key]=tuple(values[key])
    if 'layout' not in overrides and len(values.get('symbols',('GC=F',)))>1:
        values['layout']='grid'
    options=ChartOptions(**values)
    if not options.symbols or len(options.symbols)>12 or len(set(options.symbols))!=len(options.symbols):
        raise ValueError('select1..12 unique price instruments')
    if any(s not in PRICE_ASSETS for s in options.symbols):
        raise ValueError('unsupported price instrument; yield quotes such as TNX are not bond prices')
    if options.layout not in ('single','grid') or (options.layout=='single' and len(options.symbols)!=1):
        raise ValueError('single layout needs one instrument; otherwise select grid')
    if type(options.lookback) is not int or not 2<=options.lookback<=20000:
        raise ValueError('lookback must be2..20000 available daily observations')
    for windows in (options.sma_windows,options.review_windows):
        if len(set(windows))!=len(windows) or any(type(w) is not int or not 2<=w<=5000 for w in windows):
            raise ValueError('moving-average periods must be unique integers2..5000')
    if options.review and not options.review_windows: raise ValueError('review needs at least one moving-average period')
    if any(type(v) is not bool for v in (options.review,options.pivots)):
        raise ValueError('review and pivots must be boolean')
    if type(options.recent_observations) is not int or not 1<=options.recent_observations<=100:
        raise ValueError('recent observations must be1..100')
    history=options.history_search_observations
    if history is not None and (type(history) is not int or history<1):
        raise ValueError('cross history must be a positive count or all')
    if options.as_of is not None: date.fromisoformat(options.as_of)
    return options


def validate_daily_prices(frame):
    import numpy as np
    import pandas as pd
    idx=frame.index
    if (len(frame)<2 or not isinstance(idx,pd.DatetimeIndex) or idx.tz is not None or
        idx.hasnans or idx.has_duplicates or not idx.is_monotonic_increasing or not idx.equals(idx.normalize())):
        raise ValueError('price chart requires at least two unique increasing daily dates')
    required=['open','high','low','close']
    if any(c not in frame or not pd.api.types.is_numeric_dtype(frame[c]) for c in required):
        raise ValueError('numeric OHLC columns required')
    values=frame[required].to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values<=0).any(): raise ValueError('finite positive OHLC prices required; no filling')
    if ((frame['high']<frame[['open','close','low']].max(axis=1)) |
        (frame['low']>frame[['open','close','high']].min(axis=1))).any():
        raise ValueError('inconsistent OHLC price bounds')
