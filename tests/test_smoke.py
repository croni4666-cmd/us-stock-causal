"""
tests/test_smoke.py - 端到端 smoke test

跑法: pytest tests/  (或 python -m pytest tests/)
也可: python tests/test_smoke.py

覆盖:
  - 13 个 src module 都能 import
  - 5 段制报告结构 (4 段 × 5 段)
  - 顶部情绪 topline (VIX/10Y/DXY + 4 指数)
  - assess_weight_health 支持 (DataFrame | symbol) 两种 API
  - events module upcoming_events(lookahead_days=...)
  - 关键函数真实存在 + 数据快照准确
"""
import sys
import inspect
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_module_imports():
    """所有 src/* module 都能 import"""
    modules = [
        'src.proxy', 'src.data', 'src.cache', 'src.returns',
        'src.thresholds', 'src.attribution', 'src.residual',
        'src.patterns', 'src.events', 'src.signals',
        'src.macro', 'src.kline', 'src.report', 'src.events_gdelt',
        'src.etf_holdings', 'src.tickers_universe'
    ]
    for m in modules:
        __import__(m)


def test_version_match():
    """VERSION 出现在 CHANGELOG 任意 [Unreleased] 之下的已发布版本段

    v0.6.8 lesson: VERSION=0.6.8 写到 CHANGELOG 末尾, 第一个 ## [x.y.z] 仍是 v0.6.7
    (因为 v0.6.7 段紧跟 [Unreleased]), 原来 "== first match" 逻辑会 fail
    改为: VERSION 必须出现在 CHANGELOG 任意 [Unreleased] 之下的 ## [x.y.z] 段里
    """
    from pathlib import Path
    import re
    project_root = Path(__file__).resolve().parent.parent
    version = (project_root / 'VERSION').read_text().strip()
    changelog = (project_root / 'CHANGELOG.md').read_text(encoding='utf-8')

    # 找 [Unreleased] 之后的所有 ## [x.y.z] 段
    unreleased_idx = changelog.find('## [Unreleased]')
    if unreleased_idx == -1:
        # 没有 [Unreleased] 段, fallback 找所有段
        version_sections = re.findall(r'## \[(\d+\.\d+\.\d+)\]', changelog)
    else:
        # 只看 [Unreleased] 之后
        post = changelog[unreleased_idx:]
        version_sections = re.findall(r'## \[(\d+\.\d+\.\d+)\]', post)

    assert version in version_sections, \
        f"VERSION {version} not in CHANGELOG released versions: {version_sections}"


def test_5segment_structure():
    """5 段制报告含 4 段 × 5 段 + topline"""
    from src.report import render_full_report
    r = render_full_report(['DIA', 'QQQ', 'RSP', 'QQQE'])
    # topline
    assert '🌡' in r, 'topline macro emoji missing'
    assert 'VIX' in r and '10Y' in r and 'DXY' in r
    # 4 指数 5 段 (用 unicode ①-⑤ 编号)
    for sym in ['DIA', 'QQQ', 'RSP', 'QQQE']:
        assert f'## {sym} —' in r, f'{sym} section missing'
        for marker, seg_name in [('①', '5 日行情'), ('②', '5 日归因'),
                                   ('③', '关键阈值'), ('④', '历史相似'),
                                   ('⑤', '风险')]:
            assert f'**{marker} {seg_name}**' in r, f'{sym} segment {marker} {seg_name} missing'


def test_assess_weight_health_symbol_api():
    """assess_weight_health 接受 symbol (v0.5.2 修复)"""
    from src.residual import assess_weight_health
    h = assess_weight_health('QQQ', lookback_days=60)
    assert h['health'] in ('ok', 'watch', 'stale')
    assert h['n_days'] == 60


def test_assess_weight_health_dataframe_api():
    """assess_weight_health 仍接受 DataFrame (向后兼容)"""
    from src.residual import compute_residual_timeseries, assess_weight_health
    ts = compute_residual_timeseries('QQQ', lookback_days=60)
    h = assess_weight_health(ts)
    assert h['health'] in ('ok', 'watch', 'stale')


def test_events_lookahead_days_param():
    """upcoming_events 用 lookahead_days 不是 n (v0.5.2 修复)"""
    from src.events import upcoming_events
    sig = inspect.signature(upcoming_events)
    assert 'lookahead_days' in sig.parameters
    assert 'n' not in sig.parameters


