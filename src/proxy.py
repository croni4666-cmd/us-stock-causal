"""
src/proxy.py - HTTP 代理自动探测 (port from us-stock-daily v0.2)

背景: yfinance 直连被 Yahoo 风控(本机 IP 进黑名单)。
Stooq 被 Cloudflare JS PoW 挡住。
用户的 Clash Verge 在跑(127.0.0.1:7897 HTTP / 127.0.0.1:7899 mixed),
通过代理 yfinance 能拉到 1 年数据。
结论: 默认走 Clash 代理,直连作 fallback。

工作原理: urllib / requests 都遵守 HTTP_PROXY / HTTPS_PROXY 环境变量。
本模块在 import 时探测 Clash 端口,如发现就设置 env var,后续所有 HTTP 请求自动走代理。

v3 增强:
  - 修复 v0.2 的 junction 教训(避免 reparse point 误删)
  - 支持 .env 文件读 proxy 配置
"""
from __future__ import annotations

import os
import socket
from pathlib import Path
from typing import Optional

from loguru import logger


# 常见 Clash 端口 (按使用频率排)
CLASH_DEFAULT_PORTS = [7897, 7899, 7890, 7891, 10809, 10808, 1080, 8080, 8888]


def _probe_port(host: str, port: int, timeout: float = 0.5) -> bool:
    """TCP 探测端口是否监听"""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


def _detect_clash_proxy() -> Optional[str]:
    """探测 Clash HTTP 代理,返回 URL 字符串或 None"""
    for port in CLASH_DEFAULT_PORTS:
        if _probe_port("127.0.0.1", port):
            logger.info(f"[proxy] 发现本地代理在 127.0.0.1:{port}")
            return f"http://127.0.0.1:{port}"
    return None


def _parse_proxy_spec(spec: str) -> Optional[str]:
    """
    解析 proxy spec 字符串:
      "auto"           -> 自动探测 Clash
      "off"            -> 禁用代理
      "clash"          -> 探测 Clash
      "clash:7897"     -> 用指定端口
      "http://x:1234"  -> 直接用这个 URL
    """
    spec = spec.strip().lower()
    if spec in ("off", "none", "false", "0", "disable", "disabled"):
        return None
    if spec.startswith(("http://", "https://", "socks5://")):
        return spec
    if spec.startswith("clash"):
        if ":" in spec:
            port = int(spec.split(":", 1)[1])
            if _probe_port("127.0.0.1", port):
                return f"http://127.0.0.1:{port}"
            logger.warning(f"[proxy] 指定端口 {port} 无监听,降级到自动探测")
        return _detect_clash_proxy()
    if spec in ("auto", "true", "1", "enable", "enabled"):
        return _detect_clash_proxy()
    logger.warning(f"[proxy] 无法解析 proxy spec '{spec}',禁用代理")
    return None


def _load_config_proxy() -> str:
    """从 config/proxy.yaml 或 .env 读 proxy spec,默认 'auto'"""
    # 优先级: env var > yaml > .env > "auto"
    if "US_STOCK_PROXY" in os.environ:
        return os.environ["US_STOCK_PROXY"]
    return "auto"


def setup_proxy(spec: Optional[str] = None) -> Optional[str]:
    """
    启动时调用:解析 proxy spec,设置 HTTP_PROXY / HTTPS_PROXY 环境变量。

    Args:
        spec: 显式 spec 字符串,None = 读 env var / .env

    Returns:
        实际使用的代理 URL,或 None (直连)
    """
    if spec is None:
        spec = _load_config_proxy()

    proxy_url = _parse_proxy_spec(spec)
    if proxy_url is None:
        for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
            os.environ.pop(k, None)
        logger.info("[proxy] 代理禁用,直连(注意: yfinance / Stooq 可能有风控)")
        return None

    for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        os.environ[k] = proxy_url
    logger.info(f"[proxy] 已设置 HTTP(S)_PROXY={proxy_url}")
    return proxy_url


def is_proxied() -> bool:
    """检查当前是否在代理下"""
    return bool(os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY"))


# 模块级副作用: import 时就设好
# 注意: 这只对 import 在 openbb / requests 之前有效
_default_proxy: Optional[str] = None
try:
    _default_proxy = setup_proxy()
except Exception as e:
    logger.warning(f"[proxy] 自动探测失败: {e}")


if __name__ == "__main__":
    print(f"Active proxy: {os.environ.get('HTTPS_PROXY', '(none)')}")
    print(f"is_proxied(): {is_proxied()}")
