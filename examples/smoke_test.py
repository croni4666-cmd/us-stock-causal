"""OpenBB smoke test - 1 ticker via Clash proxy"""
import os
os.environ['HTTP_PROXY'] = 'http://127.0.0.1:7897'
os.environ['HTTPS_PROXY'] = 'http://127.0.0.1:7897'

from openbb import obb

result = obb.equity.price.historical(
    symbol='AAPL',
    start_date='2026-06-01',
    end_date='2026-07-10',
    provider='yfinance',
)
df = result.to_dataframe()
print(f'OK: {len(df)} rows')
print(f'columns: {list(df.columns)[:8]}')
print(f'date range: {df.index[0].date()} -> {df.index[-1].date()}')
print(f'latest close: {df["close"].iloc[-1]:.2f}')