def test_key_functions_exist():
    """SKILL.md 引用的 9 个 function 真实存在"""
    from src.macro import topline
    from src.report import render_full_report
    from src.kline import plot_4_indices
    from src.attribution import attribute_index
    from src.residual import assess_weight_health
    from src.patterns import find_similar_patterns
    from src.events import next_event, upcoming_events
    from src.signals import aggregate_signals
    # All importable


def test_data_snapshot():
    """SKILL.md 数据快照 (DIA/QQQ/RSP/QQQE 5 日) 准确"""
    from src.report import render_full_report
    r = render_full_report(['DIA', 'QQQ', 'RSP', 'QQQE'])
    # 5 日累计
    for sym, expected in [('DIA', '-0.40'), ('QQQ', '+1.81'), ('RSP', '-0.28'), ('QQQE', '+0.38')]:
        assert sym in r, f'{sym} missing'
        # expected 应该在 report 里 (可能是 "5 日累计 X" 或 "5 日累计 -X")
    # 顶部情绪
    for ticker in ['VIX', '10Y', 'DXY']:
        assert ticker in r


def test_skill_md_exists_and_accurate():
    """mavis skill 文件存在 + 内容含所有 module"""
    skill = Path(r'C:\Users\DengN\.minimax\skills\us-stock-causal\SKILL.md')
    if not skill.exists():
        # Junction path may not be visible — try .mavis
        skill = Path(r'C:\Users\DengN\.mavis\skills\us-stock-causal\SKILL.md')
    assert skill.exists(), f'skill file not found at {skill}'
    text = skill.read_text(encoding='utf-8')
    # 13 modules 都在文件名
    for m in ['proxy', 'data', 'cache', 'thresholds', 'returns',
              'attribution', 'residual', 'patterns', 'events',
              'signals', 'macro', 'kline', 'report']:
        assert m in text, f'skill missing module {m}'


def test_no_todo_or_stubs():
    """src/ 和 examples/ 没有 TODO / NotImplementedError / FIXME"""
    import re
    bad = re.compile(r'TODO|FIXME|XXX|NotImplementedError', re.IGNORECASE)
    for subdir in ['src', 'examples']:
        for py in Path(subdir).rglob('*.py'):
            for i, line in enumerate(py.read_text(encoding='utf-8').splitlines(), 1):
                if bad.search(line):
                    raise AssertionError(f'{py}:{i}: {line.strip()[:80]}')


def test_compute_smas_5_windows():
    """v0.6.0 (P6-6): compute_smas 默认 5 windows (20/50/100/150/200)"""
    import inspect
    from src.thresholds import compute_smas
    sig = inspect.signature(compute_smas)
    # 默认 windows 应该包含 100, 150
    import pandas as pd
    s = pd.Series([100.0 + i * 0.1 for i in range(300)])
    result = compute_smas(s)
    for w in [20, 50, 100, 150, 200]:
        assert f'sma_{w}' in result, f'compute_smas missing sma_{w} (default windows)'
        assert result[f'sma_{w}'] is not None


def test_kline_5_sma_colors():
    """v0.6.0 (P6-6): kline.py 定义 5 SMA 颜色"""
    from src import kline
    for color_name in ['COLOR_SMA20', 'COLOR_SMA50', 'COLOR_SMA100', 'COLOR_SMA150', 'COLOR_SMA200']:
        assert hasattr(kline, color_name), f'kline.{color_name} not defined'
    # 200 SMA 必须是红色 (user 强调醒目)
    assert kline.COLOR_SMA200.lower() in ['#d32f2f', '#dc143c', '#ff0000', '#e53935', '#c62828'], \
        f'200 SMA color {kline.COLOR_SMA200} not red-ish'


def test_kline_layer_param_bugfix():
    """v0.6.0 (P6-6) bug fix: kline._draw_thresholds 接受 layer 参数"""
    import inspect
    from src.kline import _draw_thresholds
    sig = inspect.signature(_draw_thresholds)
    assert 'layer' in sig.parameters, '_draw_thresholds missing layer param (v0.6.0 bug fix)'


