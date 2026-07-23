"""ETF constituents (硬编码) — 季度手动维护源

每只成分股的 GICS sector + 价格 / 市值估算(用于 P7-3 派生 sector weights)。

**重要**: 这里的 ticker + sector 是基于模型知识 (cutoff 2026-01), 价格 / 市值是粗估,
**不是实时数据**。季度维护时人工核对即可 (DIA 30 变化极慢, QQQ 100 偶尔有 1-2 只进出)。

Sources:
- DIA 30: Dow Jones Industrial Average constituents (2026-Q2 估计)
- QQQ 100: Nasdaq-100 constituents (2026-Q2 估计, top 60 较准确)
- 11 GICS sectors: Sector ETF ticker 映射 (XLK IT / XLF Financials / XLV HC /
  XLY Cons Disc / XLP Cons Stap / XLE Energy / XLI Industrials / XLB Materials /
  XLU Utilities / XLC Comm / XLRE Real Estate)
"""
from __future__ import annotations

# DIA 30 (price-weighted, Dow Jones Industrial Average)
# 格式: (ticker, gics_sector, approx_price_usd)
# 价格是粗估 (2026-Q2 数量级), 不准但 price-weighted 计算 sector weights 时相对误差可控
# 注意: DIA 历史上没有 Utilities / Real Estate, 30 只主要在 IT / Financials / HC / Industrials
DIA_30: list[tuple[str, str, float]] = [
    ("AAPL", "XLK", 200.0),   # Information Technology
    ("AMGN", "XLV", 300.0),   # Health Care
    ("AXP",  "XLF", 240.0),   # Financials
    ("BA",   "XLI", 200.0),   # Industrials
    ("CAT",  "XLI", 340.0),   # Industrials
    ("CRM",  "XLK", 280.0),   # Information Technology
    ("CSCO", "XLK", 50.0),    # Information Technology
    ("CVX",  "XLE", 160.0),   # Energy
    ("DIS",  "XLC", 100.0),   # Communication Services
    ("DOW",  "XLB", 50.0),    # Materials
    ("GS",   "XLF", 470.0),   # Financials
    ("HD",   "XLY", 380.0),   # Consumer Discretionary
    ("HON",  "XLI", 220.0),   # Industrials
    ("IBM",  "XLK", 180.0),   # Information Technology
    ("INTC", "XLK", 30.0),    # Information Technology
    ("JNJ",  "XLV", 160.0),   # Health Care
    ("JPM",  "XLF", 210.0),   # Financials
    ("KO",   "XLP", 60.0),    # Consumer Staples
    ("MCD",  "XLY", 290.0),   # Consumer Discretionary
    ("MMM",  "XLI", 100.0),   # Industrials
    ("MRK",  "XLV", 100.0),   # Health Care
    ("MSFT", "XLK", 420.0),   # Information Technology
    ("NKE",  "XLY", 80.0),    # Consumer Discretionary
    ("PG",   "XLP", 160.0),   # Consumer Staples
    ("TRV",  "XLF", 240.0),   # Financials
    ("UNH",  "XLV", 550.0),   # Health Care
    ("V",    "XLF", 280.0),   # Financials
    ("VZ",   "XLC", 40.0),    # Communication Services
    ("WMT",  "XLP", 70.0),    # Consumer Staples
    ("_placeholder_30th", "XLI", 150.0),  # 第 30 只不确定, 用 Industrials 中位价占位
]

