import json
from pathlib import Path

import pandas as pd
import pytest

from src.asset_report import build_asset_report, render_asset_report
from examples.asset_report import main
from src.asset_sources import parse_ishares, store_source


def prepare(tmp_path):
    market = tmp_path / 'market'
    market.mkdir()
    dates = pd.to_datetime(['2026-10-01', '2026-10-02'])
    for symbol, close in [('IEF', [100, 99]), ('_TNX', [5, 5.1]),
                          ('_IXIC', [100, 101]), ('QQQ', [100, 101])]:
        pd.DataFrame({'close': close, 'adj close': close}, index=dates).to_parquet(market / (symbol + '.parquet'))
    raw = (b'iShares 7-10 Year Treasury Bond ETF\nFund Holdings as of,"Oct 01, 2026"\n'
           b'Name,Asset Class,Weight (%),CUSIP,Duration,YTM (%),Maturity\n'
           b'TREASURY,Fixed Income,100,ABC,7,5,2035\n')
    sources = tmp_path / 'sources'
    store_source('IEF', raw, parse_ishares(raw, 'IEF'), sources,
                 retrieved_at='2026-10-03T14:00:00+00:00')
    return market, sources


def test_retrospective_treasury_has_dated_structure_and_linear_proxy(tmp_path):
    market, sources = prepare(tmp_path)
    result = build_asset_report(['IEF'], '2026-10-01', '2026-10-02', market, sources,
                               mode='retrospective')
    asset = result['assets'][0]
    assert asset['profile']['weighted_duration_years'] == 7
    assert asset['attribution']['yield_delta_bp'] == pytest.approx(10)
    assert asset['attribution']['estimated_price_effect'] == pytest.approx(-.007)
    assert asset['attribution']['residual'] == pytest.approx(-.003)
    text = render_asset_report(result)
    assert '事后解释' in text
    assert '未识别' in text
    assert '2026-10-01' in text
    assert '单期限' in text


def test_point_in_time_cannot_use_late_issuer_download(tmp_path):
    market, sources = prepare(tmp_path)
    result = build_asset_report(['IEF'], '2026-10-01', '2026-10-02', market, sources)
    asset = result['assets'][0]
    assert asset['returns']['price_return'] == pytest.approx(-.01)
    assert asset['profile'] is None
    assert asset['attribution']['status'] == 'unavailable'


def test_index_and_missing_holdings_never_receive_qqq_proxy(tmp_path):
    market, sources = prepare(tmp_path)
    result = build_asset_report(['^IXIC', 'QQQ', 'GLD'], '2026-10-01', '2026-10-02', market, sources,
                               mode='retrospective')
    index, qqq, gold = result['assets']
    assert index['profile'] is None
    assert index['attribution']['status'] == qqq['attribution']['status'] == 'unavailable'
    assert gold['returns'] is None
    assert gold['errors']
    json.dumps(result, allow_nan=False)


def test_bad_date_or_mode_rejected_before_output(tmp_path):
    market, sources = prepare(tmp_path)
    for start, end, mode in [('2026-10-02', '2026-10-01', 'retrospective'),
                             ('2026-10-01', '2026-10-02', 'invalid')]:
        with pytest.raises(ValueError):
            build_asset_report(['IEF'], start, end, market, sources, mode=mode)


def test_ambiguous_cached_symbol_fails_instead_of_choosing_a_file(tmp_path):
    market, sources = prepare(tmp_path)
    nested = market / 'another'
    nested.mkdir()
    (nested / 'IEF.parquet').write_bytes((market / 'IEF.parquet').read_bytes())
    result = build_asset_report(['IEF'], '2026-10-01', '2026-10-02', market, sources)
    assert result['assets'][0]['returns'] is None
    assert 'ambiguous' in result['assets'][0]['errors'][0]


def test_cli_report_writes_markdown_and_json_without_fetching(tmp_path):
    market, sources = prepare(tmp_path)
    output, evidence = tmp_path / 'report.md', tmp_path / 'report.json'
    assert main(['report', '--symbols', 'IEF', '^IXIC', '--start', '2026-10-01', '--end', '2026-10-02',
                 '--mode', 'retrospective', '--market-root', str(market), '--source-root', str(sources),
                 '--output', str(output), '--json-output', str(evidence)]) == 0
    assert output.exists()
    assert json.loads(evidence.read_text(encoding='utf-8'))['mode'] == 'retrospective'


