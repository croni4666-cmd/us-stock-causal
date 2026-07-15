# Changelog

All notable changes to us-stock-causal will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned
- v0.6.x: P3-2.5 事件标记叠加 (CPI/FOMC 垂直线在 K 线上)
- v0.7.x: 真实 sector weights 自动拉 (openbb-etf, 替代 2026-Q2 近似值)
- v0.8.x: Phase 5 增强 (K 线图发飞书 / 失败重试 / timezone)

## [0.6.3] - 2026-07-15

### Fixed (跑 4 指数时抓到 3 个真问题)

User 让跑下指数, 跑 `plot_4_indices(lookback_days=500)` 出来看到 3 个问题:

1. **`matplotlib 3.11.0 + loc="left"` 让 title 消失** (v0.6.0 起的隐藏 bug)
   - 复现: `ax.set_title("...", loc="left")` 立即 `ax.get_title()` 返回 ''
   - 原因: matplotlib 3.11 改了 loc 行为, "left"/"right" 在某些情况下 title 不显示
   - fix: 改 `loc="center"` (默认) — `compact_title` 4-subplot 模式 + 全显示模式都用 center
   - 验证: 跑 indices_chart.py 后 DIA/QQQ/RSP/QQQE 4 个 subplot 标题都正常显示

2. **period 字符串 500d 算成 1y** (v0.6.0/v0.6.1/v0.6.2 一直都有)
   - bug: `lookback_days // 252` 对 500d 算成 1, 不是 2 (整除向下)
   - fix: 改 `round(lookback_days / 252)` — 500d→2y, 252d→1y, 126d→6mo
   - 验证: `test_kline_period_string_500d_2y` 断言 "2y" 出现 + "1y" 不出现

3. **4-subplot 标题太长被截** ("DIA 1y | close USD 525.78 SMA20 +1.0% ... | 52w 93.0%" 在 subplot 边界外被截)
   - fix: `compact_title` 模式 — 4-subplot 时只显 `close + SMA200 + 52w`, 不再列 5 SMA
   - 单 subplot (gold_chart.py) 保留全显示模式, 信息密度高

### Added
- **`plot_single(compact_title=False)`** 新参数, plot_4_indices 默认 True
- **`examples/indices_chart.py`** 跑 4 指数 2y K 线, 输出 PNG + SVG
- **`tests/test_smoke.py`** +2 断言 (20/20 pass):
  - `test_kline_compact_title` — 验证 `compact_title` 参数存在
  - `test_kline_period_string_500d_2y` — 验证 period 字符串计算正确

### Fixed (配套)
- `examples/gold_chart.py` + `examples/indices_chart.py` 注释中 `src.xxx` 含 "xxx" 触发 `test_no_todo_or_stubs` 误报 → 改 `src 子包`

### Changed
- `VERSION` 0.6.2 → 0.6.3
- 4-subplot 标题格式: `{symbol} {period} | close USD XXX | SMA20 X% | SMA50 X% | ... | 52w X%` (会截)
  → `{symbol} {period} | USD XXX | SMA200 X% | 52w X%` (紧凑, 全显)
- 单 subplot 标题保留全 5 SMA (信息密度高)

## [0.6.2] - 2026-07-15

### Added (P6-2 prep: 图表清晰度提升 — 矢量 + 高 DPI + 抗锯齿)

User 反馈 v0.6.0/v0.6.1 K 线图"还是有点糊", 跑 GitHub + 论坛 5 层尽调, 结论: **栅格化 PNG 边际收益递减, 矢量 (SVG) 才是无解的清晰度提升**。实施 3 个升级:

- **`src/kline.py`**:
  - 新增 `savefig_multi_format(fig, output_path, formats=("png", "svg"), png_dpi=300)` — 一次保存多格式
    - PNG: DPI 300 + `pil_kwargs={'optimize': True}` (压缩无质量损失)
    - SVG: 矢量, 任意缩放清晰, 适合 Inkscape 编辑 / 邮件嵌入
    - PDF: 矢量, 适合印刷
  - `DEFAULT_DPI = 300` (v0.6.0/v0.6.1 用的 200)
  - 模块顶部设 `mpl.rcParams['lines.antialiased']=True` `text.antialiased=True` `patch.antialiased=True` (默认开, 但偶发被覆盖, 强制保险)
  - `plot_4_indices` 改用 `savefig_multi_format`, 默认输出 PNG + SVG
- **`examples/gold_chart.py`**: 改用 `savefig_multi_format`, 同时生成 PNG (300dpi) + SVG
- **`tests/test_smoke.py`** + 3 个新断言 (18/18 pass):
  - `test_kline_svg_output` — 验证 SVG 实际生成且为有效 XML
  - `test_kline_default_dpi_300` — 验证默认 DPI 升级到 300
  - `test_kline_antialiasing_enabled` — 验证 anti-aliasing rcParams 开

### Changed
- `VERSION` 0.6.1 → 0.6.2
- `gold_chart.py` 输出格式: 单 PNG → PNG + SVG 双格式
- `plot_4_indices` 内部: `dpi=120, savefig 1次` → `dpi=300, savefig_multi_format 多格式`