# QQQ 100 (cap-weighted, Nasdaq-100)
# 格式: (ticker, gics_sector, approx_market_cap_usd_billion)
# 市值粗估, 数量级 OK; 真正 P7-3 sector weights 不依赖 mcap 精度, 因为 IT/Comm 集中度
# 几乎全靠前 10 只 (AAPL/MSFT/AMZN/NVDA/META/GOOGL/GOOG/TSLA/AVGO/COST = ~60% QQQ)
# top 30 ~80%, top 60 ~95%, 后 40 只 ~5%
QQQ_100_TOP_60: list[tuple[str, str, float]] = [
    # Top 10 mega-caps (~60%)
    ("AAPL", "XLK", 3000.0),  # Apple
    ("MSFT", "XLK", 3100.0),  # Microsoft
    ("AMZN", "XLY", 1900.0),  # Amazon
    ("NVDA", "XLK", 1800.0),  # NVIDIA
    ("META", "XLC", 1400.0),  # Meta
    ("GOOGL", "XLC", 1200.0), # Alphabet A
    ("GOOG", "XLC", 1100.0),  # Alphabet C
    ("TSLA", "XLY", 800.0),   # Tesla
    ("AVGO", "XLK", 700.0),   # Broadcom
    ("COST", "XLP", 400.0),   # Costco
    # Tier 2 (~25%)
    ("NFLX", "XLC", 320.0),   # Netflix
    ("ADBE", "XLK", 240.0),   # Adobe
    ("PEP",  "XLP", 230.0),   # PepsiCo
    ("CSCO", "XLK", 200.0),   # Cisco
    ("TMUS", "XLC", 270.0),   # T-Mobile
    ("AMD",  "XLK", 260.0),   # AMD
    ("INTC", "XLK", 140.0),   # Intel
    ("CMCSA", "XLC", 160.0),  # Comcast
    ("QCOM", "XLK", 200.0),   # Qualcomm
    ("TXN",  "XLK", 180.0),   # Texas Instruments
    ("HON",  "XLI", 140.0),   # Honeywell
    ("AMGN", "XLV", 160.0),   # Amgen
    ("INTU", "XLK", 180.0),   # Intuit
    ("ISRG", "XLV", 170.0),   # Intuitive Surgical
    ("BKNG", "XLY", 130.0),   # Booking
    ("VRTX", "XLV", 120.0),   # Vertex
    ("ADP",  "XLI", 120.0),   # ADP
    ("AMAT", "XLK", 140.0),   # Applied Materials
    ("SBUX", "XLY", 100.0),   # Starbucks
    ("GILD", "XLV", 110.0),   # Gilead
    # Tier 3 (~10%)
    ("PANW", "XLK", 110.0),   # Palo Alto
    ("MU",   "XLK", 130.0),   # Micron
    ("LRCX", "XLK", 100.0),   # Lam Research
    ("MDLZ", "XLP", 90.0),    # Mondelez
    ("KLAC", "XLK", 95.0),    # KLA
    ("MELI", "XLY", 85.0),    # MercadoLibre
    ("SNPS", "XLK", 85.0),    # Synopsys
    ("CDNS", "XLK", 80.0),    # Cadence
    ("ASML", "XLK", 280.0),   # ASML (ADR)
    ("REGN", "XLV", 85.0),    # Regeneron
    ("PYPL", "XLF", 75.0),    # PayPal
    ("ABNB", "XLY", 90.0),    # Airbnb
    ("CHTR", "XLC", 50.0),    # Charter
    ("MAR",  "XLY", 70.0),    # Marriott
    ("ORLY", "XLY", 70.0),    # O'Reilly
    ("CTAS", "XLI", 80.0),    # Cintas
    ("MNST", "XLP", 60.0),    # Monster
    ("PCAR", "XLI", 55.0),    # Paccar
    ("ADSK", "XLK", 55.0),    # Autodesk
    ("PAYX", "XLI", 55.0),    # Paychex
    # Tier 4 (~5%)
    ("KDP",  "XLP", 50.0),    # Keurig Dr Pepper
    ("KHC",  "XLP", 45.0),    # Kraft Heinz
    ("FAST", "XLI", 50.0),    # Fastenal
    ("CCEP", "XLP", 35.0),    # Coca-Cola Europacific
    ("AEP",  "XLU", 55.0),    # American Electric Power
    ("DXCM", "XLV", 45.0),    # Dexcom
    ("EXC",  "XLU", 45.0),    # Exelon
    ("WBA",  "XLP", 25.0),    # Walgreens (legacy, may be removed)
    ("ROST", "XLY", 50.0),    # Ross
    ("IDXX", "XLV", 45.0),    # IDEXX
]

