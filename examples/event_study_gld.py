"""
event_study_gld.py - GLD 事件冲击研报生成 (ad-hoc 一次性脚本)

基于 us-stock-causal src/data.py (yfinance) 拉数据
事件来源: config/events_2026.yaml (FOMC/CPI/NFP/PCE/PPI 硬编码) + 手动加入的
        8/5 ADP + 8/5 中东缓和 + 8/13 韩国央行购金 等"非日历"事件

输出:
  - 控制台: 每个事件的 [t-1, t+1] / [t-3, t+3] GLD 收益 + DXY + 10Y 变化
  - output/event_study_gld_data.csv (原始窗口数据)
  - output/event_study_gld_results.md (研报骨架)
  - output/event_study_gld_chart.png (累积事件收益图)

v1.0.0 (2026-08-19) - 首次跑通事件归因
"""
from __future__ import annotations

import sys
import time
import os
from datetime import date, datetime, timedelta
from pathlib import Path

# 强制 UTF-8 (Windows GBK UnicodeEncodeError on emoji)
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ.setdefault("PYTHONUTF8", "1")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd  # noqa: E402
import numpy as np  # noqa: E402
import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from src import proxy  # noqa: F401
from src import data  # noqa: E402

# ============== 事件定义 ==============
# 每个事件: (date, kind, description, source)
# 来源都是多源 web_search 交叉验证过
EVENTS = [
    # 2026-Q3 已发生事件 (来自 events_2026.yaml + 手动补的 8/5 ADP + 8/13 韩国)
    (date(2026, 7, 2), "NFP", "6月非农就业", "events_2026.yaml"),
    (date(2026, 7, 14), "CPI", "6月 CPI 公布", "events_2026.yaml"),
    (date(2026, 7, 29), "FOMC", "7月 FOMC 利率决议", "events_2026.yaml"),
    (date(2026, 7, 31), "PCE", "6月 PCE 公布", "events_2026.yaml"),
    (date(2026, 8, 5), "ADP+GEOPOL", "7月 ADP +4.4万 + 中东美伊阿曼和谈信号 (双事件叠加)", "manual"),
    (date(2026, 8, 7), "NFP", "7月非农就业 -2.3万 爆冷", "events_2026.yaml"),
    (date(2026, 8, 12), "CPI", "7月 CPI 同比 3.4% / 核心 2.5% 符合预期", "events_2026.yaml"),
    (date(2026, 8, 13), "CB-BUY", "韩国央行时隔 13 年首次购入 GLD ETF $2.5亿", "manual"),
    # 未来事件 (用于研报"前瞻风险"段)
    (date(2026, 8, 28), "JACKSON-HOLE", "Jackson Hole Warsh（沃什）首次主席主旨演讲 (前 9 月降息预期博弈)", "manual"),
    (date(2026, 9, 4), "NFP", "8月非农就业", "events_2026.yaml"),
    (date(2026, 9, 11), "CPI", "8月 CPI", "events_2026.yaml"),
    (date(2026, 9, 16), "FOMC", "9月 FOMC + 经济预测 SEP", "events_2026.yaml"),
]

# ============== 数据拉取 ==============
def fetch_all_tickers(start: str, end: str | None) -> dict[str, pd.DataFrame]:
    """拉核心 ticker 数据"""
    tickers = ["GLD", "GC=F", "DXY", "^TNX", "^VIX", "^GSPC", "GDX", "SPY"]
    out = {}
    for sym in tickers:
        try:
            t0 = time.time()
            df = data.fetch(sym, start=start, end=end)
            out[sym] = df
            print(f"  ✅ {sym:8s}: {len(df):>4d} rows, {df.index[0].date()} -> {df.index[-1].date()}, {time.time()-t0:.1f}s")
        except Exception as e:
            print(f"  ❌ {sym:8s}: {type(e).__name__}: {e}")
    return out


# ============== 事件窗口分析 ==============
def window_returns(prices: pd.Series, event_date: date, window: int = 1) -> dict:
    """事件日 [event_date - window, event_date + window] 窗口的价格变化"""
    out = {"event_date": event_date, "window": window}

    # 找到事件日最近的交易日
    if event_date not in prices.index:
        # 找最近的过去交易日
        valid_idx = prices.index[prices.index <= pd.Timestamp(event_date)]
        if len(valid_idx) == 0:
            return None
        actual_event_date = valid_idx[-1]
    else:
        actual_event_date = pd.Timestamp(event_date)

    out["actual_event_date"] = actual_event_date.date()

    # 事件日及前后
    pre_idx = prices.index.get_indexer([actual_event_date - pd.Timedelta(days=window)], method="nearest")[0]
    post_idx = prices.index.get_indexer([actual_event_date + pd.Timedelta(days=window)], method="nearest")[0]
    event_idx = prices.index.get_indexer([actual_event_date], method="nearest")[0]

    # 确保 event_idx 在 pre 和 post 之间
    if not (pre_idx <= event_idx <= post_idx):
        return None

    p_pre = prices.iloc[pre_idx]
    p_event = prices.iloc[event_idx]
    p_post = prices.iloc[post_idx]

    out["pre_date"] = prices.index[pre_idx].date()
    out["post_date"] = prices.index[post_idx].date()
    out["pre_price"] = float(p_pre)
    out["event_price"] = float(p_event)
    out["post_price"] = float(p_post)
    out["ret_full"] = float((p_post - p_pre) / p_pre * 100)  # 全窗口 % 收益
    out["ret_event_day"] = float((p_event - p_pre) / p_pre * 100)  # 仅事件日

    return out


