# API key 安全 (R7 audit)

跨 project 公共 API key 安全模式,跟 paper-agent 经验一致。

## Key 存储矩阵

| Key 类型 | 存储位置 | 不入 git? | 跨 project? | 申请链接 |
|---|---|---|---|---|
| **FRED API** | `~/.fred_key` (32 hex chars) | ✅ | ✅ | https://fred.stlouisfed.org/docs/api/api_key.html |
| **SEC EDGAR** | 0 key (公开) | N/A | N/A | https://www.sec.gov/cgi-bin/browse-edgar |
| **Longbridge** (kansoku) | user home 加密 | ✅ | ❌ (kansoku only) | https://open.longbridge.com |
| **Zotero** (paper-agent) | `$ZOTERO_API_KEY` env var | ✅ | ❌ (paper-agent only) | https://www.zotero.org/settings/keys |
| **GitHub PAT** (paper-agent) | `~/.gh_token` + git credential | ✅ | ❌ (paper-agent only) | https://github.com/settings/tokens |

## FRED key 安全 SOP (us-stock-causal 主用)

### 一次性申请 (5 分钟)
1. https://fred.stlouisfed.org/docs/api/api_key.html
2. 填 application 描述 (hobbyist, non-commercial, 5 req/day)
3. 勾 agree, Request API Key
4. 页面显示 32 字符 hex key + email 备份

### 存到 ~/.fred_key
```powershell
# PowerShell
$key | Set-Content -Path "$env:USERPROFILE\.fred_key" -NoNewline -Encoding ASCII
```

### Python 读
```python
from pathlib import Path
import os

def _get_fred_key() -> str:
    """读 FRED API key (跨 project 优先 ~/.fred_key, 然后 env var)"""
    home_key = Path.home() / ".fred_key"
    if home_key.exists():
        return home_key.read_text().strip()
    key = os.environ.get("FRED_API_KEY", "").strip()
    if not key:
        raise FileNotFoundError(
            "FRED key 不存在: 申请 https://fred.stlouisfed.org/docs/api/api_key.html, "
            "存到 ~/.fred_key 或 $env:FRED_API_KEY"
        )
    return key
```

### 验证 key 工作
```powershell
$env:FRED_API_KEY = (Get-Content "$env:USERPROFILE\.fred_key")
$url = "https://api.stlouisfed.org/fred/series/observations?series_id=UNRATE&api_key=$env:FRED_API_KEY&file_type=json&limit=3"
(Invoke-WebRequest -Uri $url -UseBasicParsing).Content
```
期望: 200 OK + JSON 含 UNRATE 数据。

### 不入 git 验证
```powershell
git ls-files | Select-String -Pattern "fred_key"  # 期望 0 hits
git check-ignore -v $env:USERPROFILE\.fred_key  # 期望 ignored (在 home, 不在 repo)
```

## SEC EDGAR (0 key, 公开)

SEC EDGAR companyfacts API 不需 key, 但有限速:
- < 10 req/s 官方限速
- 我们设 2 req/s (paper-agent 经验)
- 0.5s/req 间隔 → `tenacity` 装饰器
- User-Agent 必填 (否则 403), mavis sec-fetch 默认 `Mavis Equity Research research@minimax.com`

## Anti-pattern (禁止)

- ❌ Key 写到 project 根目录 `.fred_key` (即使 gitignore 也不安全)
- ❌ Key 写到代码注释 (即使不编译也不安全)
- ❌ Key 每次 input (每次问 user, 烦)
- ❌ Key 入 git 历史 (即使后续删, git log 仍可见)
- ✅ `~/.fred_key` + PowerShell Set-Content (一次性, 跨 project, 永久)
- ✅ Project 读 `Path.home() / ".fred_key"` (跨 project, 自动找)
- ✅ R4 CI 跑 grep 验证 0 key 泄漏

## R7 audit 检查项

- [x] ~/.fred_key 不在 git repo (R1 .gitignore + grep)
- [x] FRED key 32 bytes ASCII no newline (R1 验证)
- [x] FRED API 5 series 200 OK (8/18 验证)
- [x] Paper-agent `~/.cache/sec_fetch/` 跨 project 共享
- [x] Paper-agent `~/.gh_token` 跨 project 共享 (但 user-side)
- [x] FRED key 跟 `~/.cache/sec_fetch/` 并存, 不冲突

## R7 audit scope (2026-08-18)

- 1 key 申请 (FRED, 5 分钟)
- 1 key 存 (32 bytes, ~/.fred_key)
- 5 series 验证 (CPI / UNRATE / INDPRO / T10Y2Y / DFF)
- 跨 project 模式 agent memory 写入 (跟 paper-agent 经验一致)
- 9/3 v0.9.5 RC1 实施 FRED 时用 (tools/fred_fetch.py + examples/fred_macro_report.py)
