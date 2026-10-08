import copy
import json
import numpy as np
import pandas as pd
import pytest

from src.hypothesis_review import evaluate_registry, summarize_support, render_hypothesis_report


def panel(sign=1., n=220):
    rng=np.random.default_rng(81)
    x=rng.normal(size=n)
    y=sign*2*np.roll(x,1)+rng.normal(0,.15,n)
    data=pd.DataFrame({'X':x,'Y':y},index=pd.bdate_range('2025-01-02',periods=n))
    data.attrs['column_units']={'X':'bp_change','Y':'pct_return'}
    return data


def claim(**changes):
    result={'id':'H1','statement':'滞后X与Y的调整关联超过登记量级',
        'kind':'lagged_directional_association','treatment':'X','outcome':'Y','controls':[],
        'units':{'X':'bp_change','Y':'pct_return'},'lag_observations':1,'direction':'positive',
        'minimum_effect':.5,'start':'2025-01-02','end':'2025-11-05',
        'registered_at':'2024-12-30T00:00:00+00:00','hac_lags':3}
    result.update(changes); return result


def evaluate(data=None, claims=None):
    return evaluate_registry({'schema_version':1,'alpha':.05,'hypotheses':claims or [claim()]},panel() if data is None else data)


def test_positive_observable_evidence_is_limited_and_never_causal_probability():
    result=evaluate(); row=result['results'][0]
    assert row['falsification_status']=='not_rejected'
    assert row['evidence_direction']=='supports_observable_proposition'
    assert row['coefficient_interval'][0]>.5
    assert result['assessments'][0]['support_tendency']=='limited_conditional_support'
    assert result['dag_trust']=='low_hypothesis_only'
    assert result['causal_probability'] is None


def test_counterexample_is_not_hidden_or_outvoted_by_support():
    positive=evaluate()['results'][0]
    negative=evaluate(panel(-1))['results'][0]
    assert negative['falsification_status']=='rejected'
    summary=summarize_support([positive,negative])
    assert summary['support_tendency']=='conflicted'
    assert summary['counter_records']==1 and summary['support_records']==1


def test_duplicate_records_do_not_create_independent_replications():
    row=evaluate()['results'][0]
    summary=summarize_support([row,copy.deepcopy(row)])
    assert summary['support_records']==1 and summary['unique_input_count']==1
    assert summary['independent_replication_verified'] is False


def test_late_registration_is_exploratory_and_cannot_upgrade_positive_support():
    result=evaluate(claims=[claim(registered_at='2026-10-07T00:00:00+00:00')])
    assert result['results'][0]['exploratory']
    assert result['assessments'][0]['support_tendency']=='insufficient'
    assert result['assessments'][0]['exploratory_support_records']==1


def test_multiple_registered_hypotheses_use_simultaneous_intervals():
    first=evaluate()['results'][0]
    result=evaluate(claims=[claim(),claim(id='H2',minimum_effect=.6)])
    second=result['results'][0]
    assert second['interval_alpha']==.025 and second['family_size']==2
    assert second['coefficient_interval'][1]-second['coefficient_interval'][0] > first['coefficient_interval'][1]-first['coefficient_interval'][0]


def test_unfalsifiable_causal_direction_does_not_enter_statistical_support():
    result=evaluate(claims=[claim(kind='causal_arrow')])
    assert result['results'][0]['falsification_status']=='untestable'
    assert result['assessments'][0]['support_tendency']=='insufficient'


@pytest.mark.parametrize('mutate',[lambda d:d.iloc[::-1],lambda d:pd.concat([d,d.iloc[:1]]),
                                  lambda d:d.assign(X=float('inf')),lambda d:d.iloc[:12]])
def test_invalid_input_keeps_registered_claim_as_untestable(mutate):
    result=evaluate(mutate(panel()))
    assert result['results'][0]['falsification_status']=='untestable'
    assert result['assessments'][0]['support_tendency']=='insufficient'


