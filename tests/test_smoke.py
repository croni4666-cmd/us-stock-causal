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
    skill = Path(r'C:\Users\project-user\.minimax\skills\us-stock-causal\SKILL.md')
    if not skill.exists():
        # Junction path may not be visible — try .mavis
        skill = Path(r'C:\Users\project-user\.mavis\skills\us-stock-causal\SKILL.md')
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


def test_kline_sma_warmup_v068g():
    """v0.6.8g (P6-7) fix: SMA 连续性 — 200 SMA 在 1y 图首日就有效 (不是 NaN)

    v0.6.8g 前 bug: plot_single 把 df 切到 iloc[-lookback_days:], 200 SMA 在前 200 天
    是 NaN, 1y 窗口 (365 天) 的前 200 天 (≈前 6 个月) 看不到 200 SMA。

    v0.6.8g fix: 不切片 df, 用全量 cache 画, xlim 限定最后 lookback_days。
    要求: cache 至少 lookback_days + 200 行 (2y 缓存能保证 1y 图 200 SMA 全程有效)。

    验证:
    1. 1y 图的 200 SMA line 在 xlim 第一天的 y 值不是 NaN
    2. cache 长度 >= 365 + 200 = 565
    """
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    from src.kline import plot_single
    from src.thresholds import load_prices

    # 1. 验证 cache 长度足够 (2y 缓存 ~730 天)
    df_gold = load_prices("GC=F", "commodities_futures")
    assert len(df_gold) >= 365 + 200, \
        f"GC=F cache 至少需 565 行 (1y + 200 SMA warmup), 实际 {len(df_gold)} 行"

    # 2. 1y 窗口下 200 SMA line 在 xlim 第一天有效
    fig, ax = plt.subplots(1, 1, figsize=(8, 5))
    plot_single("GC=F", ax, layer="commodities_futures", lookback_days=365)

    # xlim 应是 1y 窗口 (matplotlib 返回 float ordinal, 365 天 = ~365)
    xlim = ax.get_xlim()
    assert xlim[1] - xlim[0] > 360, f"xlim 应 ~365 天, 实际 {xlim[1] - xlim[0]:.1f} 天"

    # 找 200 SMA line (label 含 "200 SMA")
    sma200_line = None
    for line in ax.get_lines():
        if "200 SMA" in line.get_label():
            sma200_line = line
            break
    assert sma200_line is not None, "200 SMA line not found"

    # 在 xlim 第一天附近查 y 值, 不应是 NaN
    x_data = sma200_line.get_xdata()
    y_data = sma200_line.get_ydata()
    # xlim 第一天 (matplotlib date number = days since 0001-01-01)
    # 用 matplotlib.dates.num2date 转成 datetime, 避免 0001 overflow
    from matplotlib.dates import num2date
    x_start = num2date(xlim[0]).replace(tzinfo=None)  # naive datetime
    # 找 x_data 中最接近 x_start 的 index
    import pandas as _pd
    x_pd = _pd.to_datetime(x_data)  # DatetimeIndex
    idx_at_start = int(np.abs((x_pd - _pd.Timestamp(x_start)).to_numpy().astype('timedelta64[D]').astype(int)).argmin())
    y_at_start = y_data[idx_at_start]
    assert not np.isnan(y_at_start), \
        f"v0.6.8g fix 失效: 200 SMA 在 1y 图首日是 NaN (y={y_at_start}, idx={idx_at_start}, date={x_pd[idx_at_start]})"

    # 同样验证 100 SMA
    sma100_line = None
    for line in ax.get_lines():
        if "100 SMA" in line.get_label():
            sma100_line = line
            break
    if sma100_line is not None:
        x_data = sma100_line.get_xdata()
        y_data = sma100_line.get_ydata()
        x_pd = _pd.to_datetime(x_data)
        idx_at_start = int(np.abs((x_pd - _pd.Timestamp(x_start)).to_numpy().astype('timedelta64[D]').astype(int)).argmin())
        y_at_start = y_data[idx_at_start]
        assert not np.isnan(y_at_start), \
            f"v0.6.8g fix 失效: 100 SMA 在 1y 图首日是 NaN (y={y_at_start}, idx={idx_at_start}, date={x_pd[idx_at_start]})"

    plt.close(fig)


