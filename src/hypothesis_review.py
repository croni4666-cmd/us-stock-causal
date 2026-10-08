"""Recompute registered observable constraints; never certify a causal DAG."""
from datetime import date, datetime, time, timezone
import hashlib
import json
import math
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

KINDS = {'conditional_linear_zero','lagged_directional_association'}
SCOPE = 'observable_linear_constraint_not_causal_identification'
LIMITATIONS = [
    'DAG remains a low-trust candidate; observable constraints do not identify causal directions',
    'HAC intervals are approximate linear-model inference, not valid for arbitrary financial processes',
    'failure to reject does not establish a proposition; p-values are not truth probabilities',
    'registration timestamp and input units are declarations, not authenticated historical provenance',
    'different hashes or AI reviewers do not establish independent replication',
    'external citations and AI-generated assertions are not numerical supporting evidence']


def default_dag_assessment():
    return {'dag_trust':'low_hypothesis_only','causal_status':'not_established',
            'falsification_status':'not_evaluated','support_tendency':'insufficient',
            'causal_probability':None,'limitations':list(LIMITATIONS)}


def _serializable(value):
    """Preserve invalid nonfinite declarations as explicit diagnostic markers."""
    if isinstance(value,float) and not math.isfinite(value):
        return {'invalid_nonfinite':str(value)}
    if isinstance(value,dict): return {k:_serializable(v) for k,v in value.items()}
    if isinstance(value,list): return [_serializable(v) for v in value]
    return value