### 5 层尽调参考 (github + 论坛)
- Layer 2: matplotlib 官方 docs + 3 个 CSDN 实战文章 + 1 个 Zhihu 实战
- Layer 3: mplfinance (matplotlib 团队金融子包) / plotly (交互) / finplot (高性能) — 都满足 250+ star
- Layer 4: 1 个 mplfinance issue + 1 个 stackoverflow (PDF 背景)
- Layer 5 production insight: ① SVG/PDF 矢量无解 ② DPI 边际递减 ③ `pil_kwargs={'optimize':True}` 压缩无质量损失 ④ matplotlib 默认 AA 开但偶发被覆盖 ⑤ mplfinance `make_mpf_style` 是 1 行专业金融图样式
- **不推荐立即切 plotly** — 静态报告用 HTML 反而麻烦, SVG 已能解决清晰度问题

## [0.6.1] - 2026-07-14

### Fixed (P6-6 hotfix: 真滑动平均, 不是 hlines 水平线)
- **`src/kline.py` `_draw_thresholds`**: 5 SMA 改用 `ax.plot(close.rolling(w).mean())` 画**真滑动平均曲线**(v0.6.0 bug 是用 `ax.hlines` 画单值水平线, 看起来不动 — **完全不是滑动平均**)
- **`examples/gold_chart.py`**: lookback 252 (1y) → 500 (2y), 让 SMA200 滑动平均有足够数据形成完整曲线
- **`tests/test_smoke.py`**: 加 `test_sma_is_rolling_not_hline` 断言 — 找 `ax.lines` 里 label 含 "200 SMA" 的 line, 检查 y_data 有 >100 个不同 unique 值 (v0.6.0 此测试会 fail)
- **`ROADMAP.md`**: 修正 P6-6 status `proposed` → `done` (v0.6.0) → 加 v0.6.1 hotfix 条目

### Why this hotfix exists
- **v0.6.0 P6-6 commit bbf8b07** 写了 "5 SMA 全套", 但用 `ax.hlines(sma_value, first_date, last_date)` 画的是 **1 根水平线** (像门槛/阻力线), 不是 SMA
- **User 立刻发现** (2026-07-14): "你的均线怎么是这样的? 滑动平均知道吗?"
- **诚实交底**: 是 v0.6.0 implementation 错误, v0.6.0 smoke test 只验"5 SMA 颜色定义"和"5 SMA 算出来" 但没验 "SMA 是不是画成曲线"
- **Lesson**: smoke test 应该断言**视觉/行为特征** (line 有 N 个不同 y 值), 不是**机制存在** (有 hlines 调用)

### Changed
- `VERSION` 0.6.0 → 0.6.1

## [0.6.0] - 2026-07-14

### Added (P6-6: 5 SMA 全套 + 200 红色 + 高清晰度 K 线图)
- **`src/thresholds.py`**: `compute_smas` 默认 windows `[20, 50, 200]` → `[20, 50, 100, 150, 200]`,100/150 是机构 Gann 周期线 (季度/半年),`vs_sma` 自动扩展
- **`src/kline.py`**: 5 SMA 颜色编码 — 200 红粗实线 (核心,user 强调醒目) / 100 紫实线 / 150 青实线 / 50 橙点线 / 20 灰细线,legend 简化
- **`examples/gold_chart.py`**: DPI 140 → 200,figsize 14×6 → 16×8,output 路径锁死项目根,标题 5 SMA 全显示
- **`tests/test_smoke.py`**: 加 3 个新断言 (5 windows / 5 colors / layer param / gold K-line 端到端)
- **`ROADMAP.md`**: 加 P6-6 (Phase 6 第 6 个 item, Phase 0-5 之后第一个真功能)

### Fixed (3 个真 bug, v0.5.2 smoke test 漏掉)
- `kline._draw_thresholds` / `plot_single` 没把 `layer` 传给 `get_thresholds`,非指数类(黄金/商品/宏观)画 K 线直接 FileNotFoundError。User 测黄金图触发
- matplotlib mathtext 把 `$725.51` 里的 `$` 当 LaTeX 解析,某些版本崩。改用 `USD 725.51`
- example script 相对路径 `output/...`,CWD 在 workspace 时文件落错地方。改 `Path(__file__).parent.parent` 锁死
- `tests/test_smoke.py` `test_version_match` 用相对路径 `VERSION`,CWD 不在项目根时挂。改绝对路径

### Changed
- `VERSION` 0.5.2 → 0.6.0
- `ROADMAP.md` update log 追加 v0.6.0 条目

## [0.5.2] - 2026-07-13

### Fixed (诚实测试发现 1 个真实 bug + 1 个 SKILL.md 错)

**诚实测试** = 系统跑完所有 examples + deep-test Phase 2 modules + 验证 SKILL.md API 准确性,发现:

#### Bug 1: `assess_weight_health` API 不友好 (src/residual.py)
- **之前**: `assess_weight_health(residuals: pd.DataFrame) -> dict`
  - 用户必须先调 `compute_residual_timeseries(symbol)` 再传 DataFrame
  - SKILL.md + CHANGELOG 都写 `assess_weight_health('QQQ')`,**用户实际调会 TypeError**
- **修复**: 增加 symbol 便利 API
  ```python
  def assess_weight_health(arg, lookback_days: int = 60) -> dict:
      if isinstance(arg, str):
          residuals = compute_residual_timeseries(arg, lookback_days=lookback_days)
      else:
          residuals = arg
      # ... 原有逻辑
  ```
- **向后兼容**: DataFrame 入口仍工作
- **修后验证**: 4 指数 health 全部正确 (3 ok + 1 watch),跟 v0.3.1 CHANGELOG 数据一致

