"""Synthetic issuer-shaped samples; no redistribution of issuer archives."""
import io
import json
from pathlib import Path
from zipfile import ZipFile
from xml.sax.saxutils import escape

import pytest

from src.asset_sources import (parse_invesco, parse_ishares, parse_spdr,
                               store_source, load_sources, eligible_snapshot, capture_source)


def qqq_bytes(**changes):
    data = {"cusip": "46090E103", "effectiveDate": "2026-10-03",
            "effectiveBusinessDate": "2026-10-02", "totalNumberOfHoldings": 4,
            "holdings": [
                {"ticker": "AAA", "cusip": "111", "issuerName": "Alpha",
                 "securityTypeName": "Common Stock", "percentageOfTotalNetAssets": 80},
                {"ticker": "USD", "cusip": "USD", "issuerName": "Cash",
                 "securityTypeName": "Currency", "percentageOfTotalNetAssets": 20.1},
                {"ticker": None, "cusip": None, "issuerName": "Synthetic Cash",
                 "securityTypeName": "Synthetic Cash", "percentageOfTotalNetAssets": -.1},
                {"ticker": "USDPDV", "cusip": None, "issuerName": "Dividend",
                 "securityTypeName": "Currency", "percentageOfTotalNetAssets": None}]}
    data.update(changes)
    return json.dumps(data).encode()


def bond_bytes(symbol="TLT", weight="99.50", duration="14.00"):
    name = "iShares 20+ Year Treasury Bond ETF" if symbol == "TLT" else "iShares 7-10 Year Treasury Bond ETF"
    return (f'{name}\nFund Holdings as of,"Oct 01, 2026"\n'
            'Name,Sector,Asset Class,Market Value,Weight (%),CUSIP,Duration,YTM (%),Maturity\n'
            f'"TREASURY BOND",Treasuries,Fixed Income,"1,234.00",{weight},ABC,{duration},5.63,"May 15, 2055"\n'
            'USD,Cash and/or Derivatives,Cash,10,0.50,USD,0,-,-\n').encode()


def gold_xlsx(rows=None):
    rows = rows or [
        ["Date", "Closing Price", "Ounces of Gold per Share", "NAV/Share at 10:30am NYT",
         "Indicative Price per Share at 4:15pm NYT", "Mid point of bid/ask spread at 4:15pm NYT",
         "Premium/Discount of GLD Mid Point vs Indicative Value of GLD at 4:15pm NYT"],
        ["01-Oct-2026", 100, .09, 101, 100, 100.1, .1],
        ["02-Oct-2026", "US Holiday", "US Holiday", "US Holiday", "US Holiday", "US Holiday", "US Holiday"]]
    xml_rows = []
    for n, row in enumerate(rows, 1):
        cells = ''.join(f'<c r="{chr(65+i)}{n}" t="inlineStr"><is><t>{escape(str(v))}</t></is></c>'
                        for i, v in enumerate(row))
        xml_rows.append(f'<row r="{n}">{cells}</row>')
    out = io.BytesIO()
    with ZipFile(out, "w") as z:
        z.writestr('xl/workbook.xml', '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                   'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                   '<sheets><sheet name="US GLD Historical Archive" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr('xl/worksheets/sheet1.xml', '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                   '<sheetData>' + ''.join(xml_rows) + '</sheetData></worksheet>')
    return out.getvalue()


def test_invesco_uses_business_date_and_preserves_unknown_signed_cash():
    result = parse_invesco(qqq_bytes())
    assert result['as_of'] == '2026-10-02'
    assert result['effective_date'] == '2026-10-03'
    assert result['rows'][0]['weight'] == .8
    assert result['rows'][2]['weight'] == -.001
    assert result['rows'][3]['weight'] is None
    assert result['warnings']


@pytest.mark.parametrize('change', [{'cusip': 'OTHER'}, {'holdings': []},
                                    {'effectiveBusinessDate': 'tomorrow'}, {'totalNumberOfHoldings': 999}])
def test_invesco_rejects_wrong_fund_date_or_incomplete_document(change):
    with pytest.raises(ValueError):
        parse_invesco(qqq_bytes(**change))


def test_invesco_rejects_duplicate_stock():
    data = json.loads(qqq_bytes())
    data['holdings'][1] = data['holdings'][0]
    with pytest.raises(ValueError, match='duplicate'):
        parse_invesco(json.dumps(data).encode())