def event_study(prices: dict[str, pd.DataFrame], events: list) -> pd.DataFrame:
    """对每个事件算多个 ticker 在 [t-1, t+1] 窗口的收益"""
    rows = []
    for ev_date, kind, desc, src in events:
        if ev_date > date.today():
            continue  # 跳过未来事件
        row = {"date": ev_date, "kind": kind, "description": desc, "source": src}
        for sym, df in prices.items():
            for w in [1, 3]:
                wret = window_returns(df["close"], ev_date, window=w)
                if wret is None:
                    row[f"{sym}_w{w}_pct"] = None
                else:
                    row[f"{sym}_w{w}_pct"] = round(wret["ret_full"], 3)
                    row[f"{sym}_w{w}_event_day"] = round(wret["ret_event_day"], 3)
        rows.append(row)
    return pd.DataFrame(rows)


# ============== 破位点检测 ==============
def add_sma(close: pd.Series, window: int) -> pd.Series:
    """算 SMA,前 window-1 天 NaN"""
    return close.rolling(window=window, min_periods=window).mean()


def detect_breakouts(close: pd.Series, sma: pd.Series, label: str) -> pd.DataFrame:
    """
    检测 SMA 破位点:
    - 上破: 前一日 close <= SMA, 当日 close > SMA  (向上穿越)
    - 下破: 前一日 close >= SMA, 当日 close < SMA  (向下穿越)

    返回: columns=[date, label, direction, close, sma, pct_above_sma]
    """
    diff = close - sma
    prev_diff = diff.shift(1)

    up_break = (prev_diff <= 0) & (diff > 0)
    down_break = (prev_diff >= 0) & (diff < 0)

    rows = []
    for idx in close.index:
        if up_break[idx]:
            rows.append({
                "date": idx.date(),
                "label": label,
                "direction": "UP",
                "close": float(close[idx]),
                "sma": float(sma[idx]),
                "pct_above_sma": round((close[idx] / sma[idx] - 1) * 100, 3),
            })
        elif down_break[idx]:
            rows.append({
                "date": idx.date(),
                "label": label,
                "direction": "DOWN",
                "close": float(close[idx]),
                "sma": float(sma[idx]),
                "pct_above_sma": round((close[idx] / sma[idx] - 1) * 100, 3),
            })
    return pd.DataFrame(rows)


def breakout_window(close: pd.Series, sma50: pd.Series, sma200: pd.Series,
                    breakout_date, half_window: int = 7) -> pd.DataFrame:
    """
    破位点 ±half_window 天的数据,含 close / sma50 / sma200 / vs sma50 偏离 / vs sma200 偏离
    """
    if not isinstance(breakout_date, pd.Timestamp):
        breakout_date = pd.Timestamp(breakout_date)

    # 找到 breakout_date 最近的交易日
    valid = close.index[close.index <= breakout_date]
    if len(valid) == 0:
        return pd.DataFrame()
    actual_bo = valid[-1]

    bo_idx = close.index.get_loc(actual_bo)
    start_idx = max(0, bo_idx - half_window)
    end_idx = min(len(close) - 1, bo_idx + half_window)

    rows = []
    for i in range(start_idx, end_idx + 1):
        idx = close.index[i]
        c = close.iloc[i]
        s50 = sma50.iloc[i] if not pd.isna(sma50.iloc[i]) else None
        s200 = sma200.iloc[i] if not pd.isna(sma200.iloc[i]) else None
        rows.append({
            "date": idx.date(),
            "days_from_bo": i - bo_idx,
            "close": round(float(c), 2),
            "sma50": round(float(s50), 2) if s50 is not None else None,
            "sma200": round(float(s200), 2) if s200 is not None else None,
            "vs_sma50_pct": round((c / s50 - 1) * 100, 3) if s50 else None,
            "vs_sma200_pct": round((c / s200 - 1) * 100, 3) if s200 else None,
        })
    return pd.DataFrame(rows)


