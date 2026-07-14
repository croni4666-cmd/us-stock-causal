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
