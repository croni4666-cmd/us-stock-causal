"""Quote summary with typed price, yield and index measures; no shared macro return scale."""
from __future__ import annotations
import math
import numpy as np
from html import escape
import sys
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]

import pandas as pd
import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, MaxNLocator
from loguru import logger

from src.thresholds import load_prices, YIELD_SYMBOLS
from src.chart_labels import configure_chart_font,unit_label,instrument_label


# 中英文对照表 (用于表格显示)
SYMBOL_CN_NAMES = {
    # 指数
    "DIA":   "道琼斯 30 指数 ETF",
    "QQQ":   "纳斯达克 100 ETF",
    "RSP":   "标普 500 等权 ETF",
    "QQQE":  "纳斯达克 100 等权 ETF",
    # 行业
    "XLK":   "信息技术",
    "XLF":   "金融",
    "XLV":   "医疗保健",
    "XLY":   "可选消费",
    "XLP":   "必需消费",
    "XLE":   "能源",
    "XLI":   "工业",
    "XLB":   "材料",
    "XLU":   "公用事业",
    "XLC":   "通信服务",
    "XLRE":  "房地产",
    # 黄金
    "GC=F":  "黄金期货 (COMEX)",
    "GLD":   "黄金 ETF (SPDR)",
    # 宏观
    "^VIX":  "波动率指数 (VIX)",
    "^TNX":  "10 年期美债收益率",
    "DXY":   "美元指数 (DXY)",
}

# 颜色
COLOR_UP = "#26a69a"   # 涨绿 (跟 K 线一致)
COLOR_DOWN = "#ef5350" # 跌红 (跟 K 线一致)
COLOR_NEUTRAL = "#9e9e9e"  # 0% 灰


# 默认全标的 (layer, symbol) — 报告常用
DEFAULT_SYMBOLS: list[tuple[str, str]] = [
    # 4 指数
    ("indices", "DIA"),
    ("indices", "QQQ"),
    ("indices", "RSP"),
    ("indices", "QQQE"),
    # 11 行业 (按字母顺序)
    ("sectors", "XLB"),
    ("sectors", "XLC"),
    ("sectors", "XLE"),
    ("sectors", "XLF"),
    ("sectors", "XLI"),
    ("sectors", "XLK"),
    ("sectors", "XLP"),
    ("sectors", "XLRE"),
    ("sectors", "XLU"),
    ("sectors", "XLV"),
    ("sectors", "XLY"),
    # 2 黄金
    ("commodities_futures", "GC=F"),
    ("commodities_spot_etf", "GLD"),
    # 3 宏观
    ("macro", "^VIX"),
    ("macro", "^TNX"),
    ("macro", "DXY"),
]


def _measure(symbol,layer):
    if symbol in YIELD_SYMBOLS: return 'yield_bp','%','bp'
    if symbol=='^VIX': return 'vix_points','VIX points','VIX points'
    if symbol in ('DXY','DX-Y.NYB'): return 'index_points','index points','index points'
    if layer=='macro': return 'quote_delta','provider quote units','provider quote units'
    unit='USD/oz' if symbol=='GC=F' else 'provider quote units' if layer=='commodities_futures' else 'index points' if symbol.startswith('^') else 'USD/share'
    return 'price_quote_pct',unit,'%'


def compute_1d_change(symbol,layer,as_of=None):
    """Adjacent available quote changes, with explicit level and change units.

    change_pct remains a relative-quote diagnostic for compatibility, not a
    generic investment return. Displays use change_value/change_unit instead.
    """
    try:
        df=load_prices(symbol,layer)
        if df is None or len(df)<2: return None
        if as_of is not None: df=df.loc[:as_of]
        idx=df.index
        if len(df)<2: return None
        if (not isinstance(idx,pd.DatetimeIndex) or idx.tz is not None or idx.hasnans or
            idx.has_duplicates or not idx.is_monotonic_increasing or not idx.equals(idx.normalize())):
            raise ValueError('unique increasing daily quote dates required')
        values=df[['close','high','low']].to_numpy(dtype=float)
        if not np.isfinite(values).all(): raise ValueError('nonfinite quotes; no filling')
        last,previous=float(df['close'].iloc[-1]),float(df['close'].iloc[-2])
        kind,level_unit,change_unit=_measure(symbol,layer)
        if kind=='price_quote_pct' and (last<=0 or previous<=0):
            raise ValueError('positive price endpoints required for relative quote changes')
        relative=(last-previous)/previous*100 if previous!=0 else None
        change=(last-previous)*100 if kind=='yield_bp' else relative if kind=='price_quote_pct' else last-previous
        window=min(len(df),252)
        return {'symbol':symbol,'layer':layer,'last_close':last,'prev_close':previous,
            'change_pct':relative,'change_value':change,'change_unit':change_unit,'metric_kind':kind,
            'level_unit':level_unit,'date':str(idx[-1].date()),'previous_date':str(idx[-2].date()),
            'high_52w':float(df['high'].iloc[-window:].max()),'low_52w':float(df['low'].iloc[-window:].min()),
            'range_observations':window}
    except (OSError,ValueError,TypeError,KeyError) as exc:
        logger.warning(f'[perf] {symbol} ({layer}) unavailable: {exc}')
        return None


