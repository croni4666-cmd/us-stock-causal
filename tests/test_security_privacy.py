import io
import os
from pathlib import Path
import pytest
from lxml import html
from loguru import logger


def test_html_report_escapes_title_and_sanitizes_markdown():
    from src.report_html import render_html_report
    report = render_html_report('<img src="https://example.invalid/p" onerror="alert(1)"><script>alert(1)</script>\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\n`code` [safe](https://example.invalid) [bad](javascript:alert(1))', title='</title><script>alert(2)</script>')
    doc = html.fromstring(report)
    assert not doc.xpath('//script|//img|//*[@onerror]')
    assert not doc.xpath('//a[starts-with(@href,"javascript:")]')
    assert doc.xpath('//table') and doc.xpath('//code')
    assert doc.xpath('//a[@href="https://example.invalid"]')
    assert doc.xpath('//title')[0].text == '</title><script>alert(2)</script>'


def test_svg_sanitizer_preserves_local_refs_and_removes_active_content(tmp_path):
    from src.report_html import _read_svg_inline
    path = tmp_path / 'chart.svg'
    path.write_text('<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"><defs><path id="p" d="M0 0"/></defs><use href="#p"/><script>alert(1)</script><foreignObject><p>html</p></foreignObject><image href="https://example.invalid/p"/><path style="fill:url(https://example.invalid/p)" data-ohlcv="safe"/></svg>')
    text = _read_svg_inline(path)
    assert 'onload' not in text and '<script' not in text and 'foreignObject' not in text
    assert 'https://' not in text and 'data-ohlcv="safe"' in text
    assert '#svg-' in text


def test_svg_rejects_xml_entities(tmp_path):
    from src.report_html import _read_svg_inline
    path = tmp_path / 'chart.svg'
    path.write_text('<!DOCTYPE svg [<!ENTITY marker "entity marker">]><svg xmlns="http://www.w3.org/2000/svg"><text>&marker;</text></svg>')
    with pytest.raises(ValueError):
        _read_svg_inline(path)


def test_report_rejects_malformed_links_without_breaking_render():
    from src.report_html import render_html_report
    doc = html.fromstring(render_html_report('<a href="http://[">broken</a><a href="jav&#9;ascript:alert(1)">bad</a><a href="#note">note</a><script src="https://example.invalid/p"></script>'))
    assert not doc.xpath('//script')
    assert doc.xpath('//a/@href') == ['#note']


def test_svg_external_dtd_and_stylesheet_never_load(tmp_path,monkeypatch):
    from src.report_html import _read_svg_inline
    path = tmp_path/'chart.svg'
    path.write_text('<?xml-stylesheet href="https://example.invalid/p"?><!DOCTYPE svg SYSTEM "https://example.invalid/p"><svg xmlns="http://www.w3.org/2000/svg"><style>@import "https://example.invalid/p";</style><path style="fill: red; stroke: url(https://example.invalid/p)"/></svg>')
    text = _read_svg_inline(path)
    assert 'example.invalid' not in text and 'fill: red' in text


def test_normal_market_cache_symbols_remain_supported(tmp_path):
    from src.cache import cache_path
    for symbol, name in [('^VIX','_VIX'), ('GC=F','GC_F'), ('BRK.B','BRK_B')]:
        assert cache_path(symbol,'indices',tmp_path) == tmp_path/'indices'/(name+'.parquet')


@pytest.mark.parametrize('symbol', ['../a', '..\\a', '/a', 'C:\\a', 'C:a', 'a/b', 'a\\b', 'CON', 'NUL', 'AUX', '.','..'])
def test_cache_rejects_unsafe_symbol(tmp_path, symbol):
    from src.cache import cache_path
    with pytest.raises(ValueError):
        cache_path(symbol, 'indices', tmp_path)


@pytest.mark.parametrize('layer', ['../a', '..\\a', '/a', 'C:\\a', 'C:a', 'a/b', 'a\\b', '.', '..'])
def test_cache_rejects_unsafe_layer(tmp_path, layer):
    from src.cache import cache_path
    with pytest.raises(ValueError):
        cache_path('QQQ', layer, tmp_path)


def test_alert_date_rejects_traversal_and_invalid_date(monkeypatch,tmp_path):
    from src import alert_logger
    monkeypatch.setattr(alert_logger,'ALERT_DIR',tmp_path)
    for value in ['/../../outside/a', '2026-99-99', '2026-1-1', 'C:\\a']:
        with pytest.raises(ValueError): alert_logger.write_alerts(value, [])
    assert alert_logger.write_alerts('2026-10-08', []).parent == tmp_path


def test_proxy_preserves_url_case_and_redacts_credentials(monkeypatch):
    monkeypatch.setenv('US_STOCK_PROXY', 'off')
    from src import proxy
    output=io.StringIO(); sink=logger.add(output)
    url='http://AuditUser:CaseSensitiveSentinel@localhost:9999'
    try:
        assert proxy.setup_proxy(url)==url
        assert os.environ['HTTPS_PROXY']==url
    finally: logger.remove(sink)
    assert 'CaseSensitiveSentinel' not in output.getvalue()
    assert 'AuditUser' not in output.getvalue()
    proxy.setup_proxy('off')


