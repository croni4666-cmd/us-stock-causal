# Pre-push hygiene

2026-08的R6审计是历史记录，下面的检查需在当前版本重新执行。`.gitignore`不会取消已跟踪文件；用`git ls-files`核对，公开缓存不等于测试夹具。

R1 隐私审计标准 + R6 pre-push hygiene 跟 R4 CI 集成。

## 检查项

每次 `git commit` / `git push` 跑:

1. **R1 隐私 grep** — 0 hits for personal info
2. **GitHub 同步** — push 前确保 main / master branch 是 local 最先
3. **敏感文件** — 不入 git:
   - `~/.fred_key` (FRED API key, 跨 project 存 user home)
   - `~/.cache/sec_fetch/` (paper-agent 共享 cache)
   - `.env` / `.env.local` / `*.pem` / `*.key`
4. **路径硬编码** — 不用 `C:\Users\<name>\` 模式, 用 `Path.home()` 相对
5. **License 标注** — 借鉴 / 复制代码段加 license 头
6. **依赖版本** — 新增 dep 加 requirements.txt (>=) + requirements-lock.txt (==)

## 1 行 pre-push 脚本

```powershell
# 1) R1 grep (PowerShell 敏感信息与私钥检测)
$tracked = git ls-files
$inspect = $tracked | Where-Object { $_ -match '\.(py|md|json|ya?ml|cmd|ps1)$' }
$hits = $inspect | ForEach-Object { Select-String -LiteralPath $_ -Pattern '-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----|sk-[a-zA-Z0-9]{20,}' }
if ($hits.Count -gt 0) { Write-Host "[FAIL] R1 privacy hits:" $hits.Count; exit 1 } else { Write-Host "[OK] R1 0 hits" }

# 2) Key 不入 git
$sensitive = git diff --cached --name-only | Select-String -Pattern '(^|/)\.fred_key$|(^|/)\.env(\.|$)|\.(pem|key)$'
if ($sensitive) { Write-Host "[FAIL] Key file in commit"; exit 1 }

# 3) License 头 (src/ examples/ tests/ 顶部)
foreach ($f in (Get-ChildItem src, examples, tests -Recurse -Include '*.py')) {
    $head = Get-Content $f.FullName -TotalCount 3
    if ($head -notmatch 'License|MIT|Apache|GPL') { Write-Host "[WARN] no license header:" $f.Name }
}
```

## R4 CI 集成

`.github/workflows/test.yml` 自动跑 R1 grep + R6 hygiene:
- 0 hits 时 CI pass
- 1+ hits 时 CI fail (block PR merge)

## 已知豁免

| 豁免 | 原因 |
|---|---|
| `commit_msg_*.txt` | 临时文件应保持未跟踪；ignore不能取消已跟踪状态 |
| `output/_*.txt` | debug / untracked 文件, R1 .gitignore 已 ignore |
| `paper-agent / mavis skill` | 跨 project 引用, MIT 协议, 借鉴 OK |
| `data/cache/*` | 先区分可重建下载与唯一历史权重；仅忽略明确的运行缓存 |

## 已知失败

- ⚠️ `tools/sec_fetch.py` 复制自 mavis skill, GBK 编码 (cosmetic, 不影响功能)
- 依赖声明同时存在于pyproject.toml、requirements.txt和requirements-lock.txt；新增依赖需保持一致。

## R6 audit scope (2026-08-18)

- 4 commits (R1 + R2 + R3 + R4) 跑过 R1 grep 0 hits 验证
- 历史检查未命中所用模式；这不保证覆盖所有凭证或个人信息。
- 0 路径硬编码 user 名跨 source code
- 1 cosmetic issue (sec_fetch.py GBK 编码, 不影响功能, R10 跟 R1 不冲突)


## 当前可执行发布门（2026-10-08）

按顺序执行：`python tools/quality_gate.py`、`python -m ruff check src examples tools scripts tests archive setup.py --select E9,F63,F7,F82`、两运行版本的完整pytest、`python tools/verify_package.py`，再检查待提交差异/敏感文件与当前提交的GitHub结果。安全与依赖审计记录于[全量审查](full-audit-20261008.md)。pre-commit的Black/isort等全格式化钩子是独立风格流程；本次发布门未宣称这些旧风格债务全部通过。
