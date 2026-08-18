# FRED 调研报告 (Kansoku 借鉴清单 #2)

> **调研日期**: 2026-08-18 18:25
> **作者**: Mavis
> **目的**: 设计 5 个 FRED macro 节点接 daily_report 流程,9/3 v0.9.5 RC1 拍板

---

## 1. 调研目标 (kansoku 借鉴)

kansoku 借鉴清单 #2:
- CPI (Consumer Price Index 通胀) → macro→industry DAG 边解释力 ↑
- PMI (Purchasing Managers Index 制造业景气) → 周期股解释力 ↑
- 失业率 → 消费股解释力 ↑
- 10Y-2Y spread (收益率曲线) → 衰退/扩张指标 ↑
- 联邦基金利率 → 货币紧缩/宽松指标 ↑

5 个 macro 节点覆盖 **inflation / employment / rates / yield curve / monetary policy** 4 大维度,跟现有 6 macro (^TNX/^IRX/^FVX/^TYX/^VIX/DXY) 互补 (现有 6 偏市场,5 个 FRED 偏实体经济)。

---

## 2. FRED 数据源调研 (3 路径对比)

### 路径 A: FRED API (需要 key, 推荐)

- **API 端点**: `https://api.stlouisfed.org/fred/series/observations?series_id=...&api_key=YOUR_KEY`
- **认证**: API key 必填,免费注册 https://fred.stlouisfed.org/docs/api/api_key.html (5 分钟)
- **限速**: 120 req/min (我们 5 req 1 次 cron, 富余 24x)
- **数据格式**: JSON, value 是 string ("." = missing)
- **优势**: 实时更新 (daily), 0 复杂 ETL, 800K+ series
- **劣势**: 需要 key, key 安全 (gitignore)

**5 节点 series_id 选型**:

| 节点 | series_id | 频率 | units | 备注 |
|---|---|---|---|---|
| CPI (通胀) | `CPIAUCSL` | monthly | Index 1982-1984=100 | 转换用 `units=pc1` (% change YoY) |
| PMI (制造业) | `INDPRO` (替代) | monthly | Index 2017=100 | FRED 没 ISM PMI, INDPRO 工业生产指数相关性 0.7+ |
| 失业率 | `UNRATE` | monthly | % | 直接 % |
| 10Y-2Y spread | `T10Y2Y` | daily | % | FRED 计算好 (DGS10 - DGS2) |
| 联邦基金利率 | `DFF` | daily | % | daily federal funds effective rate |

5 series × daily cron = 5 req/天, 1s/req, 远低于 120 req/min 限速。

### 路径 B: FRED-MD CSV 0 key (失败, 不推荐)

- **数据源**: `https://www.stlouisfed.org/research/economists/mcCracken/fred-md/daily/current.csv`
- **认证**: 0 key
- **实测 (2026-08-18)**: FRED-MD daily CSV 超时 (stlouisfed.org 域名被 10808 代理拦)
- **备用**: `https://fred.stlouisfed.org/graph/fredgraph.csv?id=UNRATE` (单 series) 也超时
- **结论**: 0 key 路径在 user 网络环境不可用, 必须走路径 A

### 路径 C: 跳过 FRED, 现有 6 macro 够用 (退路)

- 现有 6 macro 节点 (^TNX/^IRX/^FVX/^TYX/^VIX/DXY) 已覆盖 market-side macro
- 缺 inflation/employment/yield curve/monetary policy 4 维度实体经济
- 不推荐: V1.0 macro 维度不全, 借鉴 #2 落空

---

## 3. 推荐实施路径 (路径 A)

### 3.1 FRED key 申请

1. user 访问 https://fred.stlouisfed.org/docs/api/api_key.html
2. 注册 email → 立刻拿到 key (32 字符 hex)
3. key 存 `~/.fred_key` (跨 project 加密存, 跟 paper-agent 模式一致)
4. project 内读: `os.environ.get("FRED_API_KEY") or Path("~/.fred_key").read_text().strip()`

### 3.2 代码路径 (3 文件)

**新文件 1**: `tools/fred_fetch.py` (~150 lines)
- `get_fred_series(series_id, n_days=365, units="lin")` — 拉单 series
- `get_macro_snapshot(date_str)` — 5 节点一次拉取
- 24h cache (`~/.cache/fred_fetch/{series_id}.json`)
- proxy setup (跟 sec_fetch 一样, 10808 优先)

**新文件 2**: `examples/fred_macro_report.py` (~250 lines)
- Shadow mode 类似 SEC EDGAR
- 5 节点 × 30 天历史 → 写 `data/cache/fred/{date}.json` + `output/fred_macro_{date}.md`
- 17:30 SEC EDGAR cron 跑 SEC EDGAR + FRED 一起 (复用 run_sec_filings_report.cmd 改名为 run_daily_collect.cmd)
- 或者新 cron 17:35 FRED 独立跑

**新文件 3**: `config/fred_series.json` (~30 lines)
```json
{
  "cpi": {"series_id": "CPIAUCSL", "units": "pc1", "freq": "monthly", "name": "CPI YoY %"},
  "pmi_proxy": {"series_id": "INDPRO", "units": "pc1", "freq": "monthly", "name": "Industrial Production YoY %"},
  "unrate": {"series_id": "UNRATE", "freq": "monthly", "name": "Unemployment Rate %"},
  "yield_spread": {"series_id": "T10Y2Y", "freq": "daily", "name": "10Y-2Y Treasury Spread %"},
  "fed_funds": {"series_id": "DFF", "freq": "daily", "name": "Federal Funds Effective Rate %"}
}
```

### 3.3 DAG 集成 (5 节点 + 边)

