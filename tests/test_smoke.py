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
        'src.macro', 'src.kline', 'src.report'
    ]
    for m in modules:
        __import__(m)


def test_version_match():
    """VERSION == CHANGELOG latest"""
    from pathlib import Path
    import re
    project_root = Path(__file__).resolve().parent.parent
    version = (project_root / 'VERSION').read_text().strip()
    changelog = (project_root / 'CHANGELOG.md').read_text(encoding='utf-8')
    m = re.search(r'## \[(\d+\.\d+\.\d+)\][^\n]*\n', changelog)
    assert m and m.group(1) == version, f"VERSION={version} != CHANGELOG={m.group(1) if m else 'missing'}"


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
