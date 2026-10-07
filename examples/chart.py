"""Offline chart profiles with explicit options, input hashes and separate SMA history."""
import argparse
from datetime import datetime,timezone
import hashlib
from io import BytesIO
import json
import math
from pathlib import Path
import sys

from src.chart_profiles import PROFILE_DEFAULTS,PRICE_ASSETS,resolve_chart_options,validate_daily_prices


def periods(value):
    if value=='none': return ()
    try: return tuple(int(v) for v in value.split(','))
    except ValueError as exc: raise argparse.ArgumentTypeError('use comma-separated integer periods or none') from exc


def history(value):
    if value=='all': return None
    try: return int(value)
    except ValueError as exc: raise argparse.ArgumentTypeError('cross-history needs all or a positive count') from exc


def main(argv=None):
    parser=argparse.ArgumentParser(description='生成可选profile行情图及独立均线检查（离线，无宏观事件叠线）')
    parser.add_argument('--list-profiles',action='store_true')
    parser.add_argument('--profile',choices=tuple(PROFILE_DEFAULTS),default='ma-review')
    parser.add_argument('--symbols',help='comma-separated instrument symbols')
    parser.add_argument('--layout',choices=('single','grid'))
    parser.add_argument('--lookback',type=int)
    parser.add_argument('--smas',type=periods,dest='sma_windows')
    parser.add_argument('--pivots',action=argparse.BooleanOptionalAction,default=None)
    parser.add_argument('--review',action=argparse.BooleanOptionalAction,default=None)
    parser.add_argument('--review-windows',type=periods)
    parser.add_argument('--recent',type=int,dest='recent_observations')
    parser.add_argument('--cross-history',type=history,dest='history_search_observations',default=argparse.SUPPRESS)
    parser.add_argument('--as-of')
    parser.add_argument('--cache-root',type=Path)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--formats',default='png')
    parser.add_argument('--dpi',type=int,default=300)
    args=parser.parse_args(argv)
    if args.list_profiles:
        print(json.dumps({name:{'label':settings['label'],'options':resolve_chart_options(name).to_dict()}
                          for name,settings in PROFILE_DEFAULTS.items()},ensure_ascii=False,indent=2))
        return 0
    fig=None
    try:
        overrides={key:getattr(args,key) for key in ('layout','lookback','sma_windows','pivots','review',
            'review_windows','recent_observations','as_of') if getattr(args,key) is not None}
        if hasattr(args,'history_search_observations'):
            overrides['history_search_observations']=args.history_search_observations
        if args.symbols is not None: overrides['symbols']=tuple(s.strip() for s in args.symbols.split(','))
        options=resolve_chart_options(args.profile,**overrides)
        formats=tuple(args.formats.split(','))
        if not formats or any(f not in ('png','svg','pdf') for f in formats) or len(set(formats))!=len(formats):
            raise ValueError('formats must be unique png,svg,pdf choices')
        if not 50<=args.dpi<=600: raise ValueError('dpi must be50..600')
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import pandas as pd
        from src import thresholds,kline
        cache_root=args.cache_root or thresholds.CACHE_ROOT
        output=args.output or Path('output')/f'chart_{options.profile}.png'
        if not options.review and any(output.with_suffix(s).exists() for s in ('.ma-review.md','.ma-review.json')):
            raise ValueError('previous SMA review files share this output name; choose a new name for a no-review chart')
        inputs=[]
        for symbol in options.symbols:
            layer,unit=PRICE_ASSETS[symbol]
            path=cache_root/layer/(thresholds.safe_name(symbol)+'.parquet')
            raw=path.read_bytes()
            frame=pd.read_parquet(BytesIO(raw))
            if options.as_of is not None: frame=frame.loc[:options.as_of]
            validate_daily_prices(frame)
            inputs.append((symbol,layer,unit,frame,{'symbol':symbol,'source_path':str(path.resolve()),
                'source_sha256':hashlib.sha256(raw).hexdigest(),'first_date':str(frame.index[0].date()),
                'quote_date':str(frame.index[-1].date()),'rows':len(frame),'declared_unit':unit}))
        columns=1 if options.layout=='single' else min(2,len(inputs))
        rows=math.ceil(len(inputs)/columns)
        fig,axes=plt.subplots(rows,columns,figsize=(14,7) if columns==1 else (16,5*rows),squeeze=False)
        for ax,(symbol,layer,unit,frame,metadata) in zip(axes.flat,inputs):
            kline.plot_single(symbol,ax,layer=layer,data=frame,sma_windows=options.sma_windows,
                show_pivots=options.pivots,ma_review=options.review,review_windows=options.review_windows,
                recent_observations=options.recent_observations,history_search_observations=options.history_search_observations,
                price_unit=unit,lookback_days=options.lookback)
        for ax in list(axes.flat)[len(inputs):]: fig.delaxes(ax)
        fig.tight_layout()
        files=kline.savefig_multi_format(fig,output,formats=formats,png_dpi=args.dpi)
        plt.close(fig); fig=None
        artifacts=[str(p.resolve()) for p in files]
        if options.review:
            artifacts.extend(str(output.with_suffix(s).resolve()) for s in ('.ma-review.md','.ma-review.json'))
        manifest={'schema_version':1,'generated_at_utc':datetime.now(timezone.utc).isoformat(),
            'options':options.to_dict(),'explicit_overrides':overrides,
            'formats':formats,'dpi':args.dpi,'inputs':[item[4] for item in inputs],
            'macro_event_overlays':False,'artifacts':artifacts,
            'known_limits':['historical daily close data, not an authenticated real-time spot quote',
                            'human visual acceptance and exchange-session completeness not certified']+
                           (['existing SVG candle-hover metadata remains unverified; read prices from PNG or numerical report'] if 'svg' in formats else [])}
        manifest_path=output.with_suffix('.manifest.json')
        manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
        print(f'Profile {options.profile}: '+', '.join(options.symbols))
        for path in artifacts: print(path)
        print(manifest_path.resolve())
        return 0
    except (ValueError,TypeError,OSError,KeyError) as exc:
        print(f'Chart generation failed: {exc}',file=sys.stderr)
        return 1
    finally:
        if fig is not None:
            import matplotlib.pyplot as plt
            plt.close(fig)


if __name__=='__main__':
    raise SystemExit(main())