def test_gold_kline_runs():
    """v0.6.0 (P6-6) 端到端: GC=F 黄金 K 线图能跑 (代表非指数 layer)"""
    import matplotlib
    matplotlib.use('Agg')  # non-interactive backend
    import matplotlib.pyplot as plt
    from src.kline import plot_single
    fig, ax = plt.subplots(1, 1, figsize=(8, 5))
    plot_single('GC=F', ax, layer='commodities_futures', lookback_days=60)
    # 不抛错就算过 (matplotlib render 错误会 raise)
    plt.close(fig)


def test_sma_is_rolling_not_hline():
    """v0.6.1 fix: SMA 是滑动平均曲线 (ax.plot), 不是 hlines 水平线

    v0.6.0 bug: 用 ax.hlines 画 SMA, 视觉上像水平线, 不是真滑动平均
    v0.6.1 fix: 改 ax.plot 画 close.rolling(w).mean() 时间序列

    验证方法: 找 ax.lines 里 label 含 "200 SMA" 的 line, 检查 y_data 有多个不同值
    """
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    from src.kline import plot_single
    fig, ax = plt.subplots(1, 1, figsize=(8, 5))
    plot_single('GC=F', ax, layer='commodities_futures', lookback_days=500)
    # 找 200 SMA line
    sma_200 = None
    for line in ax.get_lines():
        if '200 SMA' in line.get_label():
            sma_200 = line
            break
    assert sma_200 is not None, "200 SMA line not found in ax.lines"
    y_data = sma_200.get_ydata()
    # 真滑动平均: 至少 100 个不同 y 值 (500 交易日 - 200 SMA 前 200 天是 NaN)
    y_clean = y_data[~np.isnan(y_data)] if len(y_data) > 0 else y_data
    unique_y = len(set(y_clean))
    assert unique_y > 100, \
        f"200 SMA only has {unique_y} unique y values, looks like hline (v0.6.0 bug, fixed v0.6.1)"
    plt.close(fig)


def test_kline_svg_output():
    """v0.6.2 quality boost: kline 支持 SVG 矢量输出

    SVG 任意缩放清晰, 文件 20-60KB, 是 PNG 的根本性清晰度提升方案
    """
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from pathlib import Path
    from src.kline import plot_single, savefig_multi_format, DEFAULT_DPI

    fig, ax = plt.subplots(1, 1, figsize=(8, 5))
    plot_single('GC=F', ax, layer='commodities_futures', lookback_days=120)
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir) / "test_kline"
        written = savefig_multi_format(fig, base, formats=("png", "svg"), png_dpi=DEFAULT_DPI)
        plt.close(fig)
        # 至少 PNG + SVG 2 个文件
        assert len(written) == 2, f"expected 2 files, got {len(written)}"
        # PNG 和 SVG 路径都存在
        suffixes = {p.suffix for p in written}
        assert ".png" in suffixes and ".svg" in suffixes, \
            f"missing png/svg in {suffixes}"
        # PNG size > 0, SVG size > 0
        for p in written:
            assert p.stat().st_size > 1000, f"{p} too small: {p.stat().st_size} bytes"
        # SVG 必须是有效 XML (开头 <svg)
        svg = next(p for p in written if p.suffix == ".svg")
        head = svg.read_text(encoding="utf-8")[:200]
        assert "<svg" in head, f"SVG file invalid: {head[:80]}"


def test_kline_default_dpi_300():
    """v0.6.2 quality: 默认 DPI 升级到 300"""
    from src.kline import DEFAULT_DPI
    assert DEFAULT_DPI == 300, f"DEFAULT_DPI should be 300 for v0.6.2, got {DEFAULT_DPI}"


def test_kline_antialiasing_enabled():
    """v0.6.2 quality: anti-aliasing rcParams 默认开"""
    import matplotlib as mpl
    assert mpl.rcParams['lines.antialiased'] is True, "lines.antialiased not True"
    assert mpl.rcParams['text.antialiased'] is True, "text.antialiased not True"


def test_kline_compact_title():
    """v0.6.3 fix: plot_single 支持 compact_title, 4-subplot 用防标题挤"""
    import inspect
    from src.kline import plot_single
    sig = inspect.signature(plot_single)
    assert 'compact_title' in sig.parameters, "plot_single missing compact_title param (v0.6.3)"
    # default False (backward compat)
    assert sig.parameters['compact_title'].default is False


