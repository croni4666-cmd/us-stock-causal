"""从硬编码 ETF 成分股派生 sector weights → 写 config/sector_weights.json

P7-3 派生:
- DIA: 从 DIA_30 + 价格算 price-weighted sector weights
- QQQ: 从 QQQ_100 + 市值算 cap-weighted sector weights
- QQQE: 从 QQQ_100 算 equal-weighted (count-based) sector weights
- RSP: 从 S&P 500 行业股票数算 equal-weighted (count-based) sector weights

数据源: data/static/etf_constituents.py (季度手动维护)
"""
from __future__ import annotations
import sys
import json
from pathlib import Path
from collections import defaultdict

# 让脚本能 import project modules
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data.static.etf_constituents import (
    DIA_30,
    get_qqq_100,
    SP500_SECTOR_COUNTS,
    SECTOR_TICKERS_11,
    SECTOR_NAME_TO_TICKER,
)
import config  # noqa: F401  (确保 PROJECT_ROOT 路径可解析)


CONFIG_PATH = ROOT / "config" / "sector_weights.json"


def derive_dia_price_weighted() -> dict[str, float]:
    """DIA = price-weighted (Dow Jones divisor 风格)

    sector weight = sum(price_i for i in sector) / sum(price for all 30)
    """
    total = sum(p for _, _, p in DIA_30)
    by_sector: dict[str, float] = defaultdict(float)
    for _, sector, price in DIA_30:
        by_sector[sector] += price
    weights = {s: round(by_sector.get(s, 0.0) / total, 4) for s in SECTOR_TICKERS_11}
    return weights


def derive_qqq_cap_weighted() -> dict[str, float]:
    """QQQ = cap-weighted (Nasdaq-100)

    sector weight = sum(mcap_i for i in sector) / sum(mcap for all 100)
    """
    constituents = get_qqq_100()
    total = sum(m for _, _, m in constituents)
    by_sector: dict[str, float] = defaultdict(float)
    for _, sector, mcap in constituents:
        by_sector[sector] += mcap
    weights = {s: round(by_sector.get(s, 0.0) / total, 4) for s in SECTOR_TICKERS_11}
    return weights


def derive_qqqe_equal_weighted() -> dict[str, float]:
    """QQQE = equal-weight Nasdaq-100 (Invesco)

    sector weight = count(stocks in sector) / 100
    """
    constituents = get_qqq_100()
    n = len(constituents)
    by_sector: dict[str, int] = defaultdict(int)
    for _, sector, _ in constituents:
        by_sector[sector] += 1
    weights = {s: round(by_sector.get(s, 0) / n, 4) for s in SECTOR_TICKERS_11}
    return weights


def derive_rsp_equal_weighted() -> dict[str, float]:
    """RSP = equal-weight S&P 500

    sector weight = count(S&P 500 stocks in sector) / 503
    (S&P 500 实际是 503 只含 dual class shares 算多只, 用 503 跟 Invesco 公开口径一致)
    """
    total = sum(SP500_SECTOR_COUNTS.values())
    weights = {}
    for sector_name, count in SP500_SECTOR_COUNTS.items():
        ticker = SECTOR_NAME_TO_TICKER[sector_name]
        weights[ticker] = round(count / total, 4)
    # 补齐所有 11 sector (如果有 SP500_SECTOR_COUNTS 漏的, 默认 0)
    for s in SECTOR_TICKERS_11:
        weights.setdefault(s, 0.0)
    return weights


def main():
    dia_w = derive_dia_price_weighted()
    qqq_w = derive_qqq_cap_weighted()
    qqqe_w = derive_qqqe_equal_weighted()
    rsp_w = derive_rsp_equal_weighted()

    out = {
        "_meta": {
            "as_of": "2026-07-23",
            "v068f": "P7-3 done — 从硬编码 ETF 成分股派生 4 指数真 sector weights",
            "source_dia": "data/static/etf_constituents.py DIA_30 (30 成分股 + 估算价格) → price-weighted",
            "source_qqq": "data/static/etf_constituents.py QQQ_100 (100 成分股 + 估算市值) → cap-weighted",
            "source_qqqe": "data/static/etf_constituents.py QQQ_100 → equal-weight (count/100)",
            "source_rsp": "data/static/etf_constituents.py SP500_SECTOR_COUNTS (S&P 500 行业股票数) → equal-weight (count/503)",
            "warning": (
                "DIA 30 / QQQ 100 的成分股 + 价格 / 市值是模型知识 (cutoff 2026-01) + 粗估, "
                "不是实时数据。季度手动维护时, 改 data/static/etf_constituents.py 然后重跑本脚本即可。"
            ),
            "update_cadence": "quarterly (next: 2026-10, 改 etf_constituents.py + 重跑脚本)",
            "sp500_503_basis": "S&P 500 实际 503 只 (含 dual class shares 算多只, 跟 Invesco RSP 公开口径一致)",
            "v068e_kept": "SPY 仍按 v0.6.8e 真值 (从 N-30D table 22 推 11 sector), 见 SPY entry",
        },
        "SPY": {
            "note": "S&P 500 cap-weighted — v0.6.8e SPY 真值保留 (从 N-30D table 22 推 11 sector, 最可靠)",
            "XLK": 0.329, "XLF": 0.125, "XLV": 0.094, "XLC": 0.099, "XLY": 0.093,
            "XLI": 0.068, "XLP": 0.047, "XLE": 0.037, "XLU": 0.024, "XLB": 0.017, "XLRE": 0.008,
        },
        "DIA": {
            "note": "Dow Jones 30 — P7-3 从 DIA_30 + 价格派生 (price-weighted)",
            **dia_w,
        },
        "QQQ": {
            "note": "Nasdaq-100 — P7-3 从 QQQ_100 + 市值派生 (cap-weighted, IT 集中度 ~50%)",
            **qqq_w,
        },
        "RSP": {
            "note": "S&P 500 EQUAL WEIGHT — P7-3 从 S&P 500 sector stock count 派生 (count/503)",
            **rsp_w,
        },
        "QQQE": {
            "note": "Nasdaq-100 EQUAL WEIGHT — P7-3 从 QQQ_100 派生 (count/100)",
            **qqqe_w,
        },
    }

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    print(f"[derive] wrote {CONFIG_PATH}")
    print()
    print("Derived sector weights:")
    for idx in ["DIA", "QQQ", "RSP", "QQQE"]:
        w = out[idx]
        total = sum(v for k, v in w.items() if k in SECTOR_TICKERS_11)
        top3 = sorted(
            ((k, v) for k, v in w.items() if k in SECTOR_TICKERS_11),
            key=lambda x: -x[1]
        )[:3]
        print(f"  {idx:5s}: sum={total:.4f}  top3={top3}")


if __name__ == "__main__":
    main()
