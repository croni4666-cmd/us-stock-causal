"""P7-3 派生后残差对比: v0.6.7 / v0.6.8e / v0.6.8f (P7-3)"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.attribution import attribute_index

print("P7-3 (v0.6.8f) 派生后残差")
print("=" * 80)
for idx in ['DIA', 'QQQ', 'RSP', 'QQQE']:
    print(f'\n--- {idx} ---')
    for lb in [1, 5, 20]:
        try:
            r = attribute_index(idx, lookback_days=lb, date='2026-07-15')
            act = r['actual_return_pct']
            pred = r['predicted_return_pct']
            res = r['residual_pct']
            print(f'  {lb:2d}d: actual={act:+6.3f}%  predicted={pred:+6.3f}%  residual={res:+6.3f}%')
        except Exception as e:
            print(f'  {lb:2d}d: ERROR {e}')
