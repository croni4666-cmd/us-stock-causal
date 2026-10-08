import json
import socket
import urllib.request

import pytest

from src.residual_regression import INDICES, WINDOWS, compare_to_baseline


def snapshot(value=0.):
    return {'residuals': {index: {str(window): value for window in WINDOWS} for index in INDICES}}


@pytest.mark.parametrize('mutation', [
    lambda d: d.clear(),
    lambda d: d['residuals'].clear(),
    lambda d: d['residuals']['DIA'].pop('1'),
    lambda d: d['residuals'].__setitem__('DIA', []),
    lambda d: d['residuals']['DIA'].__setitem__('1', float('nan')),
    lambda d: d['residuals']['DIA'].__setitem__('1', float('inf')),
    lambda d: d['residuals']['DIA'].__setitem__('1', '0.1'),
    lambda d: d['residuals']['DIA'].__setitem__('1', True),
])
@pytest.mark.parametrize('side', ['current', 'baseline'])
def test_residual_gate_never_passes_missing_or_invalid_observations(mutation, side):
    current, baseline = snapshot(), snapshot(.1)
    mutation(current if side == 'current' else baseline)
    ok, violations = compare_to_baseline(current, baseline)
    assert ok is False and violations
    assert any(v.get('validation_error') for v in violations)
    json.dumps(violations, allow_nan=False)


def test_residual_gate_preserves_complete_snapshot_comparison():
    baseline = snapshot(.1)
    current = snapshot(.1)
    current['residuals']['QQQ']['5'] = -.2
    ok, violations = compare_to_baseline(current, baseline)
    assert ok is False
    assert violations == [{'index': 'QQQ', 'window': '5d', 'baseline_pct': .1,
                           'current_pct': .2, 'threshold_pct': .15, 'regression_ratio': 2.}]
    assert compare_to_baseline(snapshot(), baseline) == (True, [])


def test_offline_socket_boundary_rejects_before_connection():
    with socket.socket() as sock, pytest.raises(OSError, match='disabled in offline tests'):
        sock.connect(('127.0.0.1', 0))


def test_offline_urllib_boundary_rejects_before_request():
    with pytest.raises(OSError, match='disabled in offline tests'):
        urllib.request.urlopen('http://127.0.0.1:0', timeout=.1)


def test_offline_datagram_boundary_rejects_before_send():
    with socket.socket(type=socket.SOCK_DGRAM) as sock, pytest.raises(OSError, match='disabled in offline tests'):
        sock.sendto(b'no external payload', ('127.0.0.1', 0))
