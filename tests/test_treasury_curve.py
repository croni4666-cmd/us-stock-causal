import json
import pytest

from src.treasury_curve import NODES, parse_curve, store_curve, select_curve, capture_curve


def raw(values='4,4,4,4,4,4,4,4,4', day='10/01/2026'):
    return (','.join(['Date'] + list(NODES)) + '\n' + day + ',' + values + '\n').encode()


def test_reverse_order_csv_is_sorted_and_values_are_percent_not_decimals():
    sample = raw() + b'09/30/2026,3,3,3,3,3,3,3,3,3\n'
    rows = parse_curve(sample, 2026)['rows']
    assert rows[0]['date'] == '2026-09-30' and rows[1]['rates_pct']['10 Yr'] == 4.


@pytest.mark.parametrize('sample', [raw(day='10/01/2025'), raw()+b'10/01/2026,4,4,4,4,4,4,4,4,4\n',
                                  raw().replace(b'4,4,4', b'NaN,4,4'), b'<html>blocked</html>',
                                  raw().replace(b'6 Mo', b'wrong')])
def test_invalid_csv_rejected(sample):
    with pytest.raises(ValueError):
        parse_curve(sample, 2026)


def test_missing_node_is_not_filled_and_exact_day_required(tmp_path):
    store_curve(raw('4,4,4,4,4,4,N/A,4,4'), 2026, tmp_path)
    with pytest.raises(ValueError, match='complete'):
        select_curve(tmp_path, '2026-10-01', '2026-10-01', mode='retrospective')
    with pytest.raises(ValueError, match='exact'):
        select_curve(tmp_path, '2026-09-30', '2026-10-01', mode='retrospective')


def test_versions_hash_and_actual_availability_gate(tmp_path):
    a=store_curve(raw(), 2026, tmp_path, retrieved_at='2026-10-01T20:20:00+00:00')
    b=store_curve(raw('5,5,5,5,5,5,5,5,5'), 2026, tmp_path, retrieved_at='2026-10-02T21:00:00+00:00')
    assert a != b
    selected=select_curve(tmp_path, '2026-10-01', '2026-10-01')
    assert selected['start']['10 Yr'] == 4.
    assert select_curve(tmp_path,'2026-10-01','2026-10-01',mode='retrospective')['start']['10 Yr']==5.
    a.with_suffix('.raw').write_bytes(b'corrupt')
    with pytest.raises(ValueError, match='hash'):
        select_curve(tmp_path,'2026-10-01','2026-10-01',mode='retrospective')


def test_late_historical_capture_cannot_enter_strict_report(tmp_path):
    store_curve(raw(),2026,tmp_path,retrieved_at='2026-10-07T00:00:00+00:00')
    with pytest.raises(ValueError, match='eligible'):
        select_curve(tmp_path,'2026-10-01','2026-10-01')


def test_capture_uses_fixed_official_url_and_stores_response(tmp_path):
    class Response:
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def raise_for_status(self): pass
        def iter_content(self,chunk_size): yield raw()
    class Session:
        def get(self,url,**kwargs):
            assert url.startswith('https://home.treasury.gov/') and '2026/all' in url
            return Response()
    assert capture_curve(2026,tmp_path,session=Session()).exists()


def test_metadata_tampering_rejected(tmp_path):
    p=store_curve(raw(),2026,tmp_path)
    d=json.loads(p.read_text()); d['rows'][0]['rates_pct']['10 Yr']=99
    p.write_text(json.dumps(d))
    with pytest.raises(ValueError): select_curve(tmp_path,'2026-10-01','2026-10-01',mode='retrospective')