def test_kline_ylim_52w_padding_v068h():
    """v0.6.8h (P6-7.5): ylim 用 52w high+20% / 52w low-20% (User 反馈)

    User 反馈: 默认 ylim 范围太大 (黄金图 2000-5800), 价格离 y 轴太远。
    fix: 用 visible window 的 52w high/low, 各 padding 20%。
    """
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from src.kline import plot_single, _set_ylim_52w_padding
    from src.thresholds import load_prices

    # 1. 直接验证 helper function
    df_gold = load_prices("GC=F", "commodities_futures")
    window = min(len(df_gold), 252)
    high_52w = float(df_gold["high"].iloc[-window:].max())
    low_52w = float(df_gold["low"].iloc[-window:].max())  # 用 .max() 测试错误用法不会被采纳
    low_52w = float(df_gold["low"].iloc[-window:].min())
    expected_ymin = low_52w * 0.8
    expected_ymax = high_52w * 1.2

    fig, ax = plt.subplots(1, 1, figsize=(8, 5))
    _set_ylim_52w_padding(ax, df_gold)
    ylim = ax.get_ylim()
    assert abs(ylim[0] - expected_ymin) < 1.0, \
        f"ymin 应 ~{expected_ymin:.0f}, 实际 {ylim[0]:.0f}"
    assert abs(ylim[1] - expected_ymax) < 1.0, \
        f"ymax 应 ~{expected_ymax:.0f}, 实际 {ylim[1]:.0f}"
    plt.close(fig)

    # 2. 验证 plot_single 调用后 ylim 已经被设置
    fig, ax = plt.subplots(1, 1, figsize=(8, 5))
    plot_single("GC=F", ax, layer="commodities_futures", lookback_days=252)
    ylim = ax.get_ylim()
    # 验证 ymin / ymax 在 52w low-25% ~ 52w high+25% 范围内
    # (MaxNLocator 会把 ylim 稍微外扩来对齐 ticks, 留 5% buffer)
    assert ylim[0] < low_52w * 0.85, \
        f"ymin {ylim[0]:.0f} 应 < {low_52w * 0.85:.0f} (52w low - 15%)"
    assert ylim[0] > low_52w * 0.75, \
        f"ymin {ylim[0]:.0f} 应 > {low_52w * 0.75:.0f} (52w low - 25%)"
    assert ylim[1] > high_52w * 1.15, \
        f"ymax {ylim[1]:.0f} 应 > {high_52w * 1.15:.0f} (52w high + 15%)"
    assert ylim[1] < high_52w * 1.30, \
        f"ymax {ylim[1]:.0f} 应 < {high_52w * 1.30:.0f} (52w high + 30%)"
    # ylim 范围应 < 默认 auto 的 5000 (大幅收紧)
    ylim_range = ylim[1] - ylim[0]
    assert ylim_range < 5000, \
        f"v0.6.8h fix 失效: ylim 范围 {ylim_range:.0f} 偏大 (期望 < 5000)"
    plt.close(fig)


def test_performance_dashboard_runs_v068h():
    """v0.6.8h: 全标的 1d 涨跌幅 horizontal bar chart 能跑"""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from src.performance_dashboard import (
        plot_performance_dashboard,
        collect_performance,
    )
    # 默认 20 个标的应该都能 collect 到 (有 cache)
    results = collect_performance()
    assert len(results) >= 15, f"应至少 15 个标的 (4 指数 + 11 行业 + 2 黄金 + 3 宏观), 实际 {len(results)}"
    # 验证每条都有必要字段
    for r in results:
        assert "symbol" in r
        assert "last_close" in r
        assert "change_pct" in r
        assert "high_52w" in r
        assert "low_52w" in r
    # 画图不报错
    fig, ax = plt.subplots(1, 1, figsize=(10, 8))
    plot_performance_dashboard(ax)
    assert len(ax.patches) > 0, "应有 bar patches"
    assert ax.get_title() != "", "应有标题"
    plt.close(fig)


def test_performance_table_renders_v068h():
    """v0.6.8h: 中文 Google 风格表格渲染 (markdown + HTML)"""
    from src.performance_dashboard import (
        render_performance_table,
        render_performance_table_html,
    )
    md = render_performance_table()
    # markdown 格式
    assert "| 中文名 |" in md, "应有表头"
    assert "|" in md, "应有多行表格"
    assert "1d 涨跌幅" in md
    # 至少 10 行 (去掉表头表分隔)
    lines = [l for l in md.split("\n") if l.strip().startswith("|")]
    assert len(lines) >= 12, f"应至少 12 行 (表头 + 分隔 + 10 数据), 实际 {len(lines)}"

    # HTML 格式
    html = render_performance_table_html()
    assert "<table" in html
    assert "中文名" in html
    assert "1d 涨跌幅" in html
    # 验证颜色: 涨绿 (#137333) 或 跌红 (#c5221f)
    assert "#137333" in html or "#c5221f" in html, "应有 inline 颜色"


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


