# 📊 归因报告 — 2026-07-10

**生成时间**: 2026-07-20 18:30:19
**模型**: sector weights (config/sector_weights.json, 2026-Q2 近似值)

**4 指数**: DIA / QQQ / RSP / QQQE

**归因方法**: 直接 sector weight × sector return,残差 = actual - predicted

---


## 20 日归因 (lookback 20d)


## 4 指数归因 (2026-07-10)

| 指数 | 实际 % | 预测 % | 残差 % | 主驱动 (top 3) |
|------|--------|--------|--------|----------------|
| DIA | +4.98 | +3.82 | +1.15 | **XLK** +1.41, **XLF** +1.16, **XLV** +0.76 |
| QQQ | +4.49 | +3.83 | +0.66 | **XLK** +2.78, **XLY** +0.42, **XLV** +0.26 |
| RSP | +3.69 | +3.08 | +0.61 | **XLK** +0.91, **XLF** +0.84, **XLI** +0.63 |
| QQQE | +5.12 | +3.31 | +1.81 | **XLK** +1.62, **XLY** +0.58, **XLV** +0.51 |

### DIA — 实际 +4.98% (预测 +3.82%, 残差 +1.15%)
| 行业 | GICS | 贡献 % | 解读 |
|------|------|---------|------|
| XLK | Technology | +1.41 | 📈 主升 |
| XLF | Financials | +1.16 | 📈 主升 |
| XLV | Health Care | +0.76 | 📈 主升 |
| XLY | Cons Discr | +0.46 | 📈 主升 |
| XLE | Energy | -0.28 | ⬇️ 拖累 |
| XLI | Industrials | +0.28 | ⬆️ 拉升 |
| XLP | Cons Staples | -0.08 | ≈ 中性 |
| XLB | Materials | +0.05 | ≈ 中性 |
| XLC | Comm Services | +0.04 | ≈ 中性 |
| XLU | Utilities | +0.03 | ≈ 中性 |
| XLRE | Real Estate | -0.01 | ≈ 中性 |

### QQQ — 实际 +4.49% (预测 +3.83%, 残差 +0.66%)
| 行业 | GICS | 贡献 % | 解读 |
|------|------|---------|------|
| XLK | Technology | +2.78 | 📈 主升 |
| XLY | Cons Discr | +0.42 | 📈 主升 |
| XLV | Health Care | +0.26 | ⬆️ 拉升 |
| XLF | Financials | +0.19 | ⬆️ 拉升 |
| XLI | Industrials | +0.14 | ⬆️ 拉升 |
| XLC | Comm Services | +0.10 | ⬆️ 拉升 |
| XLE | Energy | -0.06 | ≈ 中性 |
| XLP | Cons Staples | -0.03 | ≈ 中性 |
| XLB | Materials | +0.03 | ≈ 中性 |

### RSP — 实际 +3.69% (预测 +3.08%, 残差 +0.61%)
| 行业 | GICS | 贡献 % | 解读 |
|------|------|---------|------|
| XLK | Technology | +0.91 | 📈 主升 |
| XLF | Financials | +0.84 | 📈 主升 |
| XLI | Industrials | +0.63 | 📈 主升 |
| XLV | Health Care | +0.56 | 📈 主升 |
| XLE | Energy | -0.34 | 📉 主跌 |
| XLY | Cons Discr | +0.33 | 📈 主升 |
| XLU | Utilities | +0.16 | ⬆️ 拉升 |
| XLB | Materials | +0.13 | ⬆️ 拉升 |
| XLP | Cons Staples | -0.11 | ⬇️ 拖累 |
| XLRE | Real Estate | -0.07 | ≈ 中性 |
| XLC | Comm Services | +0.06 | ≈ 中性 |

### QQQE — 实际 +5.12% (预测 +3.31%, 残差 +1.81%)
| 行业 | GICS | 贡献 % | 解读 |
|------|------|---------|------|
| XLK | Technology | +1.62 | 📈 主升 |
| XLY | Cons Discr | +0.58 | 📈 主升 |
| XLV | Health Care | +0.51 | 📈 主升 |
| XLF | Financials | +0.39 | 📈 主升 |
| XLI | Industrials | +0.28 | ⬆️ 拉升 |
| XLE | Energy | -0.17 | ⬇️ 拖累 |
| XLC | Comm Services | +0.10 | ⬆️ 拉升 |
| XLP | Cons Staples | -0.08 | ≈ 中性 |
| XLU | Utilities | +0.06 | ≈ 中性 |
| XLB | Materials | +0.03 | ≈ 中性 |
| XLRE | Real Estate | -0.01 | ≈ 中性 |

---

*图: sector 贡献 stacked bar 见 `output/attribution_2026-07-10.png`*
