import json
from dataclasses import asdict
import numpy as np
import pandas as pd

from src import causal, report


def data():
    rng=np.random.default_rng(17)
    x=rng.normal(size=160); y=2*x+rng.normal(0,.1,len(x))
    return pd.DataFrame({'X':x,'Y':y},index=pd.bdate_range('2025-01-02',periods=len(x)))


def test_formal_identification_and_significance_do_not_certify_dag():
    effect=causal.causal_query('X','Y',data=data(),cfg={'dot':'digraph { X -> Y; }'},n_refutations=0)
    result=effect.to_dict()
    assert effect.identification_status!='unidentifiable'
    assert result['epistemic_assessment']['dag_trust']=='low_hypothesis_only'
    assert result['epistemic_assessment']['causal_status']=='not_established'
    assert result['epistemic_assessment']['support_tendency']=='insufficient'
    assert '尚未建立因果效应' in effect.interpretation


def test_scm_result_is_a_model_scenario_with_no_truth_probability():
    cf=causal.counterfactual_query(str(data().index[-1].date()),'X','Y',.1,data=data(),
                                   cfg={'dot':'digraph { X -> Y; }'},method='scm')
    assessment=cf.to_dict()['epistemic_assessment']
    assert assessment['causal_probability'] is None and assessment['dag_trust']=='low_hypothesis_only'


def test_existing_random_noise_diagnostics_do_not_count_as_falsification_passes():
    effect=causal.causal_query('X','Y',data=data(),cfg={'dot':'digraph { X -> Y; }'},n_refutations=3,refute_method='ols')
    assert len(effect.refutation)==3
    assert effect.to_dict()['epistemic_assessment']['falsification_status']=='not_evaluated'
    assert effect.to_dict()['epistemic_assessment']['support_tendency']=='insufficient'


def test_report_retains_diagnostics_without_promotion_to_validated_intervention(monkeypatch):
    # Use real query code; only select a bounded synthetic config/data.
    sample=data().rename(columns={'X':'VIX','Y':'QQQ'}); sample['TNX']=sample['VIX']*.5
    cfg={'dot':'digraph { VIX -> QQQ; TNX -> QQQ; }'}
    monkeypatch.setattr(causal,'load_dag_config',lambda:cfg)
    monkeypatch.setattr(causal,'load_dag_data',lambda **kw:sample)
    monkeypatch.setattr(causal,'cate_heterogeneity',lambda **kw:[])
    text=report.render_causal_section(include_l3=True)
    assert 'DAG默认低可信' in text
    assert '正向支持：证据不足' in text
    assert '反驳测试 3/3 通过' not in text
    assert '**L2 干预**' not in text
    assert '**L3 反事实**' not in text


def test_offline_hypothesis_cli_writes_complete_results_and_unknowns(tmp_path):
    from examples.hypothesis_report import main
    sample=data(); sample.attrs['column_units']={'X':'bp_change','Y':'pct_return'}
    sample.to_parquet(tmp_path/'input.parquet')
    spec={'id':'H1','statement':'方向尚无可证伪约束','kind':'causal_arrow'}
    (tmp_path/'registry.json').write_text(json.dumps({'schema_version':1,'alpha':.05,'hypotheses':[spec]}))
    assert main(['--data',str(tmp_path/'input.parquet'),'--registry',str(tmp_path/'registry.json'),
                 '--output',str(tmp_path/'out.md'),'--json-output',str(tmp_path/'out.json')])==0
    assert json.loads((tmp_path/'out.json').read_text(encoding='utf-8'))['results'][0]['falsification_status']=='untestable'
    assert '当前无法检验' in (tmp_path/'out.md').read_text(encoding='utf-8')


def test_numeric_formatter_describes_model_numbers_without_predictive_certainty():
    formatted=causal.format_causal_effect(-.2,p_value=.001,std_err=.01)
    assert '预期' not in formatted['text']
    assert formatted['epistemic_assessment']['support_tendency']=='insufficient'


def test_generic_dataclass_serialization_also_carries_low_trust():
    effect=causal.causal_query('X','Y',data=data(),cfg={'dot':'digraph { X -> Y; }'},n_refutations=0)
    assert asdict(effect)['epistemic_assessment']['causal_status']=='not_established'