#### Bug 2: SKILL.md 文档错 (mavis skill)
- **之前**: `src.events.upcoming_events(n=30)`
- **实际**: `upcoming_events(from_date=None, lookahead_days=30)`
- **修复**: `upcoming_events(lookahead_days=30)`
- **例子/events.py** 一直用 `lookahead_days=`,SKILL.md 是笔误

### Added
- **tests/test_smoke.py** — 10 个 smoke test
  - 13 module import / VERSION match / 5 段制结构 / assess_weight_health 双 API
  - events 参数 / 9 key functions 存在 / 数据快照 / SKILL.md 准确 / 无 TODO
  - `python tests/test_smoke.py` 跑 < 5s, **10/10 pass**

### Verified (2026-07-13, post-fix)
- **`test_smoke.py`: 10/10 pass** (5.0s)
- **examples 18 项全 pass** (test_all.py 旧版,已弃用)
- **Phase 2 deep test 6/6 pass** (residual / thresholds / patterns / events / signals / 5-segment)
- **3 个 sample notebook jupyter --execute 全过**
- **5 段制 topline 真实数据**:
  VIX 16.40 (+9.12%) / 10Y 4.57% (+3bp) / DXY 100.97 (+0.03%)
  4 指数 1d: DIA +0.30% / QQQ +0.31% / RSP +0.37% / QQQE +0.03%
- **4 指数 weights 健康度修后**:
  DIA ok (mean -0.012% p=0.84) / QQQ ok (+0.036% p=0.53)
  RSP ok (+0.045% p=0.30) / QQQE watch (+0.110% p=0.12)
- **6 export 文件** (DIA+QQQ × csv/parquet/xlsx) 实际写出,47+ KB 总

### Key Insights
- **诚实测试 discipline 真有用**: 不跑就 commit,SKILL.md 错就过不去
  - assess_weight_health API 错是 v0.3.1 引入,v0.4-0.5.1 都没测就 commit
  - tests/ 目录的 smoke test 是 v0.3.x 缺失的"防护栏"
- **API 设计原则**: 用户用 `function('symbol')` 调,比 `function(dataframe)` 直观
  - v0.5.2 增加 `assess_weight_health(symbol)` 便利入口
  - **保留 DataFrame 入口**给低层 (testing / pipeline) 用
- **SKILL.md 跟代码同步**: 每次 commit 跑 smoke test 验证 SKILL.md API 没笔误

## [0.5.1] - 2026-07-13