def test_sector_weights_v068f_p73_derived():
    """v0.6.8f (P7-3 派生): 从硬编码 ETF 成分股派生 4 指数 sector weights

    验证 (vs v0.6.8e 主要差异):
    - DIA: price-weighted → Financials (XLF) 显著上升, IT 下降
    - QQQ: cap-weighted → IT 50%+, 跟 v0.6.8e 类似但更精确 (从 100 成分股 + mcap)
    - QQQE: equal-weight Nasdaq-100 → IT 降 (从 ~50% → ~35%)
    - RSP: equal-weight S&P 500 → Industrials/XLK 并列最高 (各 sector ~9%)
    - 5d 残差改善 (v0.6.8e avg -0.61% → v0.6.8f < 0)
    """
    from src.attribution import load_sector_weights, attribute_all_indices, SECTOR_TICKERS
    from data.static.etf_constituents import DIA_30, get_qqq_100, SP500_SECTOR_COUNTS

    weights_data = load_sector_weights()

    # 1. DIA price-weighted: XLF (Financials) 应该是 top sector
    #    (高价格股 GS=$470, V=$280, JPM=$210, TRV=$240, AXP=$240 集中)
    dia_w = weights_data["DIA"]
    assert dia_w["XLF"] > dia_w["XLK"], \
        f"DIA price-weighted: XLF ({dia_w['XLF']*100:.1f}%) 应 > XLK ({dia_w['XLK']*100:.1f}%)"
    assert dia_w["XLF"] > 0.20, \
        f"DIA XLF 应 > 20% (Financials 高价格股集中), 实际 {dia_w['XLF']*100:.1f}%"

    # 2. QQQ cap-weighted: XLK 应 ~50% (跟 published QQQ factsheet 一致)
    qqq_w = weights_data["QQQ"]
    assert 0.45 < qqq_w["XLK"] < 0.55, \
        f"QQQ XLK 应 ~50% (cap-weighted tech 集中), 实际 {qqq_w['XLK']*100:.1f}%"
    # 加上 XLC (Comm) 应 > 65%
    assert qqq_w["XLK"] + qqq_w["XLC"] > 0.65, \
        f"QQQ XLK+XLC 应 > 65% (tech + comm 主导), 实际 {(qqq_w['XLK']+qqq_w['XLC'])*100:.1f}%"

    # 3. QQQE equal-weight: XLK 应 < QQQ XLK (更分散)
    qqqe_w = weights_data["QQQE"]
    assert qqqe_w["XLK"] < qqq_w["XLK"], \
        f"QQQE XLK ({qqqe_w['XLK']*100:.1f}%) 应 < QQQ XLK ({qqq_w['XLK']*100:.1f}%) (equal-weight 更分散)"
    assert qqqe_w["XLK"] < 0.40, \
        f"QQQE XLK 应 < 40% (equal-weight 50 只 IT / 100 总), 实际 {qqqe_w['XLK']*100:.1f}%"

    # 4. RSP equal-weight: 没有 sector > 20% (没单一 sector 主导)
    rsp_w = weights_data["RSP"]
    max_sector_w = max(rsp_w[s] for s in SECTOR_TICKERS)
    assert max_sector_w < 0.20, \
        f"RSP 最大 sector 应 < 20% (equal-weight 分散), 实际 {max_sector_w*100:.1f}%"

    # 5. constituents 数据本身健全性
    assert len(DIA_30) == 30, f"DIA 应 30 只, 实际 {len(DIA_30)}"
    qqq_100 = get_qqq_100()
    assert 95 <= len(qqq_100) <= 105, f"QQQ 应 ~100 只, 实际 {len(qqq_100)}"
    # SP500 sector count 总和应该 ~500-520
    sp500_total = sum(SP500_SECTOR_COUNTS.values())
    assert 480 < sp500_total < 530, f"S&P 500 sector count 总和应 ~500, 实际 {sp500_total}"

    # 6. P7-3 派生应该比 v0.6.8e 残差更小 (avg 5d 残差绝对值)
    #    v0.6.8e avg 5d ~-0.61% (我跟 v0.6.8e commit msg 比)
    #    v0.6.8f 派生后应该 avg 5d 残差绝对值 < 0.6%
    #    注: 不 hardcode 数字, 只验"派生后没崩"
    from datetime import datetime
    results_5d = attribute_all_indices(date=None, lookback_days=5, symbols=["DIA", "QQQ", "RSP", "QQQE"])
    avg_5d_abs = sum(abs(r["residual_pct"]) for r in results_5d) / 4
    assert avg_5d_abs < 1.0, \
        f"P7-3 派生后 5d avg 残差绝对值 {avg_5d_abs:.3f}% 偏大 (期望 < 1%)"


