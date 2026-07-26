"""
examples/feishu_push.py - 飞书 webhook 推送 (Phase 5 P5-1/P5-2)

**v0.5.1 默认不自动跑**(违反 hobbyist ceiling + v1 教训)
**用户必须**:
  1. 创建飞书机器人,获取 webhook URL
  2. 写到 .env: FEISHU_WEBHOOK_URL=https://open.feishu.cn/.../...
  3. 手动跑一次: python examples/feishu_push.py --date 2026-07-13
  4. 飞书收到,确认 OK
  5. (可选) 注册 cron: mavis cron add us-stock-daily ...

推送内容:
  - 5 段报告 (markdown) — 转飞书富文本
  - K 线图 (PNG) — 作为图片附件
  - 顶部情绪 1 行 (VIX/10Y/DXY + 4 指数)

注意:
  - 飞书 webhook 限制: 单消息 < 30KB, 图片 < 10MB
  - 5 段报告 ~2400 字,转富文本 ~6KB,在限制内
  - K 线图 ~100KB,**超 10MB 限制**
  - K 线图 push 用法: 先上传到 OSS 拿 URL,再发链接 (本脚本只演示文字部分)
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import requests
from loguru import logger

from src import proxy  # noqa: F401
from src.report import render_full_report
from src.macro import topline


def load_webhook_url() -> str:
    """从 .env 读 FEISHU_WEBHOOK_URL"""
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            if key.strip() == "FEISHU_WEBHOOK_URL":
                return val.strip().strip('"').strip("'")
    return os.environ.get("FEISHU_WEBHOOK_URL", "")


def build_feishu_card(date_str: str, full_report: str, topline_str: str) -> dict:
    """构建飞书 interactive card 消息"""
    # 飞书 card 格式
    # 简化: text 元素 + 顶部情绪 header
    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "template": "blue",
                "title": {
                    "tag": "plain_text",
                    "content": f"📊 us-stock-causal 日报 — {date_str}",
                },
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": topline_str,
                    },
                },
                {"tag": "hr"},
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        # full_report 转 markdown 会有 ## 标题,飞书 lark_md 支持
                        "content": full_report[:25000],  # 飞书单消息限制 ~30KB
                    },
                },
                {"tag": "hr"},
                {
                    "tag": "note",
                    "elements": [
                        {
                            "tag": "plain_text",
                            "content": "🤖 自动生成 · us-stock-causal v0.5.1 · 不构成投资建议",
                        }
                    ],
                },
            ],
        },
    }


def send_to_feishu(webhook_url: str, payload: dict) -> bool:
    """POST 到飞书 webhook"""
    try:
        r = requests.post(webhook_url, json=payload, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data.get("code", -1) == 0 or data.get("StatusCode", -1) == 0:
                logger.info("[feishu] 推送成功")
                return True
            else:
                logger.error(f"[feishu] 推送失败: {data}")
                return False
        else:
            logger.error(f"[feishu] HTTP {r.status_code}: {r.text[:200]}")
            return False
    except Exception as e:
        logger.error(f"[feishu] 网络错误: {e}")
        return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="推送 5 段报告到飞书 webhook (Phase 5)"
    )
    parser.add_argument("--date", default="today", help="报告日期 (YYYY-MM-DD 或 'today')")
    parser.add_argument("--webhook", default=None, help="飞书 webhook URL (默认从 .env 读)")
    parser.add_argument("--dry-run", action="store_true", help="只打印 payload 不真发")
    args = parser.parse_args()

    print("=" * 72)
    print(f"us-stock-causal v0.5.1 - 飞书推送 (Phase 5 P5-2 manual test)")
    print("=" * 72)

    # 1. 拿 webhook URL
    webhook = args.webhook or load_webhook_url()
    if not webhook and not args.dry_run:
        print(f"\n❌ 找不到 FEISHU_WEBHOOK_URL")
        print(f"   配置方法:")
        print(f"   1. 创建飞书机器人 (群设置 → 群机器人 → 添加 → 自定义 webhook)")
        print(f"   2. 复制 webhook URL")
        print(f"   3. 写到 {PROJECT_ROOT}/.env:")
        print(f"      FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/...")
        print(f"   4. 跑: python examples/feishu_push.py --dry-run   (先看 payload)")
        print(f"      跑: python examples/feishu_push.py             (真发)")
        return 1
    if webhook:
        print(f"Webhook: {webhook[:50]}...{webhook[-10:]}")

    # 2. 生成报告
    from datetime import date as date_cls
    report_date = date_cls.today().isoformat() if args.date == "today" else args.date
    print(f"Report date: {report_date}")

    full_report = render_full_report(["DIA", "QQQ", "RSP", "QQQE"])
    topline_str = topline()

    # 3. 构建飞书 card
    payload = build_feishu_card(report_date, full_report, topline_str)

    # 4. 打印 / 推送
    if args.dry_run:
        print(f"\n=== DRY RUN — payload (前 500 字符) ===")
        import json
        s = json.dumps(payload, ensure_ascii=False, indent=2)
        print(s[:500])
        print(f"... (总 {len(s)} 字符)")
        print(f"\n✅ Dry run 完成,没真发")
        return 0

    if not webhook:
        return 1

    print(f"\n正在推送...")
    ok = send_to_feishu(webhook, payload)
    if ok:
        print(f"✅ 推送成功!去飞书看")
    else:
        print(f"❌ 推送失败,看 log")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
