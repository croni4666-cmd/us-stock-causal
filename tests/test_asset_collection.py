import json

import pandas as pd
import pytest

from examples import asset_report as cli
from src.asset_collection import collect_assets, inventory
from src.asset_market import store_market
from src.asset_report import build_asset_report, render_asset_report
from src.asset_sources import parse_invesco, store_source


def test_collect_preserves_success_and_manifest_when_another_provider_fails(tmp_path):
    calls = []
    def source(symbol, root):
        calls.append(symbol)
        if symbol == 'GLD':
            raise ValueError('provider down')
        path = root / (symbol + '.json')
        root.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({'symbol': symbol, 'sha256': 'example', 'as_of': '2026-10-02'}))
        return path
    def market(symbol, start, end, root):
        return store_market(symbol, pd.DataFrame({'close': [100., 101.]},
            index=pd.to_datetime(['2026-10-01', '2026-10-02'])), root, start, end)
    result = collect_assets('2026-10-01', '2026-10-03', tmp_path / 's', tmp_path / 'm',
                            tmp_path / 'runs', source_capture=source, market_capture=market)
    assert calls == ['QQQ', 'IEF', 'TLT', 'GLD']
    assert result['status'] == 'partial_failure'
    assert len(result['markets']) == 11
    assert result['sources'][-1]['error'] == 'provider down'
    assert json.loads(__import__('pathlib').Path(result['manifest_path']).read_text())['status'] == 'partial_failure'


def test_bad_query_does_not_download(tmp_path):
    def forbidden(*args):
        pytest.fail('network must not start')
    with pytest.raises(ValueError):
        collect_assets('2026-10-03', '2026-10-01', tmp_path, tmp_path, tmp_path,
                        source_capture=forbidden)


def test_inventory_counts_observation_days_and_keeps_missing_symbols(tmp_path):
    data = pd.DataFrame({'close': [100., 101.]}, index=pd.to_datetime(['2026-10-01', '2026-10-02']))
    for _ in range(2):
        store_market('QQQ', data, tmp_path / 'm', '2026-10-01', '2026-10-03')
    result = inventory(tmp_path / 's', tmp_path / 'm')
    assert result['markets']['QQQ']['snapshot_count'] == 2
    assert result['markets']['QQQ']['observation_days'] == ['2026-10-01', '2026-10-02']
    assert result['sources']['QQQ']['as_of_days'] == []
    assert result['markets']['TLT']['snapshot_count'] == 0


def test_report_uses_snapshot_store_and_actions_without_legacy_fallback(tmp_path):
    data = pd.DataFrame({'close': [100., 99.], 'dividends': [0., 1.], 'stock splits': [0., 0.]},
                        index=pd.to_datetime(['2026-10-01', '2026-10-02']))
    store_market('IEF', data, tmp_path / 'm', '2026-10-01', '2026-10-03')
    result = build_asset_report(['IEF', 'QQQ'], '2026-10-01', '2026-10-02', tmp_path / 'legacy',
                                tmp_path / 's', mode='retrospective', market_store=tmp_path / 'm')
    assert result['assets'][0]['actions']['dividend_per_share'] == 1.
    assert result['assets'][0]['market_source']['available_at']
    assert result['assets'][1]['returns'] is None
    assert '公司行动' in render_asset_report(result)
    assert not result['historical_trade_backtest_ready']


def test_cli_collect_returns_nonzero_on_partial_failure_and_inventory_is_offline(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, 'collect_assets', lambda *a, **k: {'status': 'partial_failure', 'manifest_path': 'test'})
    assert cli.main(['collect', '--start', '2026-10-01', '--end', '2026-10-03']) == 1
    output = tmp_path / 'inventory.json'
    assert cli.main(['inventory', '--source-root', str(tmp_path / 's'), '--market-store', str(tmp_path / 'm'),
                     '--output', str(output)]) == 0
    assert json.loads(output.read_text())['historical_trade_backtest_ready'] is False


def test_cli_report_accepts_store_and_rejects_competing_explicit_files(tmp_path):
    output = tmp_path / 'report.md'
    args = ['report', '--symbols', 'IEF', '--start', '2026-10-01', '--end', '2026-10-02',
             '--market-store', str(tmp_path / 'm'), '--output', str(output)]
    assert cli.main(args) == 0
    assert cli.main(args + ['--market-file', 'IEF=ambiguous.parquet']) == 1


@pytest.mark.parametrize('start,end', [('2026-10-01', '2026-10-02'), ('2026-09-30', '2026-10-01')])
def test_report_exposes_exact_daily_weight_gaps_even_when_period_model_unavailable(tmp_path, start, end):
    raw = json.dumps({'cusip': '46090E103', 'effectiveDate': '2026-10-03',
        'effectiveBusinessDate': '2026-10-02', 'totalNumberOfHoldings': 1,
        'holdings': [{'ticker': 'AAA', 'cusip': '111', 'issuerName': 'A',
                      'securityTypeName': 'Common Stock', 'percentageOfTotalNetAssets': 100}]}).encode()
    store_source('QQQ', raw, parse_invesco(raw), tmp_path / 's')
    data = pd.DataFrame({'close': [100., 101., 102.]}, index=pd.to_datetime(['2026-09-30', '2026-10-01', '2026-10-02']))
    store_market('QQQ', data, tmp_path / 'm', '2026-09-30', '2026-10-03')
    result = build_asset_report(['QQQ'], start, end, tmp_path / 'legacy',
        tmp_path / 's', mode='retrospective', market_store=tmp_path / 'm')
    assert result['assets'][0]['daily_attribution']['missing_weight_dates'] == [start]
    assert '逐日' in render_asset_report(result)


def test_daily_report_accepts_new_stock_with_only_its_held_interval(tmp_path):
    for day, ticker in [('2026-09-30', 'AAA'), ('2026-10-01', 'BBB')]:
        raw = json.dumps({'cusip': '46090E103', 'effectiveDate': '2026-10-03',
            'effectiveBusinessDate': day, 'totalNumberOfHoldings': 1,
            'holdings': [{'ticker': ticker, 'cusip': ticker, 'issuerName': ticker,
                         'securityTypeName': 'Common Stock', 'percentageOfTotalNetAssets': 100}]}).encode()
        store_source('QQQ', raw, parse_invesco(raw), tmp_path / 's')
    data = pd.DataFrame({'close': [100., 100., 110.]}, index=pd.to_datetime(['2026-09-30', '2026-10-01', '2026-10-02']))
    for ticker, part in [('QQQ', data), ('AAA', data.iloc[:2]), ('BBB', data.iloc[1:])]:
        store_market(ticker, part, tmp_path / 'm', '2026-09-30', '2026-10-03')
    result = build_asset_report(['QQQ'], '2026-09-30', '2026-10-02', tmp_path / 'legacy',
                               tmp_path / 's', mode='retrospective', market_store=tmp_path / 'm')
    daily = result['assets'][0]['daily_attribution']
    assert daily['days'][1]['covered_weight'] == 1.
    assert daily['days'][1]['missing_tickers'] == []
    assert daily['linked_contribution'] == pytest.approx(.1)
    assert daily['linked_residual'] == pytest.approx(0.)