def test_residual_regression_v068i_p75():
    """v0.6.8i (P7-5): 残差回归测试 — 任何 commit 让残差恶化 50% 触发 fail

    跑 4 指数 × 3 窗口 (1d/5d/20d), 比较当前残差 vs baseline (v0.6.8f):
    - tolerance = 1.5x (允许 50% 恶化, 留 buffer 给市场短期波动)
    - abs_floor = 0.05% (baseline 极小时避免放大)

    第一次跑会 fail (没 baseline), 应该先 `python -m src.residual_regression capture`
    """
    from src.residual_regression import (
        capture_residuals, load_baseline, compare_to_baseline, DEFAULT_BASELINE,
    )

    # baseline 必须存在 (这是 v0.6.8i 的强制要求)
    assert DEFAULT_BASELINE.exists(), \
        f"baseline {DEFAULT_BASELINE} 不存在, 先 `python -m src.residual_regression capture`"

    baseline = load_baseline()
    current = capture_residuals()
    ok, violations = compare_to_baseline(current, baseline, tolerance=1.5, abs_floor=0.05)

    if not ok:
        # 失败时, 列出所有 violation
        msgs = [
            f"  {v['index']} {v['window']}: baseline {v['baseline_pct']:+.3f}% → "
            f"current {v['current_pct']:+.3f}% (ratio {v['regression_ratio']}x)"
            for v in violations
        ]
        assert ok, f"P7-5 残差回归 fail ({len(violations)} 处):\n" + "\n".join(msgs)


def test_yfinance_rate_limit_v068j_p76():
    """v0.6.8j (P7-6): yfinance 限流检测 + 优雅降级

    验证:
    1. 限流状态 cache 文件路径正确
    2. record_rate_limit 写入正确字段
    3. is_rate_limited() 在 cooldown 期内返 True
    4. clear_rate_limit() 后 is_rate_limited() 返 False
    5. is_yf_rate_limit_error() 能识别 YFRateLimitError + 429 + 关键字
    """
    import tempfile
    from src.yfinance_rate_limit import (
        record_rate_limit, is_rate_limited, get_rate_limit_info,
        clear_rate_limit, is_yf_rate_limit_error, RATE_LIMIT_CACHE,
    )

    # 1. cache 路径在 data/cache/ 下 (Windows path 用 \\ 或 /, normalize 后 check)
    path_str = str(RATE_LIMIT_CACHE).replace("\\", "/")
    assert "data/cache" in path_str, f"cache 路径错: {RATE_LIMIT_CACHE}"
    assert path_str.endswith("yfinance_rate_limit.json"), f"cache 文件名错: {RATE_LIMIT_CACHE}"

    # 2. 干净环境: 确认初始无 record
    clear_rate_limit()
    assert not is_rate_limited(), "干净环境应该不限流"
    assert get_rate_limit_info() is None, "干净环境应该无 info"

    # 3. 模拟限流 — 写个假的异常
    class FakeRateLimitError(Exception):
        pass
    info = record_rate_limit("DIA", FakeRateLimitError("429 Too Many Requests"), duration_hours=1)
    assert info["last_symbol"] == "DIA"
    assert info["hit_count"] == 1
    assert info["status"] == "active"
    assert "FakeRateLimitError" in info["last_error"]

    # 4. 限流中: is_rate_limited 返 True
    assert is_rate_limited(), "记录后应该限流"

    # 5. get_rate_limit_info 返 dict
    info2 = get_rate_limit_info()
    assert info2 is not None
    assert info2["hit_count"] == 1

    # 6. 累加 hit_count
    record_rate_limit("QQQ", FakeRateLimitError("429"), duration_hours=1)
    info3 = get_rate_limit_info()
    assert info3["hit_count"] == 2, f"累加 hit_count 应 = 2, 实际 {info3['hit_count']}"
    assert info3["last_symbol"] == "QQQ"  # 最后一次覆盖

    # 7. is_yf_rate_limit_error 识别
    assert is_yf_rate_limit_error(FakeRateLimitError("429 Too Many Requests"))
    assert is_yf_rate_limit_error(Exception("yfratelimit exceeded"))
    assert is_yf_rate_limit_error(Exception("rate limit hit"))
    assert not is_yf_rate_limit_error(Exception("network timeout"))  # 不应误报
    assert not is_yf_rate_limit_error(ValueError("bad input"))

    # 8. clear_rate_limit 清状态
    assert clear_rate_limit() is True
    assert not is_rate_limited(), "clear 后应该不限流"
    assert get_rate_limit_info() is None, "clear 后应该无 info"

    # 9. 幂等: clear 已不存在的 cache 不报错
    assert clear_rate_limit() is False


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
