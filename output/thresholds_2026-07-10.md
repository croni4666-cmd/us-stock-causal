# Thresholds + Residual Report - 2026-07-10

**Generated**: 2026-07-13 17:57:33

**Model**: sector weights + SMA + pivot + 52w range + residual t-test

---
## 4 指数当前水平

| 指数 | 现价 | SMA20 | SMA50 | SMA200 | 200 SMA 位置 | Pivot | R1 | S1 | 52w Pos |
|------|------|-------|-------|--------|-------------|-------|-----|-----|---------|
| DIA | $525.78 | $520.45 | $509.21 | $486.21 | 🟢 +8.14% | $523.83 | $525.51 | $522.5 | 93.2% |
| QQQ | $725.51 | $722.57 | $715.16 | $638.0 | 🟢 +13.72% | $720.88 | $726.63 | $717.53 | 88.3% |
| RSP | $214.3 | $212.01 | $208.05 | $197.77 | 🟢 +8.36% | $213.39 | $214.3 | $212.59 | 94.3% |
| QQQE | $120.61 | $120.21 | $117.12 | $106.27 | 🟢 +13.50% | $120.47 | $121.0 | $120.03 | 90.4% |

### DIA 残差分析 (60d)

- **mean residual**: -0.0122% (t-test p=0.8361, -0.208)
- **std residual**: 0.454%
- **健康度**: ok — weights 健康,无需更新
- **异常日** (|z| > 2σ, 共 3 天):
  - 2026-06-04: actual +1.65% / predicted +0.71% / residual +0.93% (z=+2.08)
  - 2026-06-16: actual +0.58% / predicted -0.46% / residual +1.04% (z=+2.32)
  - 2026-07-02: actual +1.04% / predicted +0.07% / residual +0.97% (z=+2.16)

---


### QQQ 残差分析 (60d)

- **mean residual**: +0.0362% (t-test p=0.5349, 0.624)
- **std residual**: 0.450%
- **健康度**: ok — weights 健康,无需更新
- **异常日** (|z| > 2σ, 共 2 天):
  - 2026-06-05: actual -4.92% / predicted -4.00% / residual -0.92% (z=-2.13)
  - 2026-06-23: actual -3.35% / predicted -2.14% / residual -1.21% (z=-2.77)

---


### RSP 残差分析 (60d)

- **mean residual**: +0.0452% (t-test p=0.3004, 1.045)
- **std residual**: 0.335%
- **健康度**: ok — weights 健康,无需更新
- **异常日** (|z| > 2σ, 共 1 天):
  - 2026-06-26: actual -0.68% / predicted +0.32% / residual -1.00% (z=-3.12)

---


### QQQE 残差分析 (60d)

- **mean residual**: +0.1097% (t-test p=0.1168, 1.592)
- **std residual**: 0.534%
- **健康度**: watch — 权重有轻微偏差,继续观察
- **异常日** (|z| > 2σ, 共 3 天):
  - 2026-05-27: actual -0.89% / predicted +0.26% / residual -1.15% (z=-2.36)
  - 2026-06-01: actual +1.42% / predicted +0.23% / residual +1.19% (z=+2.02)
  - 2026-06-05: actual -4.36% / predicted -2.96% / residual -1.41% (z=-2.84)

---


*Chart: see `output/thresholds_2026-07-10.png`*
