# Security Policy (R4 audit)

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| v1.0.x  | :white_check_mark: |
| v0.9.x  | :white_check_mark: |
| v0.8.x  | :x:                |
| < v0.8  | :x:                |

## Reporting a Vulnerability

**Email**: open an issue at https://github.com/croni4666-cmd/us-stock-causal/issues
(GitHub repo 待 user push, R4 audit 留痕准备)

**Response time**: 7 days (hobbyist project, best-effort)

**Scope**:
- 真实 SEC EDGAR 财报数据 (mavis `sec-fetch` skill, MIT)
- FRED macro 数据 (公开 API, 需 key, 跨 project 存 `~/.fred_key`)
- Python 代码 + DAG 配置 (us-stock-causal MIT License)
- Cron / Task Scheduler 集成 (Windows 平台)

**Out of scope**:
- yfinance 数据准确性 (第三方, 责任 in yfinance)
- Task Scheduler 误触发 (Windows 系统层)
- user 自行修改的 fork

## Vulnerability Disclosure

我们 follow [responsible disclosure](https://en.wikipedia.org/wiki/Coordinated_vulnerability_disclosure):
1. Reporter 私下联系 (issue / email)
2. 维护者 7 天内确认 + 评估严重度
3. 修复 patch 准备 (在 private fork 测)
4. 修复后 90 天内公开披露
5. 致谢 reporter (如果愿意)

## R4 audit context (2026-08-18)

- 10-round security audit (跟 paper-agent v3.9.13.0 8/14 10-round 同模式)
- R1 隐私: 0 personal info hits (paper-agent 同标准)
- R2 License: MIT (项目 README 顶部 + LICENSE 文件)
- R3 依赖: requirements.txt 23 dep + requirements-lock.txt 24 exact
- R4 Repo hardening: Dependabot + CI + secret scanning 留痕准备
- R5-R10: pre-commit hooks, pre-push hygiene, API key 安全, hard safety, 文档, V1.0 路线图