def test_n30d_cache_key_cannot_escape_or_collide(monkeypatch,tmp_path):
    from types import SimpleNamespace
    from src import etf_holdings_parser as parser
    cache = tmp_path/'cache'; cache.mkdir()
    monkeypatch.setattr(parser,'CACHE_DIR',cache)
    calls = []
    def get(url,**kwargs):
        calls.append(url)
        return MockStreamResponse(('body-'+str(len(calls))).encode())
    monkeypatch.setattr(parser.requests,'get',get)
    first='https://www.sec.gov/Archives/one/report.htm'
    second='https://www.sec.gov/Archives/two/report.htm'
    assert parser.fetch_n30d_html(first)=='body-1'
    assert parser.fetch_n30d_html(second)=='body-2'
    parser.fetch_n30d_html('https://www.sec.gov/Archives/..\\outside\\marker',False)
    assert len(list(cache.glob('*.html')))==3
    assert not (tmp_path/'outside'/'marker.html').exists()
    assert parser.fetch_n30d_html(first)=='body-1'
    assert len(calls)==3


def test_archived_webhook_logs_do_not_reveal_bearer_token(monkeypatch,capsys):
    import sys
    from archive import feishu_push
    webhook='https://open.feishu.cn/open-apis/bot/v2/hook/AuditBearerSentinelMixedCase'
    monkeypatch.setattr(sys,'argv',['feishu_push','--dry-run','--webhook',webhook])
    monkeypatch.setattr(feishu_push,'render_full_report',lambda *args:'local report')
    monkeypatch.setattr(feishu_push,'topline',lambda:'local topline')
    assert feishu_push.main()==0
    stdout = capsys.readouterr().out
    assert 'Webhook:' not in stdout
    assert 'AuditBearerSentinelMixedCase' not in stdout
    def fail(*args,**kwargs):
        raise RuntimeError('connection refused '+webhook)
    monkeypatch.setattr(feishu_push.requests,'post',fail)
    output=io.StringIO(); sink=logger.add(output)
    try:
        assert feishu_push.send_to_feishu(webhook,{}) is False
    finally: logger.remove(sink)
    assert 'AuditBearerSentinelMixedCase' not in output.getvalue()


@pytest.mark.parametrize('status,data', [(400,{}),(200,{'code':1})])
def test_archived_webhook_server_error_body_is_not_logged(monkeypatch,status,data):
    from types import SimpleNamespace
    from archive import feishu_push
    response = SimpleNamespace(status_code=status,text='AuditServerSecretSentinel',json=lambda:{**data,'message':'AuditServerSecretSentinel'})
    monkeypatch.setattr(feishu_push.requests,'post',lambda *args,**kwargs:response)
    output=io.StringIO(); sink=logger.add(output)
    try: assert feishu_push.send_to_feishu('https://example.invalid/hook',{}) is False
    finally: logger.remove(sink)
    assert 'AuditServerSecretSentinel' not in output.getvalue()


def test_proxy_auto_preserves_explicit_environment_when_probe_absent(monkeypatch):
    from src import proxy
    for key in ('HTTP_PROXY','HTTPS_PROXY','http_proxy','https_proxy'):
        monkeypatch.delenv(key, raising=False)
    explicit='http://User:MixedCaseAuditPassword@localhost:9911'
    monkeypatch.setenv('HTTPS_PROXY',explicit)
    monkeypatch.setattr(proxy,'_detect_clash_proxy',lambda:None)
    output=io.StringIO(); sink=logger.add(output)
    try:
        assert proxy.setup_proxy('auto')==explicit
        assert os.environ['HTTPS_PROXY']==explicit
    finally: logger.remove(sink)
    assert 'MixedCaseAuditPassword' not in output.getvalue()


class MockStreamResponse:
    def __init__(self, body=b'body', headers=None):
        self.body=body; self.headers=headers or {}; self.encoding='utf-8'; self.status_code=200
        self.closed=False; self.iterated=False
    def raise_for_status(self): pass
    def iter_content(self,chunk_size):
        self.iterated=True
        for offset in range(0,len(self.body),chunk_size): yield self.body[offset:offset+chunk_size]
    def close(self): self.closed=True
    @property
    def text(self): return self.body.decode()
    def json(self):
        import json
        return json.loads(self.body)


def test_bounded_http_stops_on_oversize_and_closes(monkeypatch):
    import requests
    from src.http_safety import get_bounded
    response=MockStreamResponse(b'x'*17)
    flags={}
    def get(url,**kwargs): flags.update(kwargs); return response
    monkeypatch.setattr(requests,'get',get)
    with pytest.raises(ValueError): get_bounded('https://example.invalid/local', max_bytes=16)
    assert flags['stream'] is True and response.closed


def test_bounded_http_preserves_json_and_closes(monkeypatch):
    import requests
    from src.http_safety import get_bounded
    response=MockStreamResponse(b'{"hello":"world"}',{'content-type':'application/json'})
    monkeypatch.setattr(requests,'get',lambda *args,**kwargs:response)
    result=get_bounded('https://example.invalid/local')
    assert result.json()=={'hello':'world'} and response.closed