def _hash(value):
    return hashlib.sha256(json.dumps(_serializable(value),sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def _input_hash(data):
    values = pd.util.hash_pandas_object(data,index=True).values.tobytes()
    metadata = json.dumps({'columns':list(data.columns),'dtypes':[str(t) for t in data.dtypes],
                           'declared_units':data.attrs.get('column_units')},sort_keys=True).encode()
    return hashlib.sha256(values+metadata).hexdigest()


def _proposition(spec):
    fields = ('kind','treatment','outcome','controls','units','lag_observations')
    key = {k:spec.get(k) for k in fields}
    controls=spec.get('controls',[])
    if isinstance(controls,list) and all(isinstance(c,str) for c in controls):
        key['controls']=sorted(controls)
    if spec.get('kind')=='conditional_linear_zero': key['tolerance']=spec.get('tolerance')
    else: key.update(direction=spec.get('direction'),minimum_effect=spec.get('minimum_effect'))
    return key


def _evaluate(spec,data,alpha,family_size):
    row = {'id':spec['id'],'statement':spec['statement'],'proposition_key':_hash(_proposition(spec)),
           'falsification_status':'untestable','evidence_direction':'inconclusive','scope':SCOPE,
           'exploratory':True,'family_size':family_size,'interval_alpha':alpha/family_size,
           'registered_protocol':_serializable(spec),'registration_authenticated':False,
           'positive_support_interpretation':'uncalibrated ordinal support only; no causal probability'}
    try:
        row['input_sha256']=_input_hash(data)
        row['test_fingerprint']=_hash({**_proposition(spec),'start':spec.get('start'),
             'end':spec.get('end'),'hac_lags':spec.get('hac_lags'),
             'data_hash':row['input_sha256']})
        if spec.get('kind') not in KINDS:
            raise ValueError('no executable observable constraint for this hypothesis kind')
        index=data.index
        if (not isinstance(index,pd.DatetimeIndex) or index.tz is not None or index.hasnans or
            index.has_duplicates or not index.is_monotonic_increasing or not index.equals(index.normalize())):
            raise ValueError('expected unique increasing naive daily observation dates')
        start,end=date.fromisoformat(spec['start']),date.fromisoformat(spec['end'])
        if start>end: raise ValueError('invalid registered observation window')
        if data.empty or index[0].date()>start or index[-1].date()<end:
            raise ValueError('input does not cover complete registered observation window')
        at=datetime.fromisoformat(spec['registered_at'])
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError('registration timestamp needs timezone')
        row['registration_time_utc']=at.astimezone(timezone.utc).isoformat()
        # Conservative session-start gate; this remains an unauthenticated declaration.
        row['exploratory']=at>datetime.combine(start,time(9,30),ZoneInfo('America/New_York'))
        treatment,outcome=spec['treatment'],spec['outcome']
        controls=spec.get('controls',[])
        if not isinstance(controls,list) or len(controls)!=len(set(controls)):
            raise ValueError('controls must be unique')
        variables=[treatment,outcome]+controls
        if len(variables)!=len(set(variables)) or any(v not in data for v in variables):
            raise ValueError('variables absent or roles overlap')
        units=spec.get('units',{})
        actual_units=data.attrs.get('column_units',{})
        if any(not isinstance(units.get(v),str) or not units[v] or actual_units.get(v)!=units[v] for v in variables):
            raise ValueError('explicit matching declared input units required')
        if any(not pd.api.types.is_numeric_dtype(data[v]) for v in variables):
            raise ValueError('numeric observations required')
        lag=spec.get('lag_observations')
        if type(lag) is not int or not 0<=lag<=20:
            raise ValueError('invalid observation lag')
        if spec['kind']=='lagged_directional_association' and lag<1:
            raise ValueError('directional predictive constraint requires at least one observation lag')
        # Shift before clipping, so predictors always refer to earlier observations.
        values=data[[treatment]+controls].shift(lag).copy()
        values[outcome]=data[outcome]
        values=values.loc[spec['start']:spec['end']]
        if np.isinf(values.to_numpy(dtype=float)).any(): raise ValueError('nonfinite observation')
        row['missing_rows']=int(values.isna().any(axis=1).sum())
        values=values.dropna()
        row['n_obs']=len(values)
        if len(values)<max(80,10*(len(controls)+2)):
            raise ValueError('too few complete observations for this approximate diagnostic')
        if any(values[v].nunique()<2 for v in variables):
            raise ValueError('constant or degenerate variable')
        lags=spec.get('hac_lags')
        if type(lags) is not int or not 0<=lags<=min(50,len(values)//4):
            raise ValueError('invalid prespecified HAC lag count')
        import statsmodels.api as sm
        X=sm.add_constant(values[[treatment]+controls],has_constant='add')
        if np.linalg.matrix_rank(X.to_numpy())!=len(X.columns):
            raise ValueError('rank-deficient model')
        fit=sm.OLS(values[outcome],X).fit(cov_type='HAC',cov_kwds={'maxlags':lags},use_t=True)
        beta=float(fit.params[treatment])
        lower,upper=[float(v) for v in fit.conf_int(alpha=alpha/family_size).loc[treatment]]
        if not all(math.isfinite(v) for v in (beta,lower,upper)) or upper<=lower:
            raise ValueError('invalid uncertainty interval')
        row.update(coefficient=beta,coefficient_interval=[lower,upper],
                   coefficient_unit=f'{units[outcome]} per {units[treatment]}',
                   coefficient_p_value_against_zero=float(fit.pvalues[treatment]),
                   actual_start=str(values.index[0].date()),actual_end=str(values.index[-1].date()),
                   recomputed_locally=True,falsification_status='not_rejected')
        if spec['kind']=='conditional_linear_zero':
            tolerance=spec.get('tolerance')
            if not isinstance(tolerance,(int,float)) or isinstance(tolerance,bool) or not math.isfinite(tolerance) or tolerance<0:
                raise ValueError('finite nonnegative registered equivalence tolerance required')
            if upper < -tolerance or lower > tolerance:
                row.update(falsification_status='rejected',evidence_direction='opposes_observable_proposition')
            elif tolerance>0 and lower>-tolerance and upper<tolerance:
                row['evidence_direction']='supports_observable_proposition'
        else:
            minimum=spec.get('minimum_effect')
            direction=spec.get('direction')
            if direction not in ('positive','negative') or isinstance(minimum,bool) or not isinstance(minimum,(int,float)) or not math.isfinite(minimum) or minimum<0:
                raise ValueError('registered sign and finite nonnegative minimum effect required')
            lo,hi=(lower,upper) if direction=='positive' else (-upper,-lower)
            if hi<minimum:
                row.update(falsification_status='rejected',evidence_direction='opposes_observable_proposition')
            elif lo>minimum: row['evidence_direction']='supports_observable_proposition'
    except (ValueError,TypeError,KeyError,AttributeError,np.linalg.LinAlgError) as exc:
        row.update(falsification_status='untestable',evidence_direction='inconclusive',reason=str(exc))
    return row


def summarize_support(records):
    if not records or len({r['proposition_key'] for r in records})!=1:
        raise ValueError('support summary needs one identical observable proposition')
    declarations={}
    for r in records:
        declarations.setdefault(r.get('test_fingerprint',r['id']),[]).append(r)
    unique={}
    conflicts=0
    for fingerprint,rows in declarations.items():
        # Inspect every declaration, including registry duplicates and separate runs.
        # A caller cannot select an earlier timestamp or a more favorable interval.
        signatures={(r.get('registration_time_utc'),r.get('interval_alpha'),
                     r.get('falsification_status'),r.get('evidence_direction')) for r in rows}
        conflict=len(signatures)>1 or any(r.get('registration_conflict') for r in rows)
        exploratory=conflict or any(r.get('exploratory',True) for r in rows)
        conflicts+=int(conflict)
        # Keep distinct opposing dispositions; identical computations count once.
        for r in rows:
            key=(fingerprint,r.get('falsification_status'),r.get('evidence_direction'))
            unique[key]={**r,'exploratory':exploratory}
    supports,counters,exploratory,exploratory_counters=0,0,0,0
    for r in unique.values():
        if r['falsification_status']=='untestable' or not r.get('recomputed_locally'): continue
        if r['evidence_direction']=='opposes_observable_proposition':
            if r['exploratory']: exploratory_counters+=1
            else: counters+=1
        elif r['evidence_direction']=='supports_observable_proposition':
            if r['exploratory']: exploratory+=1
            else: supports+=1
    tendency=('conflicted' if ((supports or exploratory) and counters) or (supports and exploratory_counters) else 'counterevidence' if counters else
              'limited_conditional_support' if supports else 'insufficient')
    return {'proposition_key':records[0]['proposition_key'],'support_tendency':tendency,
            'support_records':supports,'counter_records':counters,'exploratory_support_records':exploratory,
            'exploratory_counter_records':exploratory_counters,
            'duplicate_declaration_conflicts':conflicts,
            'unique_input_count':len({r.get('input_sha256') for r in unique.values() if r.get('input_sha256')}),
            'independent_replication_verified':False,'causal_probability':None,
            'limitations':list(LIMITATIONS)}


def evaluate_registry(registry,data):
    if not isinstance(registry,dict) or registry.get('schema_version')!=1:
        raise ValueError('unsupported hypothesis registry')
    specs=registry.get('hypotheses')
    alpha=registry.get('alpha')
    if not isinstance(specs,list) or not specs or len(specs)>500:
        raise ValueError('expected1..500 registered hypotheses')
    if isinstance(alpha,bool) or not isinstance(alpha,(int,float)) or not 0<alpha<.5:
        raise ValueError('invalid family alpha')
    if any(not isinstance(s,dict) or not isinstance(s.get('id'),str) or not s['id'] or
           not isinstance(s.get('statement'),str) or not s['statement'] for s in specs):
        raise ValueError('hypothesis IDs and statements required')
    if len({s['id'] for s in specs})!=len(specs): raise ValueError('duplicate hypothesis ID')
    results=[_evaluate(s,data,alpha,len(specs)) for s in specs]
    groups,seen={},{}
    for row in results:
        fingerprint=row.get('test_fingerprint')
        if fingerprint in seen:
            first=seen[fingerprint]
            row['duplicate_of']=first['id']
            if row.get('registration_time_utc')!=first.get('registration_time_utc'):
                first.update(exploratory=True,registration_conflict=True)
                row.update(exploratory=True,registration_conflict=True)
        elif fingerprint is not None: seen[fingerprint]=row
        groups.setdefault(row['proposition_key'],[]).append(row)
    return {'schema_version':1,'generated_at':datetime.now(timezone.utc).isoformat(),
            'dag_trust':'low_hypothesis_only','causal_status':'not_established','causal_probability':None,
            'multiplicity':'Bonferroni simultaneous intervals over all registered entries',
            'results':results,'assessments':[summarize_support(g) for g in groups.values()],
            'limitations':list(LIMITATIONS)}


def render_hypothesis_report(result):
    labels={'rejected':'观察约束被反驳','not_rejected':'尚未反驳，不等于成立','untestable':'当前无法检验'}
    tendencies={'insufficient':'证据不足','limited_conditional_support':'有限条件支持',
                'counterevidence':'存在反对证据','conflicted':'证据冲突'}
    summaries={a['proposition_key']:a for a in result['assessments']}
    lines=['# 可证伪命题与平衡证据评估','','DAG默认低可信；因果效应未建立；不提供命题成立概率。',
           '以下只检验登记的可观察线性约束，不验证因果方向。多重比较使用保守同时区间。','']
    for row in result['results']:
        assessment=summaries[row['proposition_key']]
        lines.extend([f"## {row['id']}：{row['statement']}",labels[row['falsification_status']],
            '支持倾向：'+tendencies[assessment['support_tendency']],
            f"支持记录 {assessment['support_records']}；反对记录 {assessment['counter_records']}；事后探索支持记录 {assessment['exploratory_support_records']}。"])
        lines.append(f"事后探索反对记录 {assessment['exploratory_counter_records']}；同样不作为事前验证。")
        lines.extend(['实际登记的检验协议（文字标题不替代变量、方向和阈值）：',
                      '```json',json.dumps(row['registered_protocol'],ensure_ascii=False,indent=2,allow_nan=False),'```',
                      f"检验族大小 {row['family_size']}；单项区间 alpha={row['interval_alpha']:.6g}。",
                      '区间基于近似线性模型与HAC条件；不能保证适用于任意金融过程。'])
        if row.get('coefficient_interval') and row['falsification_status']!='untestable':
            lo,hi=row['coefficient_interval']
            lines.append(f"关联系数 {row['coefficient']:+.6g}；同时区间 [{lo:+.6g}, {hi:+.6g}]；单位 {row['coefficient_unit']}；样本 {row['n_obs']}，缺失剔除 {row['missing_rows']}。")
        if row.get('reason'): lines.append('缺口：'+row['reason'])
        if row['exploratory']: lines.append('登记晚于检验窗口，或未确认登记时序：仅作探索，不升级支持等级。')
        if row.get('duplicate_of'): lines.append('重复检验，不计复现：'+row['duplicate_of'])
        if row.get('registration_conflict'): lines.append('同一检验存在不同登记时间声明；不接受时间声明作为支持升级依据。')
        lines.extend(['输入SHA256：'+str(row.get('input_sha256','未取得')),
                      '登记时间和单位为声明，未认证；独立复现未核验。',''])
    lines.append('统计显著性、未发现反例、PC边重叠和随机噪声稳定都不能证明DAG或因果命题成立。')
    return '\n'.join(lines)+'\n'