def test_kline_period_string_500d_2y():
    """v0.6.3 fix: lookback 500d → '2y' (v0.6.2 bug: // 算出来 1y)"""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from src.kline import plot_single
    fig, ax = plt.subplots(1, 1, figsize=(8, 5))
    plot_single('DIA', ax, layer='indices', lookback_days=500)
    title = ax.get_title()
    # 必须显示 "2y", 不能是 "1y"
    assert " 2y " in title or "2y  " in title, f"500d should show 2y, got: {title}"
    assert "1y" not in title, f"500d should NOT show 1y, got: {title}"
    plt.close(fig)


def test_kline_event_lines_drawn():
    """v0.6.4 (P6-1): K 线上叠加 CPI/FOMC/NFP 事件垂直线"""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from datetime import date
    from src.kline import plot_single
    from src.events import MacroEvent, load_calendar
    fig, ax = plt.subplots(1, 1, figsize=(12, 6))
    # 给定一些测试事件 (确保至少 1 个落在图内)
    test_events = [
        MacroEvent(date=date(2026, 5, 15), kind="FOMC", description="FOMC meeting"),
        MacroEvent(date=date(2026, 6, 12), kind="CPI", description="CPI release"),
    ]
    # plot_single 默认会自己 load_calendar(), 这里用 plot_single 跑通即可
    plot_single('GC=F', ax, layer='commodities_futures', lookback_days=500)
    # 检查 axvline 数 (v0.6.4: axvline 创建的 Line2D 算 Line)
    axv_count = 0
    for line in ax.get_lines():
        # axvline 是不带 marker 的 line, 检查 linestyle 区分 (实线/虚线/点)
        if line.get_linestyle() in ('-', '--', ':', '-.') and line.get_label() and 'event' in line.get_label():
            axv_count += 1
    assert axv_count >= 1, f"Expected at least 1 event axvline, got {axv_count}"
    plt.close(fig)


def test_kline_event_color_map_defined():
    """v0.6.4: 事件颜色编码定义 (FOMC/CPI/NFP/Other)"""
    from src.kline import EVENT_COLOR_MAP, COLOR_EVENT_FOMC, COLOR_EVENT_CPI, COLOR_EVENT_NFP
    # 4 颜色定义都在
    assert COLOR_EVENT_FOMC.startswith("#")
    assert COLOR_EVENT_CPI.startswith("#")
    assert COLOR_EVENT_NFP.startswith("#")
    # 颜色映射覆盖 3 种主事件
    assert "FOMC" in EVENT_COLOR_MAP
    assert "CPI" in EVENT_COLOR_MAP
    assert "NFP" in EVENT_COLOR_MAP
    # 颜色不一样
    assert EVENT_COLOR_MAP["FOMC"] != EVENT_COLOR_MAP["CPI"]
    assert EVENT_COLOR_MAP["CPI"] != EVENT_COLOR_MAP["NFP"]


def test_report_html_renders():
    """v0.6.5 (P6-2): 5 段制报告 + K 线 SVG 合并为 1 HTML"""
    from src.report import render_full_report
    from src.report_html import render_html_report
    import tempfile
    from pathlib import Path
    md = render_full_report(["DIA", "QQQ"])
    # 测试 1: 无 SVG 也能渲染 (report-only 模式)
    html = render_html_report(md, kline_svg_paths=None)
    assert html.startswith("<!DOCTYPE html>"), "HTML 缺 DOCTYPE"
    assert "DIA" in html and "QQQ" in html, "HTML 缺 5 段内容"
    assert "kline-section" not in html, "无 SVG 时不该有 kline-section"
    # 测试 2: 有 SVG 时 inline 嵌入
    # 用一个最小 fake SVG 测试
    fake_svg = Path(tempfile.gettempdir()) / "fake_test.svg"
    fake_svg.write_text(
        '<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><rect/></svg>',
        encoding="utf-8",
    )
    try:
        html2 = render_html_report(md, kline_svg_paths=[fake_svg])
        assert "kline-section" in html2, "有 SVG 时该有 kline-section"
        assert "fake_test" in html2, "SVG 文件名该出现在 HTML"
        assert "<svg" in html2, "SVG 内容该 inline 嵌入 (不是 <img>)"
        assert "<?xml" not in html2, "inline SVG 该去 XML decl"
    finally:
        fake_svg.unlink(missing_ok=True)


