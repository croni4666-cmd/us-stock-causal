# 第二阶段执行账本

Spec: ../specs/2026-10-03-asset-data-pipeline-design.md

Base: 45ea623c1fcb1d97a191f631d1d129e930f6e9e5; branch feat/asset-specific-attribution; reuse isolated clone and draft PR8.

Global constraints: explicit network only; caller-rooted files; no future weights or filled prices; provider capture times are not historical publication evidence; no causal or certified tradable backtest claims; preserve all first-phase tests.

1. Market snapshots and corporate actions: write failing contract tests, implement immutable store/selection/capture and event summaries, verify targeted tests.
2. Collection and inventory: write failing CLI tests, implement source/market collection with partial failure manifests, expose inventory and offline report market-store option.
3. Daily QQQ reconstruction: failing missing-day/wealth-link tests, implement exact-day holdings gate and integrate JSON/Markdown report.
4. Genuine validation and delivery: execute new collection against actual providers, report outputs and failures, run both Python test matrices, one independent final review, fix evidence-backed defects, update existing PR8 and verify current-head CI.

Pre-flight: Task1 produces validated market frames and provenance consumed by Tasks2/3; Task2 must not normalize away snapshot availability. Task3 reads exact observation dates and source dates, not collection dates. Interfaces consistent.

Ruling: user has accepted the asset-specific roadmap and requested continued implementation; proceed inline without asking again. Manual collection is authorized; scheduling is outside this request.

Task 1: complete — market/event contracts RED (missing module and behavioral gate failures) → GREEN. Capture versions, exact endpoints, hash/metadata corruption, timezone/cutoff, and same-session unclosed quotes verified.

Task 2: complete — missing collection module RED → GREEN; partial failures persist successful data and manifest, inventory separates versions from dates, offline reports select store exclusively. Real default collect4+11 and optional collect4+112 both successful.

Task 3: complete — missing daily model RED → GREEN; exact daily weights, sessions, uncovered stocks and wealth linkage verified. Genuine reporting exposed a gap-diagnostic omission when all available weights were newer than report end; new regression observed RED, moving diagnostics before current-profile gate restored GREEN. Final focused set39 passed.

Task 4 local validation: complete — four genuine report scenarios asserted; rebuilt wheel installed into an isolated target and new offline CLI/module origins verified; source/hash/count summaries recorded for4 official/112 histories. Final Python3.11/3.12 suites each226 passed/3 explicitly live integration skipped/11 warnings; final targeted44 passed. One fresh independent review completed; both P2 findings reproduced and fixed. Publication uses existing draft PR8; current-head GitHub CI confirmation is recorded in PR description/Checks and the authoritative external project progress ledger.

Ruling: use exchange session close guard for US securities and conservative17:00 New York guard for continuous gold quote; prevent intraday bars from posing as completed daily observations. These clocks do not assert original provider publication or final revision times.

Final independent reviewer identified two P2 defects: whole-report stock endpoint selection excluded valid new-stock daily intervals; missing interior event sessions could present zero cash totals. Both reproduced RED with three regressions, corrected per-interval stock reader/report cutoff and event date coverage, then42 focused tests GREEN. Root follow-up found dot-only snapshot symbol paths resolving to root/parent; two regressions RED, rejection and period encoding added. Final focused44 checks and226-test matrices passed. No Critical/P1 findings reported.

Packaging ruling: direct zip import of a namespace-package wheel fell back to the checkout, so it was not accepted as package verification. Install wheel into an isolated workspace target, remove checkout path, assert module __file__ points to that target, then run offline CLI. That verification passed; rebuild/install after final source fixes before delivery.
