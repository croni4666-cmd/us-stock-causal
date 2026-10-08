# 第三阶段执行计划与账本

Spec: ../specs/2026-10-07-treasury-curve-design.md
Base5684e155; reuse feat/asset-specific-attribution and existing draft PR8. User requested continued development on approved roadmap; execute inline.

1. Write failing CSV/source/time contract tests; implement immutable official curve store, explicit capture and exact-date selection in src/treasury_curve.py.
2. Write failing cashflow/flat-par/parallel/nonparallel/coverage tests; implement bond terms reader and pricing in src/treasury_pricing.py. Legacy source schema remains unchanged.
3. Write failing offline report/CLI integration tests; add curve-sync command and optional curve-root to asset report; surface hypotheses and gaps alongside single-tenor model.
4. Genuine capture/repricing, both runtime full tests, one fresh independent whole-feature review, fixes, wheel verification, update PR8 and current-head CI.

Pre-flight: curve layer outputs percent par nodes, pricing layer converts them to experimental discount factors; report consumes contribution and provenance, never replaces causal status. Issuer terms share old raw hash and existing source identity. No new dependencies or scheduler.

Ruling: whole-curve cashflow shock uses fixed starting valuation date, not coupon-inclusive realized return. Retain unmodeled holdings and residual; state issuer rounded coupon precision. Official data availability cannot be guessed from its observation date.

Task1: complete — source tests RED missing module→GREEN11 tests. Fixed official CSV endpoint verified with192 actual2026 rows through10/06; captured raw/hash/time.
Task2: complete — pricing tests RED missing module→GREEN; flat par/zero coupon, off-couponActualActual, parallel and nonparallel nodes, missing terms and EOM/leap checked. Genuine issuer rounding prompted separate coverage/unmodeled/rounding fields rather than negative-cash interpretation.
Task3: complete — four integration tests RED→GREEN; optional report curve model independent of single-tenor proxy, curve-sync explicit, no network on reports. Related final set40 passed.
Task4 local validation: complete — current/historical/strict real reports passed, fixed-date contribution+residual reconciles; rebuilt installed wheel loads new modules and generates genuine offline report. Final3.11/3.12 suites255 passed/3 opt-in skips/11 warnings. One independent review foundP2 upcoming long first coupon admitted; regression RED→GREEN and require dated-date cycle consistency. Exact coupons/settlement/quote clocks remain documented limitations. QQQ latest daily constituent live coverage and publication/current-head CI recorded in authoritative project ledger and PR description.

Ruling: preserve all issuer original weights and label weight gap explicitly as rounding/unknown, not cash. Only dated dates aligned with anchored semiannual cycle are admitted; without first-payment evidence uncertain irregular schedules remain uncovered. No additional whole-branch review loop after the evidence-backed fix pass.

Environment note: sandbox denies Windows pytest launcher canonicalization and old cache writes; normal-permission console commands run successfully. Final local suites use no:cacheprovider solely for that host cache limitation. CI runs normal package-installed console suite.