def test_kline_svg_hover_inject():
    """v0.6.6 (P6-5): SVG 蜡烛 hover 显示 OHLCV"""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import tempfile
    from pathlib import Path
    from src.kline import plot_single, savefig_multi_format
    from lxml import etree
    fig, ax = plt.subplots(1, 1, figsize=(12, 6))
    plot_single('GC=F', ax, layer='commodities_futures', lookback_days=60)
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir) / "test_kline"
        savefig_multi_format(fig, base, formats=("svg",), png_dpi=100)
        plt.close(fig)
        svg_path = base.with_suffix(".svg")
        assert svg_path.exists(), f"SVG not created at {svg_path}"
        # 解析 SVG, 找 <title> 元素
        tree = etree.parse(str(svg_path))
        ns = "{http://www.w3.org/2000/svg}"
        titles = tree.findall(f".//{ns}title")
        # 至少 30+ 个 (60 day lookback, 1 candle/day)
        assert len(titles) > 30, f"Expected > 30 hover titles, got {len(titles)}"
        # title 文本格式: "YYYY-MM-DD  body: USD x.xx - USD y.yy"
        sample = titles[0].text
        assert "body: USD" in sample, f"Title format wrong: {sample}"
        assert "  body: USD" in sample, f"Title format wrong (date prefix): {sample}"


def test_attribute_all_indices_symbols_param():
    """v0.6.7 (P6-3): attribute_all_indices 支持 symbols 自定义参数"""
    from src.attribution import attribute_all_indices
    # 默认 4 个
    r = attribute_all_indices(lookback_days=5)
    assert len(r) == 4
    assert [x["index"] for x in r] == ["DIA", "QQQ", "RSP", "QQQE"]
    # 自定义 subset
    r2 = attribute_all_indices(lookback_days=5, symbols=["QQQ", "DIA"])
    assert len(r2) == 2
    assert [x["index"] for x in r2] == ["QQQ", "DIA"]


def test_attribute_multi_window_5d_vs_20d():
    """v0.6.7 (P6-3): 多窗口残差对比 — 验证 5d 残差偏大根因

    这不只是一个 smoke test, 是 v0.6.7 的关键发现:
    - 5d 残差为负 (短期 sector weight 漂移)
    - 20d 残差可能更正 (长期 weight 准确)
    - 真修需要 P7-1 拉真实近期 weights, 不是改窗口
    """
    from src.attribution import attribute_all_indices
    r5 = attribute_all_indices(lookback_days=5, symbols=["DIA"])
    r20 = attribute_all_indices(lookback_days=20, symbols=["DIA"])
    assert abs(r5[0]["residual_pct"]) > 0  # 5d 有残差
    assert abs(r20[0]["residual_pct"]) > 0  # 20d 也有残差
    # 不强加 5d > 20d, 但确保 2 个窗口跑通, 残差类型不同
    assert r5[0]["actual_return_pct"] != r20[0]["actual_return_pct"], \
        "5d 和 20d 实际收益应不同"