def test_cli_sync_propagates_failure_and_does_not_fake_success(tmp_path, monkeypatch):
    from examples import asset_report
    def blocked(*args, **kwargs):
        raise ValueError('bad source')
    monkeypatch.setattr(asset_report, 'capture_source', blocked)
    assert main(['sync', '--symbols', 'QQQ', '--source-root', str(tmp_path)]) == 1


def test_explicit_market_file_resolves_duplicate_cache_and_records_provenance(tmp_path):
    market, sources = prepare(tmp_path)
    nested = market / 'another'
    nested.mkdir()
    (nested / 'IEF.parquet').write_bytes((market / 'IEF.parquet').read_bytes())
    selected = market / 'IEF.parquet'
    result = build_asset_report(['IEF'], '2026-10-01', '2026-10-02', market, sources,
                               mode='retrospective', market_files={'IEF': selected})
    asset = result['assets'][0]
    assert asset['returns']['price_return'] == pytest.approx(-.01)
    assert asset['market_source']['sha256']
    assert asset['market_source']['path'] == str(selected)
    assert not asset['errors']


def test_cli_supports_explicit_market_file_selection(tmp_path):
    market, sources = prepare(tmp_path)
    out = tmp_path / 'selected.md'
    assert main(['report', '--symbols', 'IEF', '--start', '2026-10-01', '--end', '2026-10-02',
                 '--market-root', str(market), '--source-root', str(sources), '--output', str(out),
                 '--market-file', 'IEF=' + str(market / 'IEF.parquet')]) == 0
    assert '价格/报价变动' in out.read_text(encoding='utf-8')


def test_broken_source_object_does_not_abort_other_assets(tmp_path):
    market, sources = prepare(tmp_path)
    (sources / 'QQQ').mkdir()
    (sources / 'QQQ' / 'broken.json').write_text('[]', encoding='utf-8')
    result = build_asset_report(['QQQ', 'IEF'], '2026-10-01', '2026-10-02', market, sources,
                               mode='retrospective')
    assert result['assets'][0]['attribution']['status'] == 'unavailable'
    assert result['assets'][0]['errors']
    assert result['assets'][1]['attribution']['status'] == 'approximation'


def test_qqq_attribution_keeps_constituent_and_beginning_snapshot_evidence(tmp_path):
    from src.asset_sources import parse_invesco
    market, sources = prepare(tmp_path)
    stock = market / 'AAA.parquet'
    pd.DataFrame({'close': [100, 102]}, index=pd.to_datetime(['2026-10-01','2026-10-02'])).to_parquet(stock)
    documents = []
    for day, weight in [('2026-10-01', 80), ('2026-10-02', 90)]:
        raw = json.dumps({'cusip': '46090E103', 'effectiveDate': day, 'effectiveBusinessDate': day,
                          'totalNumberOfHoldings': 2, 'holdings': [
                              {'ticker':'AAA','cusip':'111','issuerName':'Alpha','securityTypeName':'Common Stock',
                               'percentageOfTotalNetAssets':weight},
                              {'ticker':'USD','cusip':'USD','issuerName':'Cash','securityTypeName':'Currency',
                               'percentageOfTotalNetAssets':100-weight}]}).encode()
        path = store_source('QQQ', raw, parse_invesco(raw), sources, retrieved_at='2026-10-03T14:00:00+00:00')
        documents.append(json.loads(path.read_text(encoding='utf-8')))
    result = build_asset_report(['QQQ'], '2026-10-01', '2026-10-02', market, sources, mode='retrospective')
    attr = result['assets'][0]['attribution']
    assert attr['market_sources']['AAA']['sha256']
    assert attr['market_sources']['AAA']['path'] == str(stock)
    text = render_asset_report(result)
    assert documents[0]['sha256'] in text  # the actual attribution input, not just current profile
    assert documents[1]['sha256'] in text
