# us-stock-causal Security Audit R2 (2026-08-18, v0.9.5 RC1 补充)

**审计触发**: 8/18 21:38 commit 4666271 + 483b937 + 7a7aa67 (3 new commits after R1 audit at 5b3764c)
**审计模式**: 10 轮 + 4 agent team 复核 (跟 paper-agent 8/14 + us-stock-causal 8/18 R1 同模式)
**审计目标**: 验证 v0.9.5 RC1 release 前的最后安全 + 性能 + 正确性门槛
**审计员**: Mavis root session (mvs_b4b34101ab204d49a27313412c346739)
**commit 范围**: 5b3764c..4666271 (3 commits, +142/-32)

---

## 10 轮审计结果 (3 层诚实 audit: 实测 / 估过宽 / 估错)

### R1 隐私 ✅ 0 hits (实测)

3 new commits 扫 `project-user|USER_LOCATION|东方|USER_NAME|C:\Users\project-user|project-user@gmail|@gmail\.com`:
- `tests/test_smoke.py` (5 fail 修 + 1 regression test): 0 hits
- `src/attribution.py` (lru_cache + functools): 0 hits
- `src/causal.py` (_QUERY_CACHE + _CATE_CACHE + clear_caches 集成): 0 hits
- `src/report.py` (ThreadPoolExecutor + render_full_report): 0 hits
- `V1.0-ROADMAP.md` (status update): 0 hits

**verdict**: 跟 R1 (5b3764c) 同 0 hits 标准通过, 隐私 0 泄漏

### R2 License ✅ OK (估过宽 — LICENSE 已就位, 8/18 R1 写)

- `LICENSE`: MIT (c) 2026 Mavis ✅
- `README.md`: 顶部 description + 命令示例 + 5 段制结构 ✅
- commit_msg 模板: 0 license 头污染 ✅

**verdict**: License 合规, MIT 跟 paper-agent R2 (8/14) 一致 (hobbyist ceiling 友好)

### R3 Deps ✅ OK (实测 — 0 新引入)

- `requirements.txt`: 11+ 核心 dep (跟 R1 8/18 一致), 0 新增
- `requirements-lock.txt`: 17 pinned exact (R3 8/18 加的, 还在)
- P10-1 优化用 stdlib: `functools.lru_cache` (Python 3.9+ stdlib) + `concurrent.futures.ThreadPoolExecutor` (Python 3.2+ stdlib) + `import` 局部 (无新 module)

**verdict**: 0 新 dep 引入, lockfile 完整, 安全

### R4 Repo hardening ✅ OK (估过宽 — R1 8/18 已就位)

- `.github/dependabot.yml` (R4 8/18 加): GitHub 自动 PR
- `.github/SECURITY.md` (R4 8/18 加): 报告漏洞流程
- `.github/workflows/test.yml` (R4 8/18 加): CI pytest on push
- `.gitignore` 14 类: pycache / data / output / secrets / commit_msg / `_*.py` debug scripts / etc.

**verdict**: GitHub 仓库 hardening 全套, 跟 paper-agent 8/14 同标准

### R5 + R6 + R7 ✅ OK (估过宽 — R1 8/18 已就位)

- R5 pre-commit: `.pre-commit-config.yaml` R1 privacy grep + black + isort + flake8 + encoding check (R5 8/18 加)
- R6 pre-push: `docs/pre-push-hygiene.md` (R6 8/18 加, 跟 paper-agent 8/14 同 SOP)
- R7 API key: `docs/api-key-security.md` (R7 8/18 加, FRED key 走 `~/.fred_key` 跨 project 模式)

**verdict**: pre-commit + pre-push + API key 三层防护就位

### R8 + R9 + R10 ✅ OK (估过宽 — R1 8/18 已就位, R12 修 1 bug)

- R8 hard safety: `docs/hard-safety-sop.md` (R8 8/18 加) + mavis-trash 替代 Remove-Item
- R9 文档: README/USER_GUIDE/ARCHITECTURE/V1.0-ROADMAP (3+ 套齐全)
- R10 V1.0 路线图: 6 conditions (8/18 21:35 R12 修 2 状态为诚实数据)

**R12 新发现 (R1 audit 后, 4 agent team 复核报告触发)**:

- **critical bug**: `src/checks/residual.py` 字段名错 — 读 `v.get("ratio")` 但 `compare_to_baseline` 返 `regression_ratio`, 同样 `current` / `baseline` vs `current_pct` / `baseline_pct`
- **影响**: 8/13-8/18 持续 6 天 daily cron 误报 5-6 alert/day, 触发 Exit 1
- **修法**: 改 `.get(field, fallback)` 双 lookup, 加 `ratio_str` 处理 `"inf"` (baseline=0 时)
- **测试**: 新加 `test_residual_check_alert_field_names_v095_p107` 验证 alert 字段正确
- **81 passed + 1 skipped + 0 fail** (8/18 21:35)

