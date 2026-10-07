"""Numerical moving-average observations alongside charts, separate from captions."""
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd


def _event(previous,current):
    if current==0: return 'touch'
    if previous<0<current: return 'crossed_above'
    if previous>0>current: return 'crossed_below'
    if previous==0: return 'departed_above' if current>0 else 'departed_below'
    return 'none'


def analyze_ma_crossings(data,symbol,unit,windows=(50,100,200),recent_observations=5,as_of=None):
    result={'symbol':symbol,'unit':unit,'status':'unavailable','moving_averages':[],
            'basis':'available daily closes; exchange-session coverage not authenticated',
            'recent_observations':recent_observations,'cross_scope':'strict opposite sides at adjacent observed closes'}
    try:
        if any(type(w) is not int or w<2 for w in windows) or not windows or len(set(windows))!=len(windows):
            raise ValueError('unique moving-average windows of at least two observations required')
        if type(recent_observations) is not int or not 1<=recent_observations<=100:
            raise ValueError('recent observation count must be1..100')
        frame=data.loc[:as_of] if as_of is not None else data
        index=frame.index
        if (not isinstance(index,pd.DatetimeIndex) or index.tz is not None or index.hasnans or
            index.has_duplicates or not index.is_monotonic_increasing or not index.equals(index.normalize())):
            raise ValueError('unique increasing naive daily dates required')
        if len(frame)<2 or not pd.api.types.is_numeric_dtype(frame['close']):
            raise ValueError('at least two numeric daily closes required')
        close=frame['close'].astype(float)
        if np.isinf(close.to_numpy()).any() or (close.dropna()<=0).any() or not math.isfinite(close.iloc[-1]):
            raise ValueError('finite positive prices and an available latest close required')
        result.update(status='evaluated',date=str(index[-1].date()),previous_date=str(index[-2].date()),
                      close=float(close.iloc[-1]),previous_close=float(close.iloc[-2]) if pd.notna(close.iloc[-2]) else None,
                      input_sha256=hashlib.sha256(pd.util.hash_pandas_object(close,index=True).values.tobytes()).hexdigest())
        for window in windows:
            means=close.rolling(window,min_periods=window).mean()
            current,previous=float(means.iloc[-1]),float(means.iloc[-2])
            row={'window':window,'sma':current if math.isfinite(current) else None,
                 'previous_sma':previous if math.isfinite(previous) else None,'position':'unavailable',
                 'distance_pct':None,'latest_event':'unavailable','recent_crossings':[],
                 'recent_pairs_evaluated':0,'recent_pairs_requested':min(recent_observations,len(close)-1)}
            if math.isfinite(current):
                diff=float(close.iloc[-1]-current)
                row.update(position='above' if diff>0 else 'below' if diff<0 else 'on',
                           distance_pct=diff/current*100)
                if math.isfinite(previous) and pd.notna(close.iloc[-2]):
                    row['latest_event']=_event(float(close.iloc[-2]-previous),diff)
            if row['latest_event']=='unavailable':
                row['reason']='current/previous rolling window lacks enough complete closes; missing values not filled'
            for i in range(max(1,len(close)-recent_observations),len(close)):
                values=[close.iloc[i-1],close.iloc[i],means.iloc[i-1],means.iloc[i]]
                if not all(math.isfinite(float(v)) for v in values): continue
                row['recent_pairs_evaluated']+=1
                event=_event(float(values[0]-values[2]),float(values[1]-values[3]))
                if event in ('crossed_above','crossed_below'):
                    row['recent_crossings'].append({'date':str(index[i].date()),
                        'previous_date':str(index[i-1].date()),'calendar_gap_days':(index[i]-index[i-1]).days,
                        'event':event,'close':float(close.iloc[i]),'sma':float(means.iloc[i])})
            result['moving_averages'].append(row)
    except (ValueError,TypeError,KeyError,AttributeError) as exc:
        result.update(status='unavailable',reason=str(exc))
    return result


def render_ma_review(reviews):
    events={'crossed_above':'收盘上穿','crossed_below':'收盘下穿','none':'未发生收盘穿越',
            'touch':'收盘触及均线','departed_above':'贴线后离开至上方，未计确认上穿',
            'departed_below':'贴线后离开至下方，未计确认下穿','unavailable':'无法判定'}
    positions={'above':'上方','below':'下方','on':'贴线','unavailable':'无法判定'}
    lines=['# 图片之外的均线穿越检查','',
           '根据原始日线数值计算，与图片描述分开。使用收盘价相对各自当日SMA的关系，不从截图猜测穿越。',
           '日均线按可用日线观察数计算；交易日完整性未认证。缺失不填补，触及不当作确认穿越。','']
    for result in reviews:
        lines.extend([f"## {result['symbol']}",''])
        if result['status']!='evaluated':
            lines.extend(['无法检查：'+result.get('reason','数据不足'),'']); continue
        lines.extend([f"行情截至 {result['date']}；收盘价 {result['close']:,.2f} {result['unit']}；上一可用日期 {result['previous_date']}。",'',
            '| 均线 | 均线值 | 收盘位置 | 偏离 | 最新收盘事件 |',
            '|---|---:|---|---:|---|'])
        for row in result['moving_averages']:
            mean='缺数据' if row['sma'] is None else f"{row['sma']:,.2f}"
            distance='无法判定' if row['distance_pct'] is None else f"{row['distance_pct']:+.2f}%"
            lines.append(f"| SMA{row['window']} | {mean} | {positions[row['position']]} | {distance} | {events[row['latest_event']]} |")
        lines.extend(['',f"最近{result['recent_observations']}个可用日线的确认穿越："])
        for row in result['moving_averages']:
            lines.append(f"- SMA{row['window']}：有效检查{row['recent_pairs_evaluated']}/{row['recent_pairs_requested']}组相邻观察。")
            if row['recent_crossings']:
                for event in row['recent_crossings']:
                    lines.append(f"- SMA{row['window']}：{event['previous_date']} → {event['date']}，{events[event['event']]}；两次可用观察相隔{event['calendar_gap_days']}个日历日。")
            else:
                unavailable=row['latest_event']=='unavailable'
                lines.append(f"- SMA{row['window']}：{'最新穿越无法判定，窗口可能不完整' if unavailable else '未记录确认穿越'}。")
            if row.get('reason'): lines.append('  数据限制：'+row['reason'])
        lines.extend(['','这是历史价格与均线的位置检查；没有证明后续趋势、收益或因果关系。',''])
    return '\n'.join(lines)+'\n'


def write_ma_review(output_path,reviews):
    base=Path(output_path)
    payload={'schema_version':1,'instruments':reviews}
    encoded=json.dumps(payload,ensure_ascii=False,indent=2,allow_nan=False)
    md=base.with_suffix('.ma-review.md'); js=base.with_suffix('.ma-review.json')
    md.write_text(render_ma_review(reviews),encoding='utf-8')
    js.write_text(encoded,encoding='utf-8')
    return md,js