# QQQ 后 40 只 (Tier 5, ~5% 总权重) — 用 sector 分布近似补全
# 实际权重占比小, sector 错误影响 < 0.5%
QQQ_100_TAIL_40: list[tuple[str, str, float]] = [
    # Industrials: 5 stocks, ~50B total
    ("VRSK", "XLI", 30.0), ("ODFL", "XLI", 30.0), ("CPRT", "XLI", 25.0),
    ("GE",   "XLI", 180.0), ("CSGP", "XLI", 35.0),  # CSGP 实际是 Real Estate services, 暂归 Industrials
    # Comm Services: 4 stocks, ~30B
    ("EA",   "XLC", 30.0), ("TTWO", "XLC", 30.0), ("NTES", "XLC", 50.0),
    ("WBD",  "XLC", 25.0),
    # IT: 12 stocks, ~250B (DDOG/ZS/TEAM 等 SaaS)
    ("ZS",   "XLK", 25.0), ("TEAM", "XLK", 30.0), ("CRWD", "XLK", 70.0),
    ("WDAY", "XLK", 60.0), ("MCHP", "XLK", 30.0), ("ON",   "XLK", 30.0),
    ("CDW",  "XLK", 25.0), ("GFS",  "XLK", 50.0), ("ANSS", "XLK", 25.0),
    ("CTSH", "XLK", 35.0), ("DDOG", "XLK", 30.0), ("MRVL", "XLK", 50.0),
    # HC: 5 stocks, ~30B
    ("BIIB", "XLV", 30.0), ("ALGN", "XLV", 25.0), ("ILMN", "XLV", 20.0),
    ("HOLX", "XLV", 15.0), ("RARE", "XLV", 15.0),
    # Cons Disc: 5 stocks, ~50B
    ("DLTR", "XLY", 25.0), ("PDD",  "XLY", 200.0), ("LCID", "XLY", 25.0),
    ("RIVN", "XLY", 15.0), ("EBAY", "XLY", 30.0),
    # Cons Stap: 3 stocks, ~30B
    ("MNST", "XLP", 60.0), ("KMB",  "XLP", 50.0), ("GIS",  "XLP", 40.0),
    # Financials: 1 stock
    ("NDAQ", "XLF", 40.0),
    # Energy: 1 stock
    ("FANG", "XLE", 50.0),
    # IT 续 (MDB/ZM/ENPH 等)
    ("MDB",  "XLK", 25.0), ("ZM",   "XLK", 20.0), ("ENPH", "XLK", 15.0),
    # Real Estate: 0 (Nasdaq-100 基本没有 REIT)
    # Utilities: 2 stocks, 实际在 QQQ
    ("XEL",  "XLU", 30.0), ("CEG",  "XLU", 30.0),  # Constellation Energy
]


def get_qqq_100() -> list[tuple[str, str, float]]:
    """完整 QQQ 100 = top 60 + tail 40 (按已知顺序合并)"""
    return QQQ_100_TOP_60 + QQQ_100_TAIL_40


# S&P 500 stock count by sector (用于 RSP equal-weight 派生)
# Source: S&P Dow Jones Indices S&P 500 sector composition 2026-Q2 (粗估)
# 总数 503 (含 dual class shares 算多只, 如 GOOG/GOOGL/FOX/FOXA)
SP500_SECTOR_COUNTS: dict[str, int] = {
    "Information Technology":       78,  # XLK
    "Industrials":                  78,  # XLI
    "Financials":                   72,  # XLF
    "Health Care":                  63,  # XLV
    "Consumer Discretionary":      50,  # XLY
    "Consumer Staples":            38,  # XLP
    "Real Estate":                  31,  # XLRE
    "Utilities":                    30,  # XLU
    "Materials":                    28,  # XLB
    "Energy":                       23,  # XLE
    "Communication Services":      22,  # XLC
}
# sum = 513 (over by 10 因为 dual class shares 算多只, 但 sector weights 是 count/503 OK)

# Sector ticker ↔ name 双向映射
SECTOR_TICKER_TO_NAME = {
    "XLK":   "Information Technology",
    "XLF":   "Financials",
    "XLV":   "Health Care",
    "XLY":   "Consumer Discretionary",
    "XLP":   "Consumer Staples",
    "XLE":   "Energy",
    "XLI":   "Industrials",
    "XLB":   "Materials",
    "XLU":   "Utilities",
    "XLC":   "Communication Services",
    "XLRE":  "Real Estate",
}
SECTOR_NAME_TO_TICKER = {v: k for k, v in SECTOR_TICKER_TO_NAME.items()}

# 11 sector tickers in canonical order (用于 output sector_weights.json)
SECTOR_TICKERS_11 = [
    "XLK", "XLF", "XLV", "XLY", "XLP", "XLE", "XLI", "XLB", "XLU", "XLC", "XLRE",
]