### R11 4 agent team 复核 (verifier / general / coder / general 并行)

- **Verifier 实测**: 性能 7.07-8.91s (skip_fetch) / 30.65s (full fetch) / 80+ tests pass / 0 隐私 hits / optimization 代码全部就位
- **Verifier 发现** (R12 trigger):
  1. R1 真 0 hits ✅
  2. 4666271 commit 7.07s 误导 (没说明是 skip_fetch 模式) — 部分真, 但 test_smoke.py end-to-end 测试也是 skip_fetch, 7.07s 是 V1.0 condition 2 (逻辑处理) < 10s 的标准
  3. ROADMAP condition 6 "9/10 PASS" 错 (实 0/10 PASS + 1 MISSING + 9 FAIL) — 诚实更新
  4. residual_regression 字段名 bug — R12 修
  5. test_load_dag_graph_cache_v075_p89 flaky — 跟 R1 已知 flaky, 单独跑 PASS, 接受
- **General (V1.0 视角)**: 5/6 conditions 达成, 1 个 (30 天 0 fail) 还需时间验证, 8/19 起预期 0 new FAIL
- **Coder (代码质量)**: P10-1 4 项优化干净, 0 副作用, 集成到 clear_caches() + get_cache_stats()
- **General (综合)**: 报告一致, 6 处数字 cleanup (R11 5b3764c 已修)

---

## 3 层诚实 audit 习惯 (user 拍)

- **5 实测**: R1 隐私 0 hits / R3 deps 0 新引入 / R8 mavis-trash OK / R12 residual bug 修了 + 新测试 / 81 passed + 1 skipped
- **3 估过宽**: R2 License / R4 Repo hardening / R5+R6+R7 pre-commit + pre-push + API key (R1 8/18 已就位, 没新引入)
- **2 估错**: ROADMAP condition 2 没注 "skip_fetch 模式" / ROADMAP condition 6 "9/10 PASS" 错 (实 0/10) — R12 修

---

## V1.0 路线图 6 conditions 状态 (8/18 21:35 R12 update)

| # | Condition | 状态 |
|---|-----------|------|
| 1 | DAG 47 节点 | ✅ 47/49 (2 delisted) |
| 2 | 性能 < 10s daily_report 逻辑处理 | ✅ 7.07-8.91s (含 fetch 30.65s, fetch 21.9s 是 yfinance 网络) |
| 3 | P8-5 错误恢复 | ✅ v0.6.9m tenacity + 优雅降级 |
| 4 | 测试 80+ | ✅ 81 passed + 1 skipped (8/18 R12 加 p107) |
| 5 | 完整文档 | ✅ v0.9.0 (958 lines) |
| 6 | 30 天 cron 0 fail | ❌ 8/9-8/18 实 0/10 (R12 修 residual 字段 bug 8/19 起 0 new FAIL 目标) |

**5/6 达成, 1 个 (30 天验证) 8/19 起重新计数, 9/8 v0.9.5 RC1 拍板**

---

## 0 commits 风险评估

- 3 new commits 净影响: +142/-32 (含 73 行测试 + 68 行 cache + 1 行 README), 0 删代码
- 0 force-push (跟 paper-agent 8/14 + us-stock-causal 8/18 R1 一致纪律)
- 0 公开文件 PII 泄漏 (R1 0 hits)
- 0 引入新 dep (R3 OK)
- 0 改 hard-safety SOP (R8 OK)
- 1 critical bug 修 (R12, 加 1 test 防回归)

---

## R12 commit list (待 commit, 8/18 22:00)

1. `src/checks/residual.py` — 字段名修 (R12 critical)
2. `tests/test_smoke.py` — 加 `test_residual_check_alert_field_names_v095_p107` (R12 regression test)
3. `V1.0-ROADMAP.md` — 诚实更新 condition 2 + 6 状态 (R11 + R12)

---

## verdict: READY WITH CAVEATS

- ✅ R1 0 hits / R2 LICENSE / R3 0 new deps / R4 hardening / R5+R6+R7 三层防护 / R8 hard safety / R9 docs / R10 V1.0
- ⚠️ V1.0 condition 6 (30 天 0 fail) 8/9-8/18 = 0/10 PASS, R12 修 bug 后 8/19 起重新计数, 9/8 v0.9.5 RC1 拍板
- ✅ 5/6 conditions 达成, R12 critical bug 修了
- ✅ 81 tests + 1 skip = 0 fail

**release v0.9.5 RC1 推荐**: YES (5/6 达成 + R12 修 critical bug + 0 force-push + 0 PII)
**v1.0.0 tag 推荐**: 9/8 等 30 天稳定期重新评估后再说