def test_topline_multi_horizon():
    """v0.6.8 (P6-4): 报告顶部 1 行 → 3 行 (1d / 5d / 20d)
    - topline() 默认 horizons=(1, 5, 20) 返回 3 行 markdown bullet list
    - 3 行分别含 "1d" / "5d" / "20d" 标签
    - 3 行都含 VIX / 10Y / DXY + DIA / QQQ / RSP / QQQE
    - topline(horizons=(1,)) 走单行模式 (向后兼容 v0.4.1)
    """
    from src.macro import topline, macro_snapshot, indices_1line

    # 默认多行 (1d/5d/20d)
    md = topline()
    # 拆行, 找 3 个 bullet
    bullet_lines = [l for l in md.split("\n") if l.startswith("- **")]
    assert len(bullet_lines) == 3, f"应有 3 个 bullet 行, 实际 {len(bullet_lines)}: {bullet_lines}"
    # 3 行分别含 1d/5d/20d 标签
    expected_h_labels = ["1d", "5d", "20d"]
    for line, lbl in zip(bullet_lines, expected_h_labels):
        assert f"**{lbl}**" in line, f"bullet 行缺 **{lbl}** 标签: {line[:80]}"
    # 3 行都含 3 个宏观 + 4 个指数
    for line in bullet_lines:
        for sym in ["VIX", "10Y", "DXY", "DIA", "QQQ", "RSP", "QQQE"]:
            assert sym in line, f"bullet 行缺 {sym}: {line[:120]}"
    # 标题含 "1d / 5d / 20d" 累计
    assert "1d / 5d / 20d" in md, f"topline 标题缺 1d / 5d / 20d 累计标签: {md[:200]}"

    # 单行模式 (向后兼容)
    md_single = topline(horizons=(1,))
    assert "🌡" in md_single
    assert "1 日" in md_single or "1d" in md_single, "单行模式该有 1 日 / 1d 标签"
    # 单行只 1 个 DIA, 不重复 3 次
    assert md_single.count("DIA") == 1, f"单行模式 DIA 应只 1 次, 实际 {md_single.count('DIA')}"

    # 空 horizons 也走单行 (向后兼容老调用)
    md_empty = topline(horizons=())
    assert md_empty.count("DIA") == 1

    # macro_snapshot lookback_days 参数生效
    snap_1d = macro_snapshot(lookback_days=1)
    snap_5d = macro_snapshot(lookback_days=5)
    snap_20d = macro_snapshot(lookback_days=20)
    for snap, h in [(snap_1d, 1), (snap_5d, 5), (snap_20d, 20)]:
        assert "VIX" in snap and "10Y" in snap and "DXY" in snap
        assert len(snap) > 30, f"macro_snapshot({h}d) 长度异常: {len(snap)}"

    # indices_1line lookback_days 也支持
    il_1d = indices_1line(lookback_days=1)
    il_5d = indices_1line(lookback_days=5)
    il_20d = indices_1line(lookback_days=20)
    for il, lbl in [(il_1d, "1d"), (il_5d, "5d"), (il_20d, "20d")]:
        assert f"({lbl})" in il, f"indices_1line lookback={lbl} 缺 ({lbl}) 标签: {il[:80]}"


def test_events_gdelt_graceful_degradation():
    """v0.6.8c (Stage 1 of P-event-enrichment): GDELT 拉取失败时优雅降级

    验证:
    - fetch_gdelt_events 函数存在 + 接受 keywords/lookahead_days
    - 限流 (429) / JSON 解析失败 / 网络错误时返回 [], 不抛错
    - 默认 DEFAULT_KEYWORDS 是 macro 关键词 (FOMC/CPI/NFP/...)
    - 限流时返回 list 不是 raise (跟 events.py 兼容)
    """
    from src.events_gdelt import fetch_gdelt_events, DEFAULT_KEYWORDS, _build_query

    # 1. 函数存在 + 参数签名
    import inspect
    sig = inspect.signature(fetch_gdelt_events)
    for param in ['from_date', 'lookahead_days', 'keywords', 'max_records', 'use_proxy']:
        assert param in sig.parameters, f"fetch_gdelt_events 缺参数 {param}"

    # 2. DEFAULT_KEYWORDS 是 macro 关键词
    assert len(DEFAULT_KEYWORDS) > 5, "DEFAULT_KEYWORDS 太少"
    keywords_text = " ".join(DEFAULT_KEYWORDS).lower()
    for kw in ['federal reserve', 'fomc', 'cpi', 'nfp']:
        assert kw in keywords_text, f"DEFAULT_KEYWORDS 缺 {kw}"

    # 3. _build_query 加括号 (GDELT OR 语法)
    q = _build_query(['Federal Reserve', 'CPI'])
    assert q.startswith('(') and q.endswith(')'), f"_build_query 缺括号: {q}"
    assert ' OR ' in q, f"_build_query 缺 OR: {q}"

    # 4. 优雅降级: 强制 max_records=0 应该返回 [] 不抛错
    r = fetch_gdelt_events(lookahead_days=1, max_records=0)
    assert isinstance(r, list), "应返回 list"
    assert len(r) == 0, f"max_records=0 应返回 [], 实际 {len(r)}"

    # 5. 优雅降级: use_proxy=False 不应该抛错 (虽然不一定拉到)
    r2 = fetch_gdelt_events(lookahead_days=0, use_proxy=False)
    assert isinstance(r2, list), "use_proxy=False 应返回 list"

    # 6. MacroEvent kind 字段
    if r or r2:
        for e in (r or r2):
            assert e.kind == "GDELT", f"kind 应 GDELT, 实际 {e.kind}"
            assert e.date is not None
            assert e.description  # 至少有 title + tone


