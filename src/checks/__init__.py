"""src/checks/__init__.py - Phase 8 (v0.6.8n) 5 类异常检测

每个 check 返回 list[alert_dict] (alert_logger.make_alert 构造)
统一从 src.checks.{stale|residual|vix_spike|ticker_fail|parquet_corrupt} import check
"""
from . import stale, residual, vix_spike, ticker_fail, parquet_corrupt

__all__ = ["stale", "residual", "vix_spike", "ticker_fail", "parquet_corrupt"]