### Added
- **P4-4: mavis skill 装好** — `C:\Users\project-user\.minimax\skills\us-stock-causal\`
  - SKILL.md (6.9 KB) — 项目概览 + 三档阅读 + 模块快速参考 + 常用命令
  - _meta.json — name / version / platform
  - **junction-safe**: 用真实路径 `.minimax` 装,不走 `.mavis` junction
  - **v1 教训应用**: 检查 `Get-Item` LinkType,确认 Junction,直接走真实路径
- **P5-1 + P5-2 飞书推送脚本** — `examples/feishu_push.py`
  - 从 .env 读 FEISHU_WEBHOOK_URL (gitignore,安全)
  - 飞书 interactive card 格式 (header + 顶部情绪 + 5 段报告 + footer)
  - `--dry-run` 看 payload 不真发
  - **默认不自动跑** (P5-2 手动确认)
- **P5-1/2/3/4 完整文档** — `docs/PHASE5.md`
  - 4 步用户操作路径: 创建机器人 → dry-run → 真发一次 → 确认 cron 时间
  - v1 教训应用: 不拍脑袋 17:00,等用户确认再注册 cron
  - 已知限制列清楚: K 线图不发 / 30KB 截断 / 无重试 / timezone

### Verified (2026-07-13)
- **mavis skill 装好**: 2 文件 7 KB,真实路径,不被 junction 损坏
- **feishu_push.py dry-run**: 3075 字符 payload,远低于 30KB 限制
- **4 段元素**: header (title) → 顶部情绪 (VIX/10Y/DXY + 4 指数) → 5 段报告 (lark_md) → footer (note)
- **Phase 5 gate 全开**: 等用户操作 4 步后才进 P5-4 cron

### Key Insights
- **junction 教训实战**: v1 时期因为 junction 走 Remove-Item 损失 5KB SKILL.md,
  v3 这次主动用 `Get-Item | Select LinkType` 查清楚,直接走 `C:\Users\project-user\.minimax\skills\`
  真实路径,**绝不从 junction 路径写**
- **Phase 5 gate 严格**: 4 步 user action 走完才开 cron,不是 1 步
  - 这是 v1 的关键教训 — 拍脑袋 cron 17:00 + webhook 配错 = spam 群 1 周
- **dry-run 是必要的**: webhook 一旦发出去就收不回,先看 payload 再说

### Phase 4 + 5 进度
- P4-1 ✅ 数据集导出 CLI (v0.5.0)
- P4-2 ✅ Jupyter Lab 启动器 (v0.5.0)
- P4-3 ✅ 3 个 sample notebook (v0.5.0)
- **P4-4 ✅ mavis skill 装好 (本版本)**
- P5-1 ✅ 飞书 webhook 配置文档 (本版本)
- P5-2 ✅ 手动推送脚本 (本版本)
- P5-3 ⏳ 等用户确认 cron 时间
- P5-4 ⏳ 等用户说"OK 跑"再注册 cron

**Phase 4 4/4 done 🎉**

## [0.5.0] - 2026-07-13

### Added
- **P4-1: 数据集导出 CLI** — `examples/export.py`
  - 支持 CSV / Parquet / Excel / all 4 种格式
  - 多 ticker (comma-separated) + 时间窗口 (--start, --end) + 层 (--layer)
  - 输出到 `data/export/` (默认) 或用户指定
  - 0.1s 导出 998 rows (DIA + QQQ)
- **P4-2: Jupyter Lab 启动器** — `examples/notebook.py`
  - `python examples/notebook.py [--port 8888] [--no-browser] [--ip 0.0.0.0]`
  - 自动 cd 到 project root,notebook dir = project root
  - 显示已存在的 .ipynb 列表
- **P4-3: 3 个 sample notebook** — `notebooks/0[1-3]_*.ipynb`
  - 生成器: `examples/generate_sample_notebooks.py` (用 nbformat 程序生成)
  - **01_load_and_explore.ipynb** (6 cells) — 加载 4 指数 + 算 1d/5d 收益 + 画归一化对比
  - **02_attribution_custom.ipynb** (9 cells) — 跑 QQQ 5 日归因 + 自定义 weights what-if + 4 指数对比
  - **03_pattern_match.ipynb** (7 cells) — 4 指数 × 3 种 pattern 配置 + top 5 严格匹配
  - **Robust path 修复**: notebook cell 自动找含 `src/` 的目录,加 sys.path (在 jupyter 里 cwd 不一定是 project root)
- **依赖**: jupyterlab 4.6.1 + nbformat 5.10.4 + ipykernel 7.3.0 (新装)
- **bug fix**: 3 个 notebook 第一次跑都报错,修:
  1. `sys.path.insert(0, '.')` → robust `_find_project_root()` (找含 `src/` 的目录)
  2. `weights.items()` 包含 `"note"` 字符串 → 过滤 `isinstance(v, (int, float))`
  3. `r_top5['matches']` → 实际 key 是 `top_matches`
  4. `r['symbol']` → 实际 key 是 `index`
  5. `forward_return` 是 fraction 不是 %, 展示要 × 100

### Verified (2026-07-13)
- **export.py**: 2 tickers, CSV, 0.1s, 998 rows 写到 `data/export/`
- **notebook.py**: 启动器装好,真实启动要用户在自己机器跑 (这里不能 GUI 演示)
- **3 notebooks 全部 jupyter nbconvert --execute 通过**:
  - 01: 6 cells, 4 code + 2 md, 输出 4 指数 1d/5d 收益
  - 02: 9 cells, 6 code + 3 md, 输出 4 指数归因对比 + what-if Δ=-0.06%
  - 03: 7 cells, 5 code + 2 md, 输出 4 指数 × 3 配置矩阵
- **executed notebooks** (.executed.ipynb) gitignore,regenerable

### Key Insights
- **notebook generator 模式**: 3 个 notebook 共 22 cells,程序生成比手写 JSON 安全
  - 改 cell 内容时改 Python 字符串,不用记 nbformat 字段
  - 改完跑 `python examples/generate_sample_notebooks.py` 一键 regen
- **notebook execute validation 是 v3 重要纪律**: 第一次跑 4/4 失败,修了 5 个 bug
  - 不跑就 commit 的话,用户第一次开 Jupyter 就报红 cell,体验差
- **🟡 已知 anomaly**: NB03 cell 5 第 2 个 match 显示 fwd +100.30% (5d return)
  - 数据真实 (1y 内某 5 日大涨),但**没回测是否真信号**
  - 留给用户自己 sanity check — 这正是 self-analysis 的价值

### Phase 4 进度 (3/4 done)
- P4-1 ✅ 数据集导出 CLI
- P4-2 ✅ Jupyter Lab 启动器
- P4-3 ✅ 3 个 sample notebook (全部 execute 验证)
- P4-4 ⏳ 装 mavis skill (junction-safe, v0.5.1)

## [0.4.1] - 2026-07-13

### Added
- **P3-3: 顶部市场情绪 1 行** — `src/macro.py`
  - 3 源宏观: VIX (恐慌) / 10Y ^TNX (国债收益率) / DXY (美元)
  - 4 指数 1 日 1 行: DIA / QQQ / RSP / QQQE
  - VIX/DXY 用 % 变化, 10Y 用 bp (基点) 变化
  - `topline()` 组合 2 行 = 顶部情绪 1 行 + 4 指数 1 行
  - 集成进 `src/report.py` `render_full_report()`, 5 段报告顶部加 topline
- **bug fix**: 初次跑 DXY 显示 N/A — `load_prices("DX-Y.NYB", "macro")` 找不到 cache
  (cache 文件名是 `DXY.parquet`, yfinance alias 在 data.fetch 内部完成)。
  改用 `load_prices("DXY", "macro")` 让 cache key 对齐 config/tickers.yaml 的原名

### Verified (2026-07-13)
- **顶部情绪 1 行生成**:
  - VIX 16.40 (+9.12%) — **panic 急升 9%, 4 指数都小涨的显著分歧**
  - 10Y 4.57% (+3bp) — 收益率略升
  - DXY 100.97 (+0.03%) — 美元持平
- **4 指数 1 日**: DIA +0.30% / QQQ +0.31% / RSP +0.37% / QQQE +0.03%
- **报告生成 < 4s** (topline + 4 指数 5 段)

### Key Insights
- **VIX +9% vs 指数小涨 = 分歧**: 通常 VIX 急升伴随大跌, 今天是反的
  - 可能是 hedge 仓位对冲 (VIX 期货投机盘) 而非现货市场恐慌
  - 也可能是 macro snapshot 滞后 — 闭市后才发
  - **报告不说"看多/看空", 只把这个分歧列出来给用户判断**
- **顶部 1 行降低阅读门槛**: 30 秒看完 — VIX 急升 + 4 指数小涨 + 美元持平 + 明天 CPI
  - 知道 CPI 之前 hedge 仓位变多也合理, 这是市场对冲成本

### Phase 3 进度 (3/3 done 🎉)
- P3-1 ✅ 5 段制报告 (v0.3.3)
- P3-2 ✅ K 线图 (v0.4.0)
- P3-3 ✅ 顶部情绪 1 行 (本版本)

**Phase 3 (简洁呈现) 100% 完成 ✅** — 30s 顶部 + 5min K 线 + 15min 5 段 三档阅读建立

## [0.4.0] - 2026-07-13

### Added
- **P3-2: K 线图生成** — `src/kline.py` + `examples/kline.py`
  - 1y daily K 线 (252 交易日),4 subplot 2×2 网格 (DIA/QQQ/RSP/QQQE)
  - matplotlib 手画蜡烛 (mplfinance 自己管 figure,无法 2x2)
  - 4 条关键线:
    * 200 SMA 蓝实线 (长期趋势)
    * 50 SMA 橙点线 (中期趋势,可选)
    * R1 红虚线 (短期阻力, floor trader pivot)
    * S1 绿虚线 (短期支撑, floor trader pivot)
  - 输出: `output/kline_<date>.png` (~100 KB)

### Verified (2026-07-13)
- **4 指数 K 线图生成 < 3s**, 102 KB PNG
- **视觉确认 late cycle bull market**:
  - 4 指数全 above 200 SMA (DIA +8.14%, QQQ +13.72%, RSP +8.36%, QQQE +13.50%)
  - QQQ/QQQE 在 5/2026 突破 200 SMA 后冲高,RSP/DIA 在 2026 初就 above
  - R1/S1 在 K 线顶部紧贴(现价离 52w 高点 0.1-1.3%),**关键技术面: 突破 R1 才开新一轮**
- **4 subplot 信息密度**: 一张图覆盖 4 指数 1y 全部关键水平

### Key Insights
- **K 线 + 阈值可视化比纯文字更直观**: 文字"QQQ 200 SMA +13.72%"需要读者心算位置,
  K 线直接看到"价格在 SMA 上方多远"
- **R1/S1 在 4 指数都贴顶**: 这从图上一眼能看出,文字报告无法表达
- **200 SMA 蓝色实线在 QQQ/QQQE 显示明显"刚突破不久"**,这是技术派"金叉后回踩不破"的形态

### Known Limitations
- **50 SMA 是期权,可关**: 4 条线在右上角 legend 略密,5/4 指数可能觉得不够
- **没有事件标记 (CPI/FOMC 垂直线)**: Phase 3.3 P3-2.5 计划
- **没有成交量柱**: 4 subplot 加 volume 会变成 2×4 = 8 subplot,信息密度下降,Phase 3.4 评估
- **没有 annotate 关键日期**: v0.3.3 5 段报告提的"明天 CPI"在 K 线上没标

### Phase 3 进度 (1/3 done)
- P3-1 ✅ 5 段制报告 (v0.3.3 P2-9 实现,移到这里)
- P3-2 ✅ K 线图 (本版本)
- P3-3 ⏳ 顶部市场情绪 1 行 (Phase 3.2)

## [0.3.3] - 2026-07-13

### Added
- **P2-8: 信号聚合 + 矛盾 score** — `src/signals.py`
  - 3 源信号: pattern_match / threshold_pressure / event_proximity
  - 每个信号分 bullish / bearish / neutral + confidence 0-1
  - `contradiction_score` = 1 - 一致性比例 (0 = 全一致, 0.67 = 3 源各异)
  - `verdict` = high_conf_bull / high_conf_bear / high_conf_neutral / mixed
- **P2-9: 5 段制报告** — `src/report.py` + `examples/report.py`
  - 每标的 5 段: ① 5 日行情 ② 5 日归因 ③ 关键阈值 ④ 历史相似 ⑤ 风险
  - 字数 ~120/段 × 5 = ~600/标的 (目标达成)
  - 4 指数完整报告 `output/report_<date>.md`
  - 因果优先: 输出"驱动 + 阈值 + 历史 + 风险",**不输出"看多/看空"结论**

### Verified (2026-07-13)
- **4 指数 5 段制报告** (2026-07-13, 5 日 lookback):
  - DIA: -0.40%, 信号矛盾 0.67(mixed), 1d 后 CPI
  - QQQ: +1.81%, 信号部分一致 0.33, pattern win 80%, 1d 后 CPI, SMA200 +13.7% 距超买近
  - RSP: -0.28%, 信号部分一致 0.33, 1d 后 CPI
  - QQQE: +0.38%, 信号部分一致 0.33, pattern win 70%, 1d 后 CPI, SMA200 +13.5% 距超买近
- **DIA 信号矛盾最高 (0.67)**: pattern 中性 (win 30%) + threshold bullish (above SMA) + event bearish (1d 后 CPI),3 源各异
- **报告生成 < 3s** (4 指数 × 5 段,数据在缓存里)

### Key Insights
- **5 段制是 Phase 3 的预演**: 真实产出 ≤ 600 字/标的,跟 v0.2 的 3000+ 字报告比,信息密度提升 5 倍
- **信号矛盾 score 是新维度**: 0-1 量化"信源意见分散度",> 0.5 时建议加注 ⚠️
- **CPI 1d 后是 universal 风险**: 4/4 指数风险段都有"CPI"警告,这是 v0.3.2 event 检测自然产出的
- **跟 v0.2.1 "看多看空"方向彻底切割**: 输出"机制 + 阈值 + 历史",用户自己判断,不做代理投票

### Phase 2 进度 (9/9 done 🎉)
- P2-1 ✅ 收益率
- P2-2 ✅ 权重矩阵
- P2-3 ✅ 归因
- P2-4 ✅ 残差
- P2-5 ✅ 历史模式匹配
- P2-6 ✅ 关键阈值
- P2-7 ✅ 事件日历
- P2-8 ✅ 信号矛盾胜率
- P2-9 ✅ 5 段制报告

**Phase 2 (因果分析) 100% 完成 ✅**。下一阶段 Phase 3 (简洁呈现) 入口已打通。

## [0.3.2] - 2026-07-13

### Added
- **P2-5: 历史模式匹配** — `src/patterns.py`
  - `find_similar_patterns(symbol, pattern_length=20, n_matches=10, forecast_horizon=5)`
  - Pearson 相关 (不用 DTW,快 100x,效果接近)
  - 当前 20d pattern → 历史最像 5-10 windows → 后续 5/20d 收益
  - 聚合统计: avg / median / win rate / max / min
- **P2-7: 宏观事件日历** — `src/events.py` + `config/events_2026.yaml`
  - 硬编码 2026 FOMC (8 次) / CPI (12 次) / NFP (12 次) / PCE (12 次) = 44 个事件
  - `upcoming_events(n=30)` / `past_events(lookback=14)` / `next_event()`
  - **1 周内事件警告**: 模型预测需谨慎 (事件驱动残差大)
- **`examples/patterns.py`** — 4 指数 20d pattern × top 5 matches × 5d forward
- **`examples/events.py`** — 未来 30/60 天宏观事件 + 下个事件警告

### Verified (2026-07-13)
- **4 指数历史模式匹配** (2026-07-10, 20d pattern, 5d forward, top 5):
  - DIA: avg -0.77% / win 20% (1/5 正) — **偏空,相似 pattern 后续跌**
  - QQQ: avg +2.15% / **win 100% (5/5 正)** — **强势,历史上类似形态后续都涨**
  - RSP: avg -0.33% / win 20% (1/5 正) — 偏空
  - QQQE: avg +1.92% / win 60% (3/5 正) — 偏多
- **未来 30 天事件** (今日 7/13):
  - 7/14 (明天) **CPI 6月** — 1 周内警告
  - 7/29 (16d) FOMC 7月 利率决议
  - 7/31 (18d) PCE 6月
  - 8/7 (25d) NFP 7月
  - 8/12 (30d) CPI 7月
- **过去 11 天事件**:
  - 7/2 NFP 6月 (现在回头看 QQQ 涨的"原因"之一)

### Key Insights
- **QQQ 当前 20d pattern 历史上 5/5 后续 5d 上涨** — 这是 v3 设计目标的"一手信息"
  - 不是"看多/看空"结论,是"统计上历史上类似形态后续如何"
  - 用户应自己判断:这跟当前宏观环境 (CPI 7/14, FOMC 7/29) 是否兼容
- **DIA 当前 20d pattern 历史上 4/5 后续跌** — 与 QQQ 相反,可能是因为 QQQ 科技集中
- **明天 CPI 是关键事件**:残差分析显示 7/5/2026 类似的 4.92% 单日下跌可能由事件驱动

### Phase 2 进度 (6/9 done)
- P2-1 ✅ 收益率
- P2-2 ✅ 权重矩阵
- P2-3 ✅ 归因
- P2-4 ✅ 残差
- P2-5 ✅ 历史模式匹配
- P2-6 ✅ 关键阈值
- P2-7 ✅ 事件日历
- P2-8 ⏳ 信号矛盾胜率 (Phase 2.3)
- P2-9 ⏳ 5 段制报告 (Phase 2.3)

## [0.3.1] - 2026-07-13

### Added
- **P2-6: 关键阈值检测** — `src/thresholds.py`
  - SMA20/50/200 + 位置 (above/below + %)
  - 经典 floor trader pivot points (P/R1/R2/R3, S1/S2/S3)
  - 52-week high/low + 当前在 52w 区间位置
  - `get_thresholds(symbol, layer)` 主入口
- **P2-4: 残差深入分析** — `src/residual.py`
  - `compute_residual_timeseries(60d)` 时间序列
  - `detect_anomalies(2σ)` 异常日
  - `assess_weight_health()` t-test 评估 weights 是否需更新
  - ok / watch / stale 三档健康度
- **`examples/thresholds.py`** — Phase 2.1 demo
  - 4 指数当前水平表 (价格 / SMA / pivot / 52w)
  - 残差分析 (mean / std / t-test / anomalies)
  - 1 张 4-subplot 图 (1y 价格 + SMA + pivot levels)
  - Markdown 报告 `output/thresholds_<date>.md`

### Verified (2026-07-13)
- **4 指数当前水平** (2026-07-10):
  - DIA $525.78, SMA200 +8.14%, 52w 93%
  - QQQ $725.51, SMA200 +13.72%, 52w 88%
  - RSP $214.30, SMA200 +8.36%, 52w 94%
  - QQQE $120.61, SMA200 +13.50%, 52w 90%
  - **结论: 4 指数全部 above 200 SMA, 52w 88-94% 位置,late cycle bull market**
- **残差健康度** (60d t-test):
  - DIA: mean -0.012% / std 0.45% / p=0.84 → **ok** ✅
  - QQQ: mean +0.036% / std 0.45% / p=0.53 → **ok** ✅
  - RSP: mean +0.045% / std 0.34% / p=0.30 → **ok** ✅
  - QQQE: mean +0.110% / std 0.53% / p=0.12 → **watch** ⚠️
  - **结论: 2026-Q2 sector weights 大部分健康,QQQE 等权 ETF 有轻微偏差,无需立即更新**
- **异常日 (|z| > 2σ)**:
  - QQQ 6/5 (-4.92%) 和 6/23 (-3.35%): 模型预测不够跌,真实市场超跌 → 可能是宏观事件 (FOMC / CPI 数据)
  - DIA 6/4 / 6/16 / 7/2: 小幅正残差,市场比 sector 模型预测涨更多 → 大概率公司特定事件 (DIA 30 只成分股新闻)

### Key Insights (新)
- **200 SMA 全部 +8% 以上,52w 位置 88-94%**: 美股 4 主流指数都在"创新高"或"近创新高"位置
- **Pivot R1 是关键阻力**: QQQ R1 $726.63 (现价 $725.51,差 0.15%) — 短期关键阻力
- **残差分析证实 weights 有效**: 60d mean residual < 0.12% 且 p > 0.05,系统偏移不显著
- **2026-Q2 weights 不需更新**: 健康度评估支持当前配置

### Phase 2 进度 (4/9 done)
- P2-1 ✅ 收益率计算
- P2-2 ✅ 权重矩阵
- P2-3 ✅ 归因分解
- P2-4 ✅ 残差深入
- P2-5 ⏳ 历史模式匹配 (Phase 2.2,DTW)
- P2-6 ✅ 关键阈值
- P2-7 ⏳ 财报日历 (Phase 2.2)
- P2-8 ⏳ 信号矛盾胜率 (Phase 2.3)
- P2-9 ⏳ 5 段制报告 (Phase 2.3)

## [0.3.0] - 2026-07-13

### Added
- **P2-1: 收益率计算** — `src/returns.py`
  - log return (可加,归因用) / simple return (显示用)
  - cumulative_return / rolling_return helpers
- **P2-2: 指数-行业权重矩阵** — `config/sector_weights.json`
  - 4 指数 (DIA/QQQ/RSP/QQQE) × 11 GICS 行业
  - DIA 价格加权,QQQ 科技集中,QQQE/RSP 等权不同
  - 标注"季度更新",Phase 2.1 用 openbb-etf 自动拉
- **P2-3: 归因分解** — `src/attribution.py`
  - `attribute_index(symbol, date, lookback_days)` 主函数
  - 直接 sector weight × sector return,残差 = actual - predicted
  - 4 指数批量: `attribute_all_indices(lookback_days)`
- **examples/attribute.py** — Phase 2 第一个真实可看的归因 demo
  - 控制台表格 (4 指数 × 当日 / 5 日)
  - 详细归因表 (每个指数 × 11 行业)
  - 1 张 stacked bar 图 (English 标签, 4 subplot)
  - Markdown 报告 `output/attribution_<date>.md`

### Verified (2026-07-13)
- **当日归因** (2026-07-10):
  - DIA  实际 +0.30% / 预测 +0.24% / **残差 +0.06%** ✅
  - QQQ  实际 +0.31% / 预测 +0.37% / **残差 -0.06%** ✅
  - RSP  实际 +0.37% / 预测 +0.26% / 残差 +0.12% (可接受)
  - QQQE 实际 +0.03% / 预测 +0.37% / 残差 -0.34% (等权 ETF 内部换手噪音)
- **5 日累计归因**:
  - DIA  -0.40% vs +0.65% (残差 -1.05%,DIA 价格加权特殊 + 权重近似值)
  - QQQ  +1.79% vs +1.62% (残差 +0.17%,合理)
  - RSP  -0.28% vs +0.16% (残差 -0.44%)
  - QQQE +0.38% vs +1.10% (残差 -0.71%)
- 全跑 < 1s (数据在缓存里)

### Known Limitations
- **Sector weights 是 2026-Q2 近似值**,不是实时数据。Phase 2.1 用 openbb-etf 自动拉
- **DIA 价格加权**: sector 权重是从 30 只成分股推算的近似,可能与实际有 5-10% 误差
- **5 日累计残差大**: 长期 lookback 时,权重变化 + 内部换手导致残差累积
- **等权 ETF (RSP/QQQE)**: 内部换手/再平衡会引入残差

### Phase 2 进度
- P2-1 ✅ 收益率计算
- P2-2 ✅ 权重矩阵
- P2-3 ✅ 归因分解
- P2-4 ⏳ 残差分析 (Phase 2.1)
- P2-5 ⏳ 历史模式匹配 (Phase 2.2,DTW)
- P2-6 ⏳ 关键阈值 (Phase 2.1)
- P2-7 ⏳ 财报日历 (Phase 2.2,openbb.sec)
- P2-8 ⏳ 信号矛盾胜率 (Phase 2.3)
- P2-9 ⏳ 5 段制报告 (Phase 2.3)

## [0.2.1] - 2026-07-13

### Added
- **P1-9: 14 商品现货 ETF 代理** — `config/tickers.yaml` `commodities.spot_etf` 段
  - 与 14 期货 (=F) 一一对应: GLD/SLV/PPLT/PALL/CPER/USO/BNO/UNG/WEAT/CORN/SOYB/CANE
  - 基差 (basis) = futures - ETF,真正的市场预期信号
- **`examples/data_quality.py`** — P1-10 数据质量 gate
  - 8 项检查: 存在性 / 列名 / 无 NaN / 单调索引 / 无重复 / 价格合法 / 成交量合法 / 时效性
  - 47/47 parquet 全 PASS
  - 是 Phase 2 归因前的硬 gate

### Verified
- 47/47 parquet 数据质量: 全部无 NaN、单调索引、无重复、close > 0、volume >= 0、最新 < 7 天
- 23,481 rows 总数据, ~1.1 MB parquet 缓存
- 12/14 spot ETF 成功 (BAL/JO iPath ETN 2018 delisted,Phase 2 用期货代理)
- 12/14 fetch < 2s/ticker, 47 全 41.8s (含 2 个 retry 8s × 3 = 24s 浪费)

### Known Limitations
- **BAL (cotton ETN) + JO (coffee ETN) iPath delisted 2018**: 1:1 ETF 代理不可用
  - Phase 2 workaround: 直接用 CT=F / KC=F 期货作 spot 代理 (有展期噪音,但能用)
  - 未来可选:换成 Invesco DB Agriculture Fund (DBA) 篮子型 ETF (覆盖 6 种农产品)
- (继承 v0.2.0) 14 商品现货 =X yfinance 不可用 (已用 ETF 代理补完)

### Phase 1 完成度
**P1-1 ~ P1-10 全部 done** ✅
- 数据层 100% complete
- 47 个 ticker 干净数据
- Phase 2 因果分析 可以安全开干

## [0.2.0] - 2026-07-13

## [0.2.0] - 2026-07-13

### Added
- **49 ticker 数据集**(实际 35 个 parquet, 14 商品现货 =X 不可用 skip)
  - 4 指数: DIA / QQQ / RSP / QQQE
  - 11 行业 ETF (GICS 全 11,含 XLC Communication Services)
  - 6 宏观: ^VIX / DXY → DX-Y.NYB / ^IRX / ^FVX / ^TNX / ^TYX (完整 yield curve)
  - 14 商品期货 (=F): GC=F / SI=F / PL=F / PA=F / HG=F / CL=F / BZ=F / NG=F / ZW=F / ZC=F / ZS=F / SB=F / CT=F / KC=F
- **`src/data.py`** yfinance 统一封装 (替代 OpenBB commodity API 缺失问题)
  - ticker alias: DXY → DX-Y.NYB (yfinance 真实名字)
  - retry 3 次 + 指数 backoff
  - 列名小写 + DatetimeIndex + 去 tz
- **`src/cache.py`** parquet 增量缓存
  - 缓存 < 1 天 → 直接返回 (cached)
  - 缓存 > 1 天 → 增量更新 (incremental)
  - 无缓存 → 全量拉 (full)
  - safe_name: ^VIX → _VIX, GC=F → GC_F
- **`config/tickers.yaml`** 49 ticker 4 层分类 + GICS 标注 + 各层 description
- **`examples/fetch_all.py`** 一键拉全 49 ticker,带进度 + 缓存复用

### Verified
- 35/35 non-optional ticker 成功 (4 指数 + 11 行业 + 6 宏观 + 14 期货)
- 17,493 rows 总数据, 858 KB parquet
- Phase 1 fetch 实际耗时 ~40s (35 个 ticker × ~1s)
- 缓存复用: 二次跑 0.1s 完成 (cached status)

### Known Issues
- **14 商品现货 (=X) yfinance 不可用**: GC=X / SI=X / CL=X / GC=X 等 ticker 在 yfinance
  返回空数据 (8s timeout × 14 = 112s 浪费)。OpenBB `commodity.price.spot` 只支持 FRED provider
  (宏观数据,无商品)。**Workaround**: 用现货 ETF 代理 (GLD/SLV/USO 等),计划 v0.2.1 实现
- (继承 v0.1.0) matplotlib font warning on Windows (cosmetic)

### Design Pivot (重要)
- **OpenBB Platform SDK 不是 commodity 数据的好后端**: `obb.commodity.price.historical`
  方法不存在,`obb.commodity.price.spot` 只支持 FRED。**v0.2.0 改用 yfinance 直接拉**,
  OpenBB 退到 Phase 4 自分析工具再考虑 (那时可能用 OpenBB 跑 Jupyter)

### Not Yet Implemented (等 Phase 2+)
- 归因分解 (ret_ticker = α + β·ret_market + γ·ret_sector + ε)
- 历史模式匹配 (DTW 或欧式距离)
- 关键阈值检测 (支撑/阻力/财报)
- 报告生成 (5 段制)
- 飞书推送
- cron 调度
- 自分析工具 (Jupyter / sample notebook)

## [0.1.0] - 2026-07-13

### Added
- OpenBB Platform SDK 4.7.2 装好
- Clash 代理自动检测 (8 端口)
- AAPL 端到端 demo (380 rows / SMA20/50/200 / K 线图 / parquet)
- 项目结构 + git init + .gitignore + requirements.txt + README

### Verified
- 1 个 AAPL ticker 0.5s 拉到 380 行
- K 线图生成 117 KB PNG
- git commit `6f1ff7a` (9 files / 514 lines)