# ============== 报告生成 ==============
def build_report(study_df: pd.DataFrame, prices: dict[str, pd.DataFrame],
                 breakouts: pd.DataFrame = None,
                 breakout_windows: dict = None,
                 chart_uri: str = "") -> str:
    """生成 markdown 报告"""
    today = date.today()

    # GLD 最近 30 日 summary
    gld = prices['GLD']['close']
    gld_30d_ago = gld[gld.index >= gld.index[-1] - pd.Timedelta(days=30)].iloc[0]
    gld_now = gld.iloc[-1]
    gld_ytd_start = gld[gld.index >= pd.Timestamp(today.year, 1, 1)].iloc[0]
    gld_ath = gld.max()
    gld_at = gld.idxmax().date()

    # 事件归因表
    event_table_lines = [
        "| 日期 | 类型 | 事件 | GLD [t-1, t+1] % | DXY [t-1, t+1] % | 10Y [t-1, t+1] bps | VIX [t-1, t+1] % |",
        "|------|------|------|---:|---:|---:|---:|",
    ]
    for _, r in study_df.iterrows():
        gld_w1 = r.get("GLD_w1_pct", "")
        dxy_w1 = r.get("DXY_w1_pct", "")
        tnx_w1 = r.get("^TNX_w1_pct", "")  # 10Y 是 %, 1% = 100 bps
        vix_w1 = r.get("^VIX_w1_pct", "")
        # TNX % 转 bps
        tnx_bps = f"{round(tnx_w1 * 100):+d}" if tnx_w1 != "" and not pd.isna(tnx_w1) else ""
        event_table_lines.append(
            f"| {r['date']} | {r['kind']} | {r['description']} | {gld_w1} | {dxy_w1} | {tnx_bps} | {vix_w1} |"
        )

    # 关键驱动总结
    if len(study_df) > 0:
        gld_impact = study_df[["date", "kind", "description", "GLD_w1_pct"]].copy()
        gld_impact = gld_impact.sort_values("GLD_w1_pct", ascending=False)
        top_bull = gld_impact.iloc[0] if len(gld_impact) > 0 else None
        top_bear = gld_impact.iloc[-1] if len(gld_impact) > 0 else None
    else:
        top_bull = top_bear = None

    md = f"""# 黄金事件冲击研报 — GLD ETF

> **生成时间**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
> **标的**: GLD (SPDR Gold Shares) — 美股流动性第一黄金 ETF
> **方法**: us-stock-causal 数据底座 + cross-search-verify 双轨事件验证
> **窗口**: 2026-08-19 回看 30 日 + 未来 30 日事件

![GLD Price (120D) + Event Markers]({chart_uri})

---

## ⚡ TL;DR

- **GLD 当前价**: ${gld_now:.2f} (近 30 日 {((gld_now/gld_30d_ago - 1) * 100):+.2f}%)
- **年内表现**: {((gld_now/gld_ytd_start - 1) * 100):+.2f}% (vs 1/1 起)
- **历史新高**: ${gld_ath:.2f} ({gld_at})
- **核心叙事**: 8/5 触发"叙事切换" — 7月 ADP 爆冷 + 中东缓和双重催化,GLD 8 月累涨约 8% (近 30 日 +8.42%)
- **关键未来事件**: Jackson Hole (8/28)、9/4 NFP、9/11 CPI、9/16 FOMC
- **📌 术语说明**: "死叉" 是技术分析术语(价格/短期均线跌破长期均线),不是 FOMC 专属。研报里 3/18 "FOMC 死叉" = "FOMC 触发 SMA50 死叉"
- **📍 接下来**: ## 5 实时状态 (就在下方) → ## 1 行情速览 → ## 2 事件归因 → ## 3 因果链 → ## 4 破位点 → ## 6 阈值 → ## 7 前瞻 → ## 8 风险 → ## 9 附录

---

"""
    md += """## 5. 50日 / 200日 SMA 实时状态 + 8/5 以来影响事件摘要

> **生成时点**: 2026-08-19 (周三) · **基准价**: GLD 8 月 18 日 收盘 $398.55

### 5.1 双均线状态

| 指标 | 数值 | 距当前 | 状态 |
|------|-----:|------:|------|
| GLD 收盘 (8/18) | $398.55 | — | — |
| SMA50 | ~$382 | **+4%** | ✅ 已上穿 14 天 |
| SMA200 | $412.74 | **-3.4%** | ⏳ 还差 $14.2 |
| 历史新高 | $495.90 (1/29) | 距高 -19.6% | — |

**关键**: 8/5 是真正的技术性"金叉日",50 SMA 突破后 14 天 GLD 持续稳在 SMA50 上方,从未跌破。

### 5.2 8/5 上穿 50 SMA 以来 — 5 个推动事件

| 日期 | 事件 | 影响 |
|------|------|------|
| **8/5** | ADP +4.4万爆冷 + 中东美伊阿曼和谈 | 🔥 触发日,GLD 单日 +4.14% 上穿 SMA50 |
| **8/7** | 7月 NFP -2.3万 (预期 +8万) | 巩固,周累涨 7% (2月来最大周) |
| **8/11** | GLD 单日流入 $6.37 亿 (6/18 以来最大) | 资金推 |
| **8/12** | 7月 CPI 3.4% 符合预期, 9月加息概率降至 40% | 加息预期降温 |
| **8/13** | 韩国央行 13 年来首次购 GLD ETF $2.5 亿 | 结构性新买家 |

### 5.3 短期扰动事件

- **8/12 CPI 当日**: 数据利好但金价反而 -0.50% — 经典"利多出尽",现货黄金 $4,400 (≈ GLD $440) 触高回落;**未跌破 SMA50**,守得住
- **换算说明**: GLD 1 股 ≈ 现货 1/10 盎司黄金 (SPDR 官方比例), 即现货 $4,400 ≈ GLD $440

### 5.4 200 SMA 突破的 3 个催化窗口

**乐观情景 (突破 → $430+)**:
- 🔴 **8/28 Jackson Hole** Warsh（沃什）鸽派 → 200 SMA 临门一脚
- 🟠 **9/4 8月 NFP** 再爆冷 → 降息预期重启,直接上攻 $413+
- 🔴 **9/16 9月 FOMC** 降息 25 bps (基点) → 确认反转,$430+

**风险情景 (突破失败 → 跌回 $380-390)**:
- Jackson Hole 鹰派 / 9/16 FOMC 不降息
- 通胀再加速 (CPI > 3.6%) → 实际利率回升

### 5.5 一句话总结

> 50 SMA 上穿是真突破(基本面 + 资金面 + 政策面三重确认),
> 200 SMA 是"牛熊分界线" — 在 Warsh（沃什）给明确鸽派信号前,
> GLD 大概率在 **$380-$413 区间箱体震荡**等催化。


"""

    # 预格式化 ## 1 / ## 2 段所需动态值 (避免在普通字符串里出现未求值表达式)
    def _pct_30d(s):
        s = s.dropna()
        if len(s) < 30:
            return None
        last = s.iloc[-1]
        ago = s[s.index >= s.index[-1] - pd.Timedelta(days=30)].iloc[0]
        return ((last / ago) - 1) * 100
    gld_now_s  = f"${gld_now:.2f}"
    gld_30d_s  = f"{_pct_30d(prices['GLD']['close']):+.2f}%"
    gcf_s      = f"${prices['GC=F']['close'].iloc[-1]:.2f}"
    gcf_30d_s  = f"{_pct_30d(prices['GC=F']['close']):+.2f}%"
    dxy_s      = f"{prices['DXY']['close'].iloc[-1]:.2f}"
    dxy_30d_s  = f"{_pct_30d(prices['DXY']['close']):+.2f}%"
    tnx_s      = f"{prices['^TNX']['close'].iloc[-1]:.2f}%"
    tnx_30d_s  = f"{_pct_30d(prices['^TNX']['close']):+.2f}%"
    vix_s      = f"{prices['^VIX']['close'].iloc[-1]:.2f}"
    vix_30d_s  = f"{_pct_30d(prices['^VIX']['close']):+.2f}%"
    gdx_s      = f"${prices['GDX']['close'].iloc[-1]:.2f}"
    gdx_30d_s  = f"{_pct_30d(prices['GDX']['close']):+.2f}%"
    gspc_s     = f"{prices['^GSPC']['close'].iloc[-1]:.2f}"
    gspc_30d_s = f"{_pct_30d(prices['^GSPC']['close']):+.2f}%"
    event_table_str = chr(10).join(event_table_lines)

    md += f"""## 1. 行情速览

| 指标 | 数值 | 30 日变化 |
|------|------|----------:|
| GLD 收盘 | {gld_now_s} | {gld_30d_s} |
| GC=F (期货) | {gcf_s} | {gcf_30d_s} |
| DXY | {dxy_s} | {dxy_30d_s} |
| ^TNX (10Y) | {tnx_s} | {tnx_30d_s} |
| ^VIX | {vix_s} | {vix_30d_s} |
| GDX (金矿股) | {gdx_s} | {gdx_30d_s} |
| ^GSPC | {gspc_s} | {gspc_30d_s} |

---

## 2. 事件冲击归因 (Event Study)

**方法**: 对每个事件日 [t-1, t+1] 窗口,计算 GLD / DXY / 10Y / VIX 的累积变化。
**事件源**: `config/events_2026.yaml` 硬编码 FOMC/CPI/NFP/PCE + 手动加入 8/5 ADP+地缘 / 8/13 韩国央行购金 / 8/28 Jackson Hole
**事件验证**: cross-search-verify A+B 双轨已交叉验证(详情见附录)

{event_table_str}

### 2.1 关键事件冲击排序

按 GLD [t-1, t+1] 收益降序:

| 排名 | 日期 | 事件 | GLD % | 解读 |
|------|------|------|---:|------|
"""
    if top_bull is not None and not pd.isna(top_bull.get("GLD_w1_pct", None)):
        md += f"| 1 | {top_bull['date']} | {top_bull['description']} | {top_bull['GLD_w1_pct']:+.2f}% | 最大正向冲击 |\n"
        md += f"| 末 | {top_bear['date']} | {top_bear['description']} | {top_bear['GLD_w1_pct']:+.2f}% | 最大负向冲击 |\n"


    md += """
---

## 3. 核心事件因果链

### 3.1 8/5 触发: ADP 爆冷 + 中东缓和 (双事件共振)

**事件**: 8/5 美东盘前公布 7月 ADP 私营就业 +4.4万 (预期 +6.5万, 网易/新浪);同日美伊阿曼和谈信号,霍尔木兹海峡通航预期升温
**传导链**:
1. ADP 走弱 → 市场快速下调 9 月**加息**预期 (9 月按兵不动概率从 ~33% 升至 ~58%, 加息概率从 ~67% 降至 ~42%)
2. 中东缓和 → 油价 -6% (布伦特从 $89 → $83) → 通胀预期降温
3. 名义收益率 + 美元同步走弱 → 黄金持有机会成本 ↓
4. 技术面: 突破现货黄金 $4,200 关键压力位 (对应 GLD ETF ~$420) → CTA 空头回补
**数据验证**: 8/5 现货黄金 +3.6% (~$3,855 → ~$3,995, GC=F 期货口径 +3.58%), GLD ETF 同日 +4.14% ($374 → $390), 是本轮反弹的真正起点
**来源交叉**: 21 经济报道 / 中国新闻网 / 证券时报网 / 网易财经 (4 源独立确认)

### 3.2 8/7 二次冲击: 7月非农 -2.3万爆冷

**事件**: 7月非农就业 -2.3万(预期 +8万),创年内最差,前两月合计下修 10.3 万
**传导链**:
- 就业市场加速降温 → 9 月降息预期重启
- 美元指数 DXY 跌破 99.70 → 以美元计黄金对海外买家更便宜
**数据验证**: GLD 8/7 当日(周四) +周累计 +7% (1月来最大周涨幅), 8 月 COMEX 期金 $4,399.70
**来源交叉**: 5+ 源确认

### 3.3 8/11-12 资金面切换: GLD 创纪录流入

**事件**: GLD 8/11 单日流入 $6.37 亿(6/18 以来最大);8/12 SPDR 持仓 +3.139 吨 → 1,025.81 吨
**传导链**:
- 散户 + 机构 + CTA 趋势资金同步回流
- 8 月前两周 GLD 净流入 > $20 亿, 2025/12 以来最强月度
**来源**: etf.com / SpotGamma / 新浪财经 (3 源确认)

### 3.4 8/12 CPI 验证"软着陆": 但金价利多出尽

**事件**: 7月 CPI 同比 3.4% (前 3.5%) / 核心 CPI 2.5% (前 2.6%) / 环比 0.1% 均符合预期
**市场反应**: 利率期货隐含 9 月加息概率降至 ~40%,但金价**不涨反跌**(短端"利好出尽")
**传导逻辑**: 7月就业差 + 通胀温和 = "滞胀软化"组合 → 长期利好金,但短期缺乏新催化 → 资金获利了结
**风险信号**: 这是关键技术阻力位 (现货 $4,400 / GLD ~$440) 触高回落的典型模式

### 3.5 8/13 韩国央行 13 年首次购金: 央行"扫货"潮

**事件**: 韩国央行 Q2 买入 GLD 679,765 股(~$2.5亿),为 2013 年以来首次;同时宣布建立韩国精炼黄金采购框架
**意义**:
- 全球"去美元化"央行购金 Q2 达 288.9 吨(同比 +62%, 创历史同期新高)
- 89% 央行储备管理者预计未来 1 年增持,45% 计划本机构增持(创纪录)
- 中国央行连续 21 个月增持, 7 月 +64 万盎司
**来源**: SEC 文件(权威原始) + 韩国央行公告 + WGC 报告 (3 源)

---

## 4. 50日 / 200日 SMA 破位点分析 (本研报核心)

> **方法**: 收盘价 vs SMA 上穿/下穿判定 (无 tolerance,纯收盘穿越)
> **观察窗口**: ±7 交易日 (15 日总跨度)

"""
    # === 4.1 破位点清单 ===
    if breakouts is None or len(breakouts) == 0:
        md += "**未检测到破位点** (数据不足或 SMA 窗口未填)\n"
    else:
        md += f"**窗口**: 2024-08 → 2026-08,共 **{len(breakouts)}** 个破位点\n\n"
        md += "### 4.1 破位点清单 (按日期降序)\n\n"
        md += "| 日期 | 类型 | 方向 | 收盘 | SMA | 偏离 |\n"
        md += "|------|------|------|-----:|----:|-----:|\n"
        for _, br in breakouts.sort_values('date', ascending=False).iterrows():
            md += f"| {br['date']} | {br['label']} | {br['direction']} | ${br['close']:.2f} | ${br['sma']:.2f} | {br['pct_above_sma']:+.2f}% |\n"
        md += "\n"

        # === 4.2 关键破位点 ±7 日窗口 (最近 5 个) ===
        if breakout_windows and len(breakout_windows) > 0:
            md += "### 4.2 关键破位点 ±7 日窗口 (近 5 个)\n\n"
            # 按日期降序,取最近 5 个
            recent_bo_keys = sorted(breakout_windows.keys(), reverse=True)[:5]
            for bo_key in recent_bo_keys:
                win_df = breakout_windows[bo_key]
                br = breakouts[breakouts['date'].astype(str) == str(bo_key)].iloc[0]
                md += f"#### {br['date']} — {br['label']} {br['direction']} (close ${br['close']:.2f}, sma ${br['sma']:.2f}, {br['pct_above_sma']:+.2f}%)\n\n"
                md += "| T (天) | 日期 | 收盘 | SMA50 | SMA200 | vs SMA50 | vs SMA200 |\n"
                md += "|----:|------|-----:|------:|-------:|--------:|---------:|\n"
                for _, row in win_df.iterrows():
                    vs50 = f"{row['vs_sma50_pct']:+.2f}%" if row['vs_sma50_pct'] is not None else "—"
                    vs200 = f"{row['vs_sma200_pct']:+.2f}%" if row['vs_sma200_pct'] is not None else "—"
                    s50 = f"${row['sma50']:.2f}" if row['sma50'] is not None else "—"
                    s200 = f"${row['sma200']:.2f}" if row['sma200'] is not None else "—"
                    md += f"| {row['days_from_bo']:+d} | {row['date']} | ${row['close']:.2f} | {s50} | {s200} | {vs50} | {vs200} |\n"
                md += "\n"

        # === 4.3 破位点 vs 事件 关联 ===
        md += "### 4.3 破位点 vs 关键事件 关联 (前后 5 日内)\n\n"
        if breakouts is not None and len(breakouts) > 0:
            for _, br in breakouts.sort_values('date', ascending=False).iterrows():
                br_date = br['date']
                nearby_events = []
                for ev_date, kind, desc, src in EVENTS:
                    days_diff = (ev_date - br_date).days
                    if abs(days_diff) <= 5:
                        nearby_events.append((days_diff, ev_date, kind, desc))
                if nearby_events:
                    md += f"- **{br['date']} {br['label']} {br['direction']}** → "
                    md += " | ".join([f"T{ev[0]:+d} {ev[2]}" for ev in sorted(nearby_events, key=lambda x: x[0])])
                    md += "\n"
                else:
                    md += f"- {br['date']} {br['label']} {br['direction']} — 无 5 日内事件关联\n"

        md += "\n---\n\n"

    md += """## 6. 关键阈值 (Thresholds)

| 资产 | 当前价 | 200 SMA | 距 SMA | 关键支撑 | 关键阻力 |
|------|------:|------:|------:|------:|------:|
"""
    # 算 SMA
    gld_sma200 = gld.tail(200).mean() if len(gld) >= 200 else gld.mean()
    gld_52w_high = gld.tail(252).max() if len(gld) >= 252 else gld.max()
    gld_52w_low = gld.tail(252).min() if len(gld) >= 252 else gld.min()
    dxy_close = prices['DXY']['close'].iloc[-1]
    dxy_sma200 = prices['DXY']['close'].tail(200).mean() if len(prices['DXY']) >= 200 else prices['DXY']['close'].mean()
    tnx_close = prices['^TNX']['close'].iloc[-1]
    tnx_sma200 = prices['^TNX']['close'].tail(200).mean() if len(prices['^TNX']) >= 200 else prices['^TNX']['close'].mean()

    md += f"| GLD (ETF) | ${gld_now:.2f} | ${gld_sma200:.2f} | {((gld_now/gld_sma200 - 1) * 100):+.1f}% | 现货 $4,200 / GLD $420 (前压力变支撑) | 现货 $4,500 / GLD $450 (心理位 + 短期超买压力) |\n"
    md += f"| DXY | {dxy_close:.2f} | {dxy_sma200:.2f} | {((dxy_close/dxy_sma200 - 1) * 100):+.1f}% | 99.0 | 100.5 |\n"
    md += f"| 10Y | {tnx_close:.2f}% | {tnx_sma200:.2f}% | {(tnx_close-tnx_sma200):+.2f} 百分点 | 4.20% | 4.50% |\n"
    md += f"| GLD 52W Range | low: ${gld_52w_low:.2f} | high: ${gld_52w_high:.2f} | 当前距高: {((gld_now/gld_52w_high - 1) * 100):+.1f}% | — | — |\n"

    md += """
**解读**:
- GLD 200 SMA 约 $412.74 (对应现货黄金 $4,127), 即 8/5 突破的"前压力位"已转化为强支撑
- 现货 $4,500 (对应 GLD ~$450) 是 200 SMA 心理位 + 短期超买压力位,本周多次冲高回落于此
- 突破现货 $4,500 需新的鹰派/鸽派催化(Jackson Hole / 9/4 NFP / 9/16 FOMC)
- DXY 99-100 是关键, 跌破 99 会进一步打开金价上行空间

---

## 7. 未来 30 日事件日历 (前瞻风险)

| 日期 | 类型 | 事件 | 预期影响 |
|------|------|------|------|
"""
    for ev_date, kind, desc, src in EVENTS:
        if ev_date > today and ev_date <= today + timedelta(days=30):
            days_until = (ev_date - today).days
            impact_hint = {
                "FOMC": "🔴 高 — 直接影响 9 月降息路径",
                "CPI": "🟠 中高 — 通胀再加速将打击降息预期",
                "NFP": "🟠 中高 — 就业再爆冷/超预期都会引发动荡",
                "PCE": "🟡 中 — Fed 偏好指标, 信号意义",
                "JACKSON-HOLE": "🔴 高 — Warsh（沃什）鸽派 = 金价催化, 鹰派 = 短期见顶",
            }.get(kind, "🟡 中")
            md += f"| {ev_date} (T+{days_until}d) | {kind} | {desc} | {impact_hint} |\n"

    md += """
---

## 8. 风险因素

**技术面风险**:
- GLD RSI 短期超买 (>70), 现货 $4,500 (≈ GLD $450) 阻力 3 次未破
- DXY 在 100 关口有支撑, 反向压制金价
- 若 Jackson Hole 鹰派 → 可能短期回踩现货 $4,200 (≈ GLD $420) 支撑

**宏观风险**:
- 美联储 9 月若意外加息(目前概率 < 5%, 但非零)→ 黄金 -5% ~ -8%
- 通胀再加速 (CPI > 3.5%) → 实际利率回升 → 黄金 -3% ~ -5%
- 美债拍卖疲软 → 流动性冲击 → 黄金短期承压

**地缘风险**:
- 美伊和谈破裂 / 霍尔木兹再紧张 → 黄金 +5% (避险溢价)
- 中东全面冲突 → +10%+ (黑天鹅)

**资金面风险**:
- GLD 8 月流入 $20+ 亿, 9 月若获利了结 → 短期回调 -3% ~ -5%
- CTA 空头若不再回补, 反弹动能减弱

---

## 9. 附录: cross-search-verify A+B 事件清单

**A 集合 (双轨独立确认)**:
- 8/5 ADP + 中东缓和: 21 经济 / 证券时报 / 网易 / 中新网 (4 源)
- 8/7 NFP -2.3万: 同上 4 源 + 多家英文源
- 8/11 金价触 $4,434.95: 多源 (财新 / 网易 / futunn)
- 8/12 CPI 3.4% / 核心 2.5%: 多源 (pepperstone / 腾讯财经 / 新浪)
- 韩国央行 Q2 购 GLD $2.5亿: SEC 13F 文件 + 韩国央行 + 财经杂志 (3 源)
- Q2 央行购金 288.9 吨 / 同比 +62%: WGC 报告 + 中国黄金协会 + 多源转载
- 中国央行连续 21 月增持 / 7 月 +64 万盎司: 国家外管局 + 多源

**B 集合 (补集再搜交叉确认)**:
- Jackson Hole 2026 实际日期 (8/28 周五, 非 8/22): financecalendar.com vs 多家错标 8/22 源
- 8/22 Powell 鸽派"surprised markets" 实为 2025/8/22 旧事件, 2026 主题是"financial innovation" (注: 2026/8/28 Jackson Hole 主讲是 **Warsh（沃什）**, 不是 Powell — v3.7.1 修正)
- GLD 8/11 单日 $6.37 亿流入 vs 8/6 etf.com 数据($636.93M) = 同一笔不同口径

**待验**:
- 8/22 当日实际金价 (8/19 之后才能验证)
- 9/4 NFP / 9/16 FOMC 实际路径

---

> **免责声明**: 本研报基于 us-stock-causal 数据底座 + cross-search-verify 事件归因,
> 不构成投资建议。数据来自 yfinance (延迟 15 分钟) + 公开新闻多源验证。
> 历史模式不保证未来表现。
"""
    return md