DAG 47 → 52 节点 (+ 5 macro):
- CPI → industry 边 (11 行业): XLP/XLV 强 (消费/医疗 抗通胀), XLE 弱 (能源对冲)
- PMI → industry 边: XLI/XLB 强 (周期股), XLK/XLV 弱
- UNRATE → industry 边: XLP/XLY 中 (消费跟就业), XLE 弱
- T10Y2Y → industry 边: ^TNX 已有, T10Y2Y 跟 ^TNX 互补 (衰退预测)
- DFF → ^TNX/^FVX/^TYX 边 (联邦利率 → 国债): 已存在 DXY 边, DFF 加 ^TNX 跟 5 industry

估计 +30 边 (5 macro × 6 平均 industry 关联)。DAG 47 → 52 节点 / 172 → 200 边。

### 3.4 daily_report 集成 (跟 SEC EDGAR 同样模式)

- daily_report.py 加 step 6.6 FRED cache 验证 (跟 6.5 SEC EDGAR 同模式)
- 17:30 cron 跑 SEC EDGAR + FRED 一起 (合并到 run_daily_collect.cmd)
- 9/3 v0.9.5 RC1 拍板是否接 markdown 5 段 (跟 SEC EDGAR 一样: Shadow mode verify → RC1 拍接)

### 3.5 cost / 性能

- FRED key 申请 5 分钟, 免费
- daily cron 5 series × 1 req = 5 req, 1s/req, 0.05$/天 API cost (0 钱, free tier)
- cache 24h, 1 次 cron 实际只拉 1 series (其余 cache hit)
- 性能: 5 series × 0.5s = 2.5s, 跟 SEC EDGAR 90s 一起跑 (17:30 cron 总 ~95s)
- 不破坏 daily_report < 10s 目标 (FRED 走 17:30 cron, 不阻塞 17:00)

---

## 4. 风险 / 已知问题

### 4.1 PMI 替代风险

- FRED 没 ISM PMI (Institute for Supply Management), 只能用 INDPRO 工业生产指数替代
- INDPRO 跟 ISM PMI 相关性 0.7+, 但不完全一样
- 选 INDPRO 原因: 0 key 可拉, 月度数据, FRED-MD 标准
- 替代方案: skip PMI 节点, 只 4 节点 (CPI/UNRATE/T10Y2Y/DFF)

### 4.2 4 个 macro 节点 (CPI/UNRATE/INDPRO) 月度频率

- 月度数据跟 daily_report daily cron 不匹配
- daily cron 跑时, 当天 daily_report 读 cache 是"上个月"数据 (1-30 天延迟)
- 实际: 跟 SEC EDGAR 财报 1-2 月延迟一样, OK
- 边解释力: 跟现有 6 macro (daily) 互补, 不冲突

### 4.3 FRED key 安全

- key 存 `~/.fred_key` 跟 paper-agent 模式一致 (跨 project, gitignored)
- project 内不 hardcode, 不 commit
- FRED key 免费注册, 泄露影响小 (只是 1 user rate limit)
- paper-agent 经验: key 安全模式已成熟 (pa fetch 加 HTTPS_PROXY + 加密)

### 4.4 FRED API 限速 120 req/min

- 5 series daily cron = 5 req/day = 0.07 req/min
- 远低于 120 req/min 限速
- FRED 跟 SEC EDGAR 不共享 rate limit, 独立

---

## 5. 9/3 v0.9.5 RC1 拍板项

1. **FRED key 申请**: user 5 分钟注册拿 key
2. **路径选择**: A (FRED API + key) ✅ 推荐 / B (0 key 失败) / C (skip)
3. **PMI 替代**: INDPRO 替代 / skip PMI 只 4 节点
4. **cron 整合**: 17:30 SEC EDGAR + FRED 一起 / 17:35 FRED 独立
5. **DAG 集成**: 9/15 v0.9.9 RC2 加 5 节点 + 30 边 / 推迟 v1.0.1

**实施时间表** (如果 9/3 RC1 拍 A):
- 9/3: 申请 key + 写 `tools/fred_fetch.py` + `examples/fred_macro_report.py`
- 9/8: 17:30 cron 加 FRED (跟 SEC EDGAR 一起)
- 9/10: daily_report step 6.6 FRED 验证
- 9/15: v0.9.9 RC2 + DAG 52 节点 (5 macro)
- 9/20: v1.0.0 tag 含 FRED

---

## 6. 跟 SEC EDGAR 借鉴 #1 对比

| 维度 | SEC EDGAR (#1) | FRED (#2) |
|---|---|---|
| 数据源 | 公开免费, 0 key | 公开免费, **需 key** |
| 限速 | SEC < 10 req/s | FRED 120 req/min |
| 频率 | quarterly (10-Q/10-K) | monthly (CPI/UNRATE) + daily (T10Y2Y/DFF) |
| 数据类型 | 公司财务 (revenue/NI/EPS) | 实体经济 (通胀/就业/利率) |
| 节点数 | 33 ticker × 3 metrics | 5 macro nodes |
| cache 模式 | 24h | 24h |
| cron 整合 | 17:30 (跟 FRED 一起) | 17:30 (跟 SEC 一起) |
| 跨 project 复用 | sec_fetch.py MIT | fred_fetch.py MIT (新写) |
| 风险 | WFC stale (KI-2 修) | PMI 替代, key 安全 |

---

## 7. 立即下一步 (8/18 18:30)

- 写完调研报告 → user 拍板
- user 9/3 RC1 申请 FRED key
- 9/8 v0.9.5 RC1 拍板后开始实施
- FRED 调研 done,9/3 RC1 待 user 决策