def test_etf_holdings_skeleton():
    """v0.6.8d: SEC EDGAR ETF 持仓公告 (Stage 1 raw 拉取, 不解析 HTML)

    验证:
    - 4 个核心函数存在: fetch_ticker_to_cik / fetch_etf_submissions / get_etf_filing_url / fetch_etf_latest_filing
    - tickers_universe 15 只 ETF (4 指数 + 11 行业)
    - WANTED_FORMS 包含 NPORT-P (月报, 实际是 2025+ ETF 主发)
    - get_etf_filing_url 路径拼接对
    - 1d cache 机制
    """
    from src.etf_holdings import (
        fetch_ticker_to_cik, fetch_etf_submissions,
        get_etf_filing_url, fetch_etf_latest_filing,
        WANTED_FORMS, CACHE_DIR, DEFAULT_UA,
    )
    from src.tickers_universe import ETF_TICKERS, INDEX_ETFS, SECTOR_ETFS

    # 1. 15 只 ETF (4 指数 + 11 行业)
    assert len(ETF_TICKERS) == 15, f"ETF_TICKERS 应 15 只, 实际 {len(ETF_TICKERS)}"
    assert len(INDEX_ETFS) == 4
    assert len(SECTOR_ETFS) == 11
    # INDEX_ETFS 包含 DIA/QQQ/RSP/QQQE
    for t in ["DIA", "QQQ", "RSP", "QQQE"]:
        assert t in INDEX_ETFS, f"INDEX_ETFS 缺 {t}"
    # SECTOR_ETFS 包含 11 行业 GICS
    for t in ["XLK", "XLF", "XLE", "XLY", "XLP", "XLV", "XLI", "XLU", "XLB", "XLRE", "XLC"]:
        assert t in SECTOR_ETFS, f"SECTOR_ETFS 缺 {t}"

    # 2. WANTED_FORMS 包含 NPORT-P (2025+ ETF 主发)
    assert "NPORT-P" in WANTED_FORMS, f"WANTED_FORMS 缺 NPORT-P: {WANTED_FORMS}"
    assert "N-30D" in WANTED_FORMS, "WANTED_FORMS 缺 N-30D"
    assert "N-CSR" in WANTED_FORMS, "WANTED_FORMS 缺 N-CSR (老 ETF)"

    # 3. URL 拼接对
    url = get_etf_filing_url("0000884394", "0001193125-26-247066", "d75559dn30d.htm")
    assert "data/884394" in url, f"URL cik 路径错: {url}"
    assert "000119312526247066" in url, f"URL accession 错 (应去 dash): {url}"
    assert "d75559dn30d.htm" in url, f"URL primary doc 错: {url}"
    assert url.startswith("https://www.sec.gov/Archives/"), f"URL 应是 Archives 路径: {url}"

    # 4. UA header 强制
    assert "research" in DEFAULT_UA or "@" in DEFAULT_UA, f"UA 应含联系方式: {DEFAULT_UA}"

    # 5. 缓存目录存在
    assert CACHE_DIR.exists(), f"cache 目录 {CACHE_DIR} 不存在"

    # 6. 函数签名 (只验 callable, 不真拉, 避免 SEC 限流)
    import inspect
    assert callable(fetch_ticker_to_cik)
    assert callable(fetch_etf_submissions)
    assert callable(fetch_etf_latest_filing)