def test_unverified_units_and_unknown_controls_are_not_silently_assumed():
    data=panel(); data.attrs={}
    assert evaluate(data)['results'][0]['falsification_status']=='untestable'
    assert evaluate(claims=[claim(controls=['MISSING'])])['results'][0]['falsification_status']=='untestable'


def test_zero_nonrejection_is_not_proof_and_equivalence_needs_declared_tolerance():
    data=panel(0,n=220)
    exact=claim(kind='conditional_linear_zero',lag_observations=0,tolerance=0)
    result=evaluate(data,[exact])
    assert result['results'][0]['evidence_direction']=='inconclusive'
    approx=claim(kind='conditional_linear_zero',lag_observations=0,tolerance=.2)
    result=evaluate(data,[approx])
    assert result['results'][0]['evidence_direction']=='supports_observable_proposition'


def test_p_value_is_never_interpreted_as_probability_that_the_claim_is_true():
    row=evaluate()['results'][0]
    assert 'probability' not in row
    assert row['scope']=='observable_linear_constraint_not_causal_identification'


def test_unrelated_propositions_cannot_be_combined_into_one_vote():
    result=evaluate(claims=[claim(),claim(id='H2',direction='negative')])
    assert len(result['assessments'])==2
    with pytest.raises(ValueError): summarize_support(result['results'])


def test_raw_permutation_and_duplicate_input_are_not_a_supporting_source():
    result=evaluate(claims=[claim(),claim(id='H2')])
    assert result['results'][1]['duplicate_of']=='H1'
    assert result['assessments'][0]['support_records']==1


def test_registration_timestamp_changes_do_not_create_extra_evidence():
    result=evaluate(claims=[claim(),claim(id='H2',registered_at='2026-10-07T00:00:00+00:00')])
    assert result['results'][1]['duplicate_of']=='H1'
    assert result['assessments'][0]['support_tendency']=='insufficient'
    assert result['results'][0]['registration_conflict']


def test_incomplete_registered_time_window_is_untestable_not_partial_confirmation():
    result=evaluate(claims=[claim(end='2026-12-31')])
    assert result['results'][0]['falsification_status']=='untestable'


def test_late_selected_counterevidence_has_same_exploratory_limits_as_support():
    result=evaluate(panel(-1),[claim(registered_at='2026-10-07T00:00:00+00:00')])
    summary=result['assessments'][0]
    assert summary['support_tendency']=='insufficient'
    assert summary['counter_records']==0 and summary['exploratory_counter_records']==1


def test_cross_run_registration_conflict_cannot_be_selected_by_order():
    early=evaluate()['results'][0]
    late=evaluate(claims=[claim(registered_at='2026-10-07T00:00:00+00:00')])['results'][0]
    for rows in ([early,late],[late,early]):
        summary=summarize_support(rows)
        assert summary['support_tendency']=='insufficient'
        assert summary['support_records']==0 and summary['exploratory_support_records']==1
    assert not early['exploratory']  # aggregation must not mutate its inputs


@pytest.mark.parametrize('threshold',[float('nan'),float('inf'),-float('inf')])
def test_malformed_threshold_keeps_valid_siblings_and_serializable_report(threshold):
    result=evaluate(claims=[claim(),claim(id='BAD',minimum_effect=threshold)])
    assert result['results'][0]['evidence_direction']=='supports_observable_proposition'
    assert result['results'][1]['falsification_status']=='untestable'
    json.dumps(result,allow_nan=False)


def test_markdown_exposes_tested_protocol_despite_misleading_free_text():
    result=evaluate(claims=[claim(statement='关联超过5')])
    report=render_hypothesis_report(result)
    for fragment in ('minimum_effect', '0.5', 'direction', 'positive', 'controls',
                     'lag_observations', '2025-01-02', '2025-11-05', 'hac_lags',
                     'registered_at', 'bp_change', 'pct_return'):
        assert fragment in report