def collect_performance(symbols=None,as_of=None):
    return [r for layer,symbol in (DEFAULT_SYMBOLS if symbols is None else symbols)
            if (r:=compute_1d_change(symbol,layer,as_of=as_of)) is not None]


def _sorted_rows(results):
    return sorted(results,key=lambda r:(r['metric_kind']!='price_quote_pct',
        r['metric_kind'] if r['metric_kind']!='price_quote_pct' else '',-r['change_value']))


def _change_text(row):
    value=row['change_value']
    number=f'{value:+.2f}' if value==0 or abs(value)>=.005 else f'{value:+.4g}'
    return number+('' if row['change_unit']=='%' else ' ')+row['change_unit']


def plot_performance_dashboard(ax,symbols=None,top_n=None,as_of=None):
    """Price-quote percentage bars plus separate, unranked macro quote cards."""
    configure_chart_font()
    if top_n is not None and (type(top_n) is not int or top_n<1):
        raise ValueError('top_n must be a positive integer')
    results=collect_performance(symbols,as_of)
    for old in list(getattr(ax,'_performance_panels',{}).get('macro',[])): old.remove()
    previous=getattr(ax,'_performance_panels',{}).get('prices')
    if previous is not None: previous.remove()
    ax.clear(); ax.set_axis_off()
    ax._performance_rows=results
    panels={'prices':None,'macro':[]}; ax._performance_panels=panels
    if not results:
        ax.text(.5,.5,'No quote data',ha='center',transform=ax.transAxes)
        return ax
    prices=sorted([r for r in results if r['metric_kind']=='price_quote_pct'],key=lambda r:-r['change_value'])
    macro=[r for r in results if r['metric_kind']!='price_quote_pct']
    if top_n is not None and len(prices)>2*top_n: prices=prices[:top_n]+prices[-top_n:]
    card_columns=min(3,len(macro)) if macro else 1
    card_rows=math.ceil(len(macro)/card_columns) if macro else 0
    card_region=min(.55,.25*card_rows) if prices else .9
    quote_dates=sorted({r['date'] for r in results})
    date_text=quote_dates[0] if len(quote_dates)==1 else quote_dates[0]+' to '+quote_dates[-1]
    ax.set_title('Quote summary（报价总览） | '+date_text,fontsize=11,fontweight='bold',pad=8)
    if prices:
        chart=ax.inset_axes([.20,card_region+.12,.77,.80-card_region])
        panels['prices']=chart
        values=[r['change_value'] for r in prices]
        colors=[COLOR_UP if v>0 else COLOR_DOWN if v<0 else COLOR_NEUTRAL for v in values]
        bars=chart.barh(range(len(prices)),values,color=colors,alpha=.85)
        chart.set_yticks(range(len(prices)))
        chart.set_yticklabels([instrument_label(r['symbol']) for r in prices],fontsize=9)
        chart.invert_yaxis()
        scale=max(max(abs(v) for v in values),.1)
        for i,(row,value) in enumerate(zip(prices,values)):
            chart.text(value+(.025*scale if value>=0 else -.025*scale),i,_change_text(row),
                va='center',ha='left' if value>=0 else 'right',fontsize=9)
        chart.set_xlim(min(0,min(values))-.3*scale,max(0,max(values))+.3*scale)
        chart.axvline(0,color=COLOR_NEUTRAL,linestyle='--',linewidth=.8)
        chart.xaxis.set_major_formatter(FuncFormatter(lambda value,_:f'{value:+.1f}%'))
        chart.xaxis.set_major_locator(MaxNLocator(nbins=6,steps=[1,2,5,10]))
        chart.tick_params(axis='x',labelsize=8)
        chart.set_title(f'Price quote changes（价格报价变化） (%) | {len(prices)} instruments（标的）',fontsize=10,pad=5)
        chart.set_xlabel('Adjacent quotes（相邻报价）; excludes distributions and roll costs\n不含分红与展期成本；各标的观察日期见表格',fontsize=8)
        chart.grid(axis='x',alpha=.25,linestyle=':'); chart.set_axisbelow(True)
    for i,row in enumerate(macro):
        column=i%card_columns; line=i//card_columns
        height=card_region/card_rows*.82
        bottom=.015+(card_rows-1-line)*card_region/card_rows
        card=ax.inset_axes([column/card_columns+.015,bottom,1/card_columns-.03,height])
        card.set_axis_off()
        card.add_patch(mpl.patches.Rectangle((0,0),1,1,transform=card.transAxes,
            facecolor='#f3f6fa',edgecolor='#b8c6d7',linewidth=.8))
        card.text(.04,.79,instrument_label(row['symbol']),fontsize=9,transform=card.transAxes)
        card.text(.04,.52,f"Level（最新数值） {row['last_close']:,.3f} {row['level_unit']}",fontsize=10,fontweight='bold',transform=card.transAxes)
        suffix='（基点）' if row['change_unit']=='bp' else '（点）' if row['change_unit'] in ('VIX points','index points') else ''
        card.text(.04,.27,'Change（变化） '+_change_text(row)+suffix,fontsize=9,color='#174a7e',transform=card.transAxes)
        card.text(.04,.06,row['previous_date']+' to '+row['date'],fontsize=7,transform=card.transAxes)
        card._performance_row=row; panels['macro'].append(card)
    return ax