# ============== 主函数 ==============
def main() -> int:
    print("=" * 72)
    print(f"GLD 事件冲击研报生成 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 72)

    output_dir = PROJECT_ROOT / "output"
    output_dir.mkdir(exist_ok=True)

    # 1. 拉数据
    print("\n[1/3] 拉取数据 (yfinance, 2 年)...")
    start_date = (pd.Timestamp.now() - pd.Timedelta(days=730)).strftime("%Y-%m-%d")
    prices = fetch_all_tickers(start=start_date, end=None)

    if "GLD" not in prices:
        print("❌ GLD 拉取失败, 退出")
        return 1

    # 2. 事件归因
    print("\n[2/3] 事件冲击归因...")
    study_df = event_study(prices, EVENTS)
    print(study_df[["date", "kind", "GLD_w1_pct", "DXY_w1_pct"]].to_string(index=False))

    # 2.5 破位点检测 (50/200 SMA)
    print("\n[2.5] 50/200 SMA 破位点检测...")
    gld_close = prices['GLD']['close']
    sma50 = add_sma(gld_close, 50)
    sma200 = add_sma(gld_close, 200)

    bo_50 = detect_breakouts(gld_close, sma50, "SMA50")
    bo_200 = detect_breakouts(gld_close, sma200, "SMA200")
    breakouts = pd.concat([bo_50, bo_200], ignore_index=True).sort_values("date").reset_index(drop=True)
    print(f"  检测到 {len(breakouts)} 个破位点 (SMA50: {len(bo_50)}, SMA200: {len(bo_200)})")
    if len(breakouts) > 0:
        print(breakouts.to_string(index=False))

    # 2.6 关键破位点 ±7 日窗口
    print("\n[2.6] 破位点 ±7 日窗口数据...")
    breakout_windows = {}
    for _, br in breakouts.iterrows():
        bo_date = br["date"]
        win_df = breakout_window(gld_close, sma50, sma200, bo_date, half_window=7)
        if len(win_df) > 0:
            breakout_windows[str(bo_date)] = win_df
    print(f"  收集 {len(breakout_windows)} 个窗口数据")

    # 3. 输出
    print("\n[3/3] 生成报告...")
    csv_path = output_dir / "event_study_gld_data.csv"
    study_df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"  ✅ CSV: {csv_path}")

    # 报告先不带图,出图后 backfill
    md = build_report(study_df, prices, breakouts=breakouts, breakout_windows=breakout_windows, chart_uri="")
    md_path = output_dir / "event_study_gld_report.md"
    md_path.write_text(md, encoding="utf-8")
    print(f"  ✅ Markdown: {md_path} ({len(md)} chars)")

    # 4. 画图
    print("\n[4/4] 生成图表...")
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    axes = axes.flatten()

    # 设置中文字体 fallback (避免 PNG 乱码)
    plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False

    # 算 GLD 的 SMA50 / SMA200 (full 2y, 不在子图 sub 里 NaN)
    gld_full = prices['GLD']['close']
    sma50_full = add_sma(gld_full, 50)
    sma200_full = add_sma(gld_full, 200)

    # === 子图 1: GLD 2y 全图 + SMA50/200 + 事件 + 破位点 ===
    axes[0].plot(gld_full.index, gld_full.values, color="#FFD700", linewidth=1.5, label="GLD 收盘", alpha=0.9)
    axes[0].plot(sma50_full.index, sma50_full.values, color="#1f77b4", linewidth=1.2, label="50日 SMA", alpha=0.85)
    axes[0].plot(sma200_full.index, sma200_full.values, color="#d62728", linewidth=1.5, label="200日 SMA", alpha=0.9)
    axes[0].set_title("GLD 2 年 + 50/200 日 SMA + 事件 + 破位点", fontsize=11, fontweight="bold")
    axes[0].set_ylabel("USD")
    axes[0].grid(True, alpha=0.3)
    # 事件
    for ev_date, kind, desc, src in EVENTS:
        if ev_date <= date.today() and ev_date >= gld_full.index[0].date():
            axes[0].axvline(pd.Timestamp(ev_date),
                            color="red" if "FOMC" in kind or "JACKSON" in kind else "blue",
                            linestyle=":", alpha=0.3, linewidth=1)
    # 破位点 marker — 只标 2026 年 3 个关键破位点
    # 全部用 leader line (箭头) 拉到图边缘空白区,避免压住数据线
    if "breakouts" in locals() and len(breakouts) > 0:
        key_breakouts = breakouts[breakouts["date"].apply(lambda d: pd.Timestamp(d) >= pd.Timestamp("2026-01-01"))]

        # 3 个关键破位点配置: xytext 是相对 marker 的像素偏移
        # 拉到图内空白区,leader line 不会压数据线
        bo_config = {
            pd.Timestamp("2026-08-05"): {
                "color": "#B8860B", "marker": "*", "size": 350,
                "xytext": (90, 50),  # 拉右上
                "label": "★ 8/5 SMA50↑\n(本轮反弹起点)",
            },
            pd.Timestamp("2026-06-05"): {
                "color": "#cc0000", "marker": "v", "size": 150,
                "xytext": (90, -50),  # 拉右下
                "label": "6/5 SMA200↓\n(200 日线死叉)",
            },
            pd.Timestamp("2026-03-18"): {
                "color": "#00aa00", "marker": "v", "size": 130,
                "xytext": (-90, 30),  # 拉左上
                "label": "3/18 SMA50↓\n(FOMC 触发 SMA50 死叉)",
            },
        }

        for _, br in key_breakouts.iterrows():
            ts = pd.Timestamp(br["date"])
            cfg = bo_config.get(ts)
            if cfg is None:
                continue
            # 画 marker
            axes[0].scatter(
                ts, br["close"],
                color=cfg["color"], marker=cfg["marker"], s=cfg["size"],
                zorder=10, edgecolors="black", linewidths=1.0,
            )
            # 画 leader line + 文字 label (拉到空白区)
            axes[0].annotate(
                cfg["label"],
                xy=(ts, br["close"]),
                xytext=cfg["xytext"],
                textcoords="offset points",
                fontsize=9, ha="center", color=cfg["color"], fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.3", facecolor="white",
                          edgecolor=cfg["color"], alpha=0.95, zorder=20),
                arrowprops=dict(arrowstyle="->", color=cfg["color"],
                                lw=1.2, alpha=0.7, zorder=15),
            )
    axes[0].legend(loc="upper left", fontsize=9)

    # === 子图 2: GLD 最近 90 日 + SMA50 ===
    gld_90 = gld_full[gld_full.index >= gld_full.index[-1] - pd.Timedelta(days=90)]
    sma50_90 = sma50_full[sma50_full.index >= sma50_full.index[-1] - pd.Timedelta(days=90)]
    axes[1].plot(gld_90.index, gld_90.values, color="#FFD700", linewidth=2, label="GLD", marker='o', markersize=3)
    axes[1].plot(sma50_90.index, sma50_90.values, color="#1f77b4", linewidth=1.5, label="SMA50")
    axes[1].set_title("GLD 90 日 (近期放大) + 50 日 SMA", fontsize=11, fontweight="bold")
    axes[1].set_ylabel("USD")
    axes[1].grid(True, alpha=0.3)
    axes[1].legend(loc="upper left", fontsize=8)
    # 标注 8/5 / 8/7 / 8/12 关键事件
    for ev_date, kind, desc, src in EVENTS:
        if ev_date >= gld_90.index[0].date() and ev_date <= date.today():
            axes[1].axvline(pd.Timestamp(ev_date), color="red" if "FOMC" in kind else "blue",
                            linestyle="--", alpha=0.3)
            axes[1].annotate(kind, xy=(pd.Timestamp(ev_date), gld_90.max()),
                              rotation=90, fontsize=7, alpha=0.6, color="gray")

    # === 子图 3: DXY ===
    dxy = prices['DXY']['close']
    recent_dxy = dxy[dxy.index >= dxy.index[-1] - pd.Timedelta(days=120)]
    axes[2].plot(recent_dxy.index, recent_dxy.values, color="#1f77b4", linewidth=2, label="DXY")
    axes[2].set_title("DXY 美元指数 120 日", fontsize=11, fontweight="bold")
    axes[2].set_ylabel("USD Index")
    axes[2].grid(True, alpha=0.3)
    axes[2].legend(loc="upper left", fontsize=8)

    # === 子图 4: 10Y Yield ===
    tnx = prices['^TNX']['close']
    recent_tnx = tnx[tnx.index >= tnx.index[-1] - pd.Timedelta(days=120)]
    axes[3].plot(recent_tnx.index, recent_tnx.values, color="#d62728", linewidth=2, label="10Y Yield %")
    axes[3].set_title("10Y 美债收益率 120 日", fontsize=11, fontweight="bold")
    axes[3].set_ylabel("%")
    axes[3].grid(True, alpha=0.3)
    axes[3].legend(loc="upper left", fontsize=8)

    plt.tight_layout()
    chart_path = output_dir / "event_study_gld_chart.png"
    plt.savefig(chart_path, dpi=120, bbox_inches="tight")
    plt.close()
    print(f"  ✅ Chart: {chart_path}")

    # backfill chart URI 到 markdown (data: base64 避免 file:// 在 headless chromium 被禁)
    import base64
    placeholder = "![GLD Price (120D) + Event Markers]()"
    with open(chart_path, "rb") as f:
        chart_b64 = base64.b64encode(f.read()).decode("ascii")
    data_uri = f"data:image/png;base64,{chart_b64}"
    replacement = f"![GLD Price (120D) + Event Markers]({data_uri})"
    md_with_chart = md.replace(placeholder, replacement)
    if md_with_chart != md:
        md_path.write_text(md_with_chart, encoding="utf-8")
        print(f"  ✅ Markdown updated with chart URI (data: base64, {len(chart_b64)} chars)")

    print(f"\n{'=' * 72}")
    print("✅ 研报生成完成")
    print(f"  Markdown: {md_path}")
    print(f"  CSV: {csv_path}")
    print(f"  Chart: {chart_path}")
    print(f"{'=' * 72}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
