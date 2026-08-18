# Pre-push hygiene (R6 audit)

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
# 1) R1 grep (PowerShell)
$hits = Select-String -Path . -Pattern 'project-user|USER_LOCATION|USER_LOCATION东方|USER_LOCATIONUSER_INSTITUTION|USER_INSTITUTION|project-user@gmail|@gmail\.com|C:\\Users\\project-user' -Recurse -Include '*.py','*.md','*.json','*.yaml','*.cmd' -ErrorAction SilentlyContinue
if ($hits.Count -gt 0) { Write-Host "[FAIL] R1 privacy hits:" $hits.Count; exit 1 } else { Write-Host "[OK] R1 0 hits" }

# 2) Key 不入 git
git diff --cached --name-only | Select-String -Pattern '\.fred_key|sec_fetch.*\.json'
if ($LASTEXITCODE -eq 0) { Write-Host "[FAIL] Key file in commit"; exit 1 }

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
| `commit_msg_*.txt` | git commit -F 临时文件, .gitignore 已 ignore |
| `output/_*.txt` | debug / untracked 文件, R1 .gitignore 已 ignore |
| `paper-agent / mavis skill` | 跨 project 引用, MIT 协议, 借鉴 OK |
| `data/cache/*` | regenerable, .gitignore 已 ignore |

## 已知失败

- ⚠️ `tools/sec_fetch.py` 复制自 mavis skill, GBK 编码 (cosmetic, 不影响功能)
- ⚠️ R3 dependencies 没 pyproject.toml (传统 requirements.txt 够用, v1.0 后再升级)

## R6 audit scope (2026-08-18)

- 4 commits (R1 + R2 + R3 + R4) 跑过 R1 grep 0 hits 验证
- 0 隐私泄漏跨 src/ examples/ tests/ docs/ .github/
- 0 路径硬编码 user 名跨 source code
- 1 cosmetic issue (sec_fetch.py GBK 编码, 不影响功能, R10 跟 R1 不冲突)