def render_performance_table(symbols=None,as_of=None):
    results=_sorted_rows(collect_performance(symbols,as_of))
    if not results: return '无数据'
    lines=['| 中文名 | 标的 | 最新数值 | 单位 | 相邻观察变化 | 观察日期 | 近252观察高 | 近252观察低 |',
           '|---|---|---:|---|---:|---|---:|---:|']
    for row in results:
        name=SYMBOL_CN_NAMES.get(row['symbol'],row['symbol'])
        digits=3 if row['level_unit']=='%' else 2
        lines.append(f"| {name} | `{row['symbol']}` | {row['last_close']:,.{digits}f} | {row['level_unit']} | {_change_text(row)} | {row['previous_date']} → {row['date']} | {row['high_52w']:,.{digits}f} | {row['low_52w']:,.{digits}f} |")
    lines.extend(['','变化按相邻可用报价计算，日期逐行列出。高低值与最新数值使用同一单位；历史观察不足252条时使用已有记录。',
                  '价格报价百分比不等于含分红的投资总回报；收益率用bp，VIX和美元指数用各自点数，不能合并为同一种盈亏。'])
    return '\n'.join(lines)


def render_performance_table_html(symbols=None,as_of=None):
    results=_sorted_rows(collect_performance(symbols,as_of))
    if not results: return '<p>无数据</p>'
    headers=['中文名','标的','最新数值','单位','相邻观察变化','观察日期','近252观察高','近252观察低']
    parts=['<table style="border-collapse:collapse;width:100%;font-size:13px"><thead><tr>']
    parts.extend('<th style="padding:8px">'+h+'</th>' for h in headers)
    parts.append('</tr></thead><tbody>')
    for row in results:
        value=row['change_value']
        color=('#137333' if value>0 else '#c5221f' if value<0 else '#5f6368') if row['metric_kind']=='price_quote_pct' else '#174a7e'
        digits=3 if row['level_unit']=='%' else 2
        cells=[SYMBOL_CN_NAMES.get(row['symbol'],row['symbol']),row['symbol'],f"{row['last_close']:,.{digits}f}",
               row['level_unit'],_change_text(row),row['previous_date']+' → '+row['date'],
               f"{row['high_52w']:,.{digits}f}",f"{row['low_52w']:,.{digits}f}"]
        parts.append('<tr>')
        for i,cell in enumerate(cells):
            style='padding:7px;border-bottom:1px solid #eee'+(f';color:{color}' if i==4 else '')
            parts.append('<td style="'+style+'">'+escape(str(cell))+'</td>')
        parts.append('</tr>')
    parts.append('</tbody></table><p>变化按相邻可用报价；高低值与最新数值同单位。价格涨跌不是完整投资总回报。收益率bp、VIX点数、美元指数点数分别呈现；颜色只描述数值方向。</p>')
    return '\n'.join(parts)