@pytest.mark.parametrize('symbol', ['IEF', 'TLT'])
def test_ishares_parses_quoted_metadata_and_percentage_units(symbol):
    doc = parse_ishares(bond_bytes(symbol), symbol)
    assert doc['as_of'] == '2026-10-01'
    assert doc['rows'][0]['weight'] == .995
    assert doc['rows'][0]['duration_years'] == 14
    assert doc['rows'][0]['yield_pct'] == 5.63
    assert doc['rows'][1]['yield_pct'] is None


@pytest.mark.parametrize('data', [bond_bytes('IEF'), bond_bytes(weight='NaN'),
                                bond_bytes(duration='-3'), b'<html>blocked</html>'])
def test_ishares_rejects_wrong_fund_bad_units_and_html(data):
    with pytest.raises(ValueError):
        parse_ishares(data, 'TLT')


def test_spdr_keeps_pricing_clocks_and_skips_holiday_rows():
    doc = parse_spdr(gold_xlsx())
    assert doc['as_of'] == '2026-10-01'
    assert len(doc['rows']) == 1
    assert doc['rows'][0]['nav_1030'] == 101
    assert doc['rows'][0]['premium_pct_1615'] == .1
    assert doc['rows'][0]['ounces_per_share'] == .09


def test_store_and_load_verify_hash_without_changing_capture_time(tmp_path):
    raw = qqq_bytes()
    path = store_source('QQQ', raw, parse_invesco(raw), tmp_path,
                        retrieved_at='2026-10-03T14:00:00+00:00')
    docs = load_sources('QQQ', tmp_path)
    assert len(docs) == 1
    assert docs[0]['available_at'] == '2026-10-03T14:00:00+00:00'
    assert docs[0]['sha256']
    path.with_suffix('.raw').write_bytes(b'corrupt')
    with pytest.raises(ValueError, match='hash'):
        load_sources('QQQ', tmp_path)


def test_cutoffs_reject_future_weights_and_later_downloads(tmp_path):
    raw = qqq_bytes()
    store_source('QQQ', raw, parse_invesco(raw), tmp_path,
                 retrieved_at='2026-10-03T14:00:00+00:00')
    doc = load_sources('QQQ', tmp_path)[0]
    assert eligible_snapshot(doc, '2026-10-01', 'retrospective') is False
    assert eligible_snapshot(doc, '2026-10-02', 'retrospective') is True
    assert eligible_snapshot(doc, '2026-10-02', 'point_in_time') is False
    assert eligible_snapshot(doc, '2026-10-05', 'point_in_time') is True
    with pytest.raises(ValueError):
        eligible_snapshot(doc, '2026-10-05', 'unknown')


def test_availability_requires_timezone_and_asof_cannot_be_future(tmp_path):
    raw = qqq_bytes()
    for captured in ['2026-10-03T14:00:00', '2026-10-01T14:00:00+00:00']:
        with pytest.raises(ValueError):
            store_source('QQQ', raw, parse_invesco(raw), tmp_path, retrieved_at=captured)


def test_capture_rejects_unsupported_symbol_before_request(tmp_path):
    with pytest.raises(ValueError, match='unsupported'):
        capture_source('../../OTHER', tmp_path)


def test_cash_without_cusip_has_explicit_cash_identity():
    raw = bond_bytes().replace(b'USD,Cash and/or Derivatives,Cash,10,0.50,USD',
                               b'USD CASH,Cash and/or Derivatives,Cash,10,0.50,-')
    doc = parse_ishares(raw, 'TLT')
    assert doc['rows'][1]['id'] == 'Cash:USD CASH'


def test_gold_awaited_field_is_missing_not_zero_or_dropped_date():
    raw = gold_xlsx([['Date', 'Closing Price', 'Ounces of Gold per Share', 'NAV/Share at 10:30am NYT',
                      'Indicative Price per Share at 4:15pm NYT', 'Mid point of bid/ask spread at 4:15pm NYT',
                      'Premium/Discount of GLD Mid Point vs Indicative Value of GLD at 4:15pm NYT'],
                     ['01-Oct-2026', 100, .09, 'AWAITED', 100, 100.1, .1]])
    doc = parse_spdr(raw)
    assert doc['rows'][0]['nav_1030'] is None
    assert doc['rows'][0]['close'] == 100