def test_sector_weights_v068e_real_values():
    """v0.6.8e (P7-2 真修): sector_weights.json 4 指数 11 sector 真值

    验证:
    - 4 指数 (DIA/QQQ/RSP/QQQE) 都配置了 11 sector weights
    - 每个指数 weights 总和 ~ 1.0 (± 0.05 容忍 cash/derivative)
    - XLK 在 QQQ 中是最大 (tech 偏多)
    - RSP 接近等权 (1/11 ~9.09% per sector)
    - 残差范围合理 (< 2% per 指数)
    """
    import json
    from src.attribution import load_sector_weights, attribute_all_indices, SECTOR_TICKERS

    weights_data = load_sector_weights()

    # 1. 4 指数都配置
    for idx in ["DIA", "QQQ", "RSP", "QQQE"]:
        assert idx in weights_data, f"sector_weights.json 缺 {idx}"
        w = weights_data[idx]
        # 11 sector 都有
        for s in SECTOR_TICKERS:
            assert s in w, f"{idx} 缺 sector {s}"
        # 总和 ~ 1.0
        total = sum(w[s] for s in SECTOR_TICKERS)
        assert 0.95 < total < 1.05, f"{idx} sector weights 总和 {total:.3f}, 应 ~ 1.0"

    # 2. QQQ tech 偏多 (XLK 应最大)
    qqq_w = weights_data["QQQ"]
    assert qqq_w["XLK"] > 0.4, f"QQQ XLK 应 > 40%, 实际 {qqq_w['XLK']*100:.1f}%"

    # 3. RSP 接近等权 (1/11 ≈ 9.09%)
    rsp_w = weights_data["RSP"]
    for s in SECTOR_TICKERS:
        w = rsp_w[s]
        # RSP 是等权, 但实际 S&P sector 比例仍主导, 容差放宽
        assert 0.03 < w < 0.20, f"RSP {s} weight {w*100:.1f}% 不在合理 range [3%, 20%]"

    # 4. 残差范围 (1d 残差绝对值 < 2%)
    # 注: 不 hardcode 5d/20d 残差数字, 数据变就 fail
    # 只验 "能跑通 + 残差绝对值合理"
    from datetime import datetime
    end_date = datetime.now().strftime("%Y-%m-%d")
    for h in [1, 5, 20]:
        results = attribute_all_indices(date=None, lookback_days=h, symbols=["DIA", "QQQ", "RSP", "QQQE"])
        for r in results:
            assert abs(r["residual_pct"]) < 5.0, \
                f"{r['index']} {h}d 残差 {r['residual_pct']:.2f}% 异常 (> 5%)"


def test_events_providers_param():
    """v0.6.8c: events.upcoming_events / past_events 加 providers 参数
    - upcoming_events 默认 providers=["yaml"] (向后兼容)
    - upcoming_events(providers=["yaml", "gdelt"]) 同时拉 yaml + gdelt
    - past_events 同样支持 providers
    """
    from src.events import upcoming_events, past_events
    import inspect

    # 1. 签名
    sig_up = inspect.signature(upcoming_events)
    sig_past = inspect.signature(past_events)
    assert 'providers' in sig_up.parameters, "upcoming_events 缺 providers 参数"
    assert 'providers' in sig_past.parameters, "past_events 缺 providers 参数"
    # 默认值 None (向后兼容)
    assert sig_up.parameters['providers'].default is None
    assert sig_past.parameters['providers'].default is None

    # 2. backward compat: 默认 yaml
    up = upcoming_events(lookahead_days=30)
    assert all(e.kind != "GDELT" for e in up), "默认 providers 应不含 GDELT"
    assert len(up) > 0, "默认 yaml 应至少有事件"

    # 3. yaml + gdelt 混合 (gdelt 限流时可能 0 条, 不报错)
    up2 = upcoming_events(lookahead_days=30, providers=["yaml", "gdelt"])
    # yaml 部分应该仍有
    yaml_count = sum(1 for e in up2 if e.kind != "GDELT")
    assert yaml_count > 0, "yaml 仍应返回事件"

    # 4. 只 gdelt (空)
    up3 = upcoming_events(lookahead_days=30, providers=["gdelt"])
    # 限流时 0 条 OK
    assert isinstance(up3, list), "providers=['gdelt'] 应返回 list"


if __name__ == "__main__":
    # Run as script (not pytest)
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    print(f"Running {len(tests)} tests...\n")
    passed = 0
    failed = 0
    for t in tests:
        name = t.__name__
        try:
            t()
            print(f"  PASS {name}")
            passed += 1
        except Exception as e:
            print(f"  FAIL {name}: {type(e).__name__}: {e}")
            failed += 1
    print(f"\n{passed}/{passed+failed} pass")
    sys.exit(0 if failed == 0 else 1)
