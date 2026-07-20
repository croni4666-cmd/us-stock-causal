"""
src/tickers_universe.py - 我们关注的 ETF 列表 (P7-2 真修残差专用)

**4 指数 + 11 行业 ETF = 15 只**
  - 4 指数: DIA / QQQ / RSP / QQQE (State Street SPDR / Invesco / ProShares)
  - 11 行业: XLK/XLF/XLE/XLY/XLP/XLV/XLI/XLU/XLB/XLRE/XLC (State Street SPDR Select Sector)

**Why 只 15 只 ETF, 不用 config/tickers.yaml 的 49 ticker**:
  - 49 ticker 含 6 宏观 (^VIX/DXY/^TNX...) + 14 期货 (GC=F/CL=F...) + 14 现货 (GLD/SLV/...)
  - 这些不发 N-CSR, 不在 SEC EDGAR 里
  - 只有 ETF (15 只) 才有 N-CSR 持仓公告, 能拉真 sector weights

**Why 不用 RSP/QQQE 的 holdings 推 sector weights**:
  - RSP 是等权 S&P 500 (每个 sector ~7.7%), DIA 偏 industrial
  - QQQE 是等权 Nasdaq 100 (tech 偏多但比 QQQ 轻)
  - 这 2 只的 sector 派生是简化, 不算 "真" sector weights
  - P7-3 单独处理 (季度更新, 接受近似)

**使用**: P7-2 `src/weights.py` 拉 15 只 ETF 的 N-CSR 真 sector weights
"""

# 4 指数 ETF
INDEX_ETFS = [
    "DIA",   # SPDR Dow Jones Industrial Average
    "QQQ",   # Invesco QQQ Trust
    "RSP",   # Invesco S&P 500 Equal Weight
    "QQQE",  # ProShares Nasdaq-100 Equal Weighted
]

# 11 行业 ETF (State Street Select Sector SPDR)
SECTOR_ETFS = [
    "XLK",   # Technology
    "XLF",   # Financials
    "XLE",   # Energy
    "XLY",   # Consumer Discretionary
    "XLP",   # Consumer Staples
    "XLV",   # Health Care
    "XLI",   # Industrials
    "XLU",   # Utilities
    "XLB",   # Materials
    "XLRE",  # Real Estate
    "XLC",   # Communication Services
]

# 全部 15 只 ETF (P7-2 真修对象)
ETF_TICKERS = INDEX_ETFS + SECTOR_ETFS


if __name__ == "__main__":
    print(f"INDEX_ETFS: {len(INDEX_ETFS)}")
    for t in INDEX_ETFS:
        print(f"  - {t}")
    print(f"\nSECTOR_ETFS: {len(SECTOR_ETFS)}")
    for t in SECTOR_ETFS:
        print(f"  - {t}")
    print(f"\nETF_TICKERS (总): {len(ETF_TICKERS)}")