@pytest.mark.parametrize('target',['n30d','etf','gdelt','sec_facts'])
def test_legacy_downloaders_use_bounded_stream(monkeypatch,tmp_path,target):
    import requests
    from src import http_safety
    monkeypatch.setattr(http_safety,'MAX_BYTES',16)
    response=MockStreamResponse(b'x'*17,{'content-type':'application/json'})
    flags={}
    def get(url,**kwargs): flags.update(kwargs); return response
    monkeypatch.setattr(requests,'get',get)
    if target=='n30d':
        from src import etf_holdings_parser as module
        monkeypatch.setattr(module,'CACHE_DIR',tmp_path)
        assert module.fetch_n30d_html('https://example.invalid/local',False) is None
    elif target=='etf':
        from src import etf_holdings as module
        monkeypatch.setattr(module,'CACHE_DIR',tmp_path)
        assert module.fetch_etf_submissions('0000000001',True)['recent_filings']==[]
    elif target=='gdelt':
        from src import events_gdelt as module
        assert module.fetch_gdelt_events()==[]
    else:
        from tools import sec_fetch as module
        monkeypatch.setattr(module,'_CACHE_DIR',str(tmp_path))
        monkeypatch.setattr(module,'get_company_cik',lambda *args:'0000000001')
        with pytest.raises(ValueError):module.get_company_facts('LOCAL',False)
    assert flags['stream'] is True and response.closed


def test_n30d_expires_after_one_day(monkeypatch,tmp_path):
    import hashlib,time
    from src import etf_holdings_parser as module
    url='https://example.invalid/local'
    path=tmp_path/(hashlib.sha256(url.encode()).hexdigest()+'.html')
    path.write_text('old')
    os.utime(path,(time.time()-86401,time.time()-86401))
    monkeypatch.setattr(module,'CACHE_DIR',tmp_path)
    monkeypatch.setattr(module.requests,'get',lambda *args,**kwargs:MockStreamResponse(b'fresh'))
    assert module.fetch_n30d_html(url)=='fresh'


@pytest.mark.parametrize('script',['tools/sec_fetch.py','src/etf_holdings_parser.py','src/events_gdelt.py','src/etf_holdings.py'])
def test_standalone_legacy_module_imports_shared_helper_without_network(script):
    import subprocess,sys
    code = ('import os,socket,runpy; '
            'os.makedirs=lambda *args,**kwargs:None; '
            'socket.create_connection=lambda *args,**kwargs:(_ for _ in ()).throw(OSError("disabled")); '
            'runpy.run_path('+repr(script)+',run_name="__offline_audit__")')
    completed=subprocess.run([sys.executable,'-X','utf8','-I','-c',code],capture_output=True,text=True,timeout=30)
    assert completed.returncode==0,completed.stderr


def test_sec_import_respects_shared_proxy_and_has_no_global_side_effects(monkeypatch,tmp_path):
    import importlib,socket,requests
    from contextlib import nullcontext
    from src import proxy
    from tools import sec_fetch
    monkeypatch.setenv('US_STOCK_PROXY','off')
    monkeypatch.setenv('HTTPS_PROXY','http://ExplicitAuditProxy:9888')
    probes=[]; directories=[]
    monkeypatch.setattr(socket,'create_connection',lambda *args,**kwargs:(probes.append(args),nullcontext())[1])
    monkeypatch.setattr(os.path,'expanduser',lambda *args:str(tmp_path))
    monkeypatch.setattr(os,'makedirs',lambda *args,**kwargs:directories.append(args))
    sentinel=lambda *args,**kwargs:None
    monkeypatch.setattr(requests.Session,'get',sentinel)
    before=os.environ['HTTPS_PROXY']
    importlib.reload(sec_fetch)
    assert probes==[]
    assert directories==[]
    assert requests.Session.get is sentinel
    assert os.environ['HTTPS_PROXY']==before


def test_sec_cache_directory_is_created_only_when_writing(monkeypatch,tmp_path):
    import json
    from tools import sec_fetch
    cache=tmp_path/'new-cache'
    monkeypatch.setattr(sec_fetch,'_CACHE_DIR',str(cache))
    body=json.dumps({'0':{'ticker':'LOCAL','cik_str':1}}).encode()
    monkeypatch.setattr(sec_fetch.requests,'get',lambda *args,**kwargs:MockStreamResponse(body))
    assert sec_fetch._load_ticker_map()=={'LOCAL':'0000000001'}
    assert (cache/'tickers.json').exists()


@pytest.mark.parametrize('attribute',['fill','stroke','clip-path'])
def test_svg_presentation_attributes_reject_escaped_external_css(attribute):
    from lxml import etree
    from src.svg_metadata import sanitize_svg
    root=etree.fromstring(b'<svg xmlns="http://www.w3.org/2000/svg"><path/></svg>')
    node=root[0];node.set(attribute,chr(92)+'75rl(https://example.invalid/audit.svg#paint)')
    sanitize_svg(root)
    assert node.get(attribute) is None
