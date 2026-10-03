# Asset-specific attribution implementation plan

> Execute inline with superpowers:executing-plans. Base:1de358d. Authoritative project progress stays in the original review workspace `.review` files. This plan records the bounded feature implementation; no competing project plan.

Spec: ../specs/2026-10-03-asset-specific-attribution-design.md

## Shared contracts

`SourceDocument` is a versioned dict produced by official parsers; `capture_source(symbol, root, *, session=None)` downloads only allowlisted official sources and stores raw plus normalized JSON. `load_sources(symbol, root)` checks hash/version. `eligible_snapshot(doc, start, mode)` checks effective day and conservative availability. Roots are caller supplied; report never downloads. All return numbers are decimal fractions except explicitly named yield_pct, premium_pct, and yield_delta_bp.

## Task 1: official source and evidence foundation

Produces `src/asset_sources.py`: source specs, pure `parse_invesco`, `parse_ishares`, `parse_spdr`, `store_source`, `load_sources`, `capture_source`, `eligible_snapshot`. Tests `tests/test_asset_sources.py`.

- [x] Write synthetic JSON/CSV/XLSX parser and temporal/hash tests; run `.venv/Scripts/python -m pytest tests/test_asset_sources.py -q --basetemp .review/asset-source-red`.
  Expected: missing new module (RED).
- [x] Implement pure parsers, field/unit validation, fail-closed schema/identity/date checks, conservative available_at, atomic local storage and bounded official fetch.
- [x] Run source tests with fresh basetemp; expected GREEN; commit source foundation and specification.

## Task 2: asset mechanics and return contracts

Consumes Task1 document format; produces `src/asset_models.py`: asset kinds, `period_return`, `return_summary`, `equity_contributions`, `treasury_profile`, `duration_effect`, `gold_archive_metrics`. Tests `tests/test_asset_models.py`.

- [x] Write RED tests for incomplete endpoints, adjusted-series absence, units, unsupported assets, future/current weights, coverage without renormalization, +10bp duration, GLD clock labels.
- [x] Implement pure calculations using explicit input datasets, no network or global cache; QQQ residual only with like-for-like price returns.
- [x] Run both new test files; expected GREEN; commit mechanical models.

## Task 3: report and usable commands

Consumes Task1/2; produces `src/asset_report.py` and `examples/asset_report.py`; tests `tests/test_asset_report.py`.

- [x] Write RED integration tests for offline reports, missing input/readiness, historical cutoffs, different index identities and CLI sync/report routing.
- [x] Implement report using explicit market/source roots, source coverage and source timestamps; optional constituent inputs from local caches; show current structural profile separately from gated historical attribution.
- [x] CLI: `sync --symbols QQQ IEF TLT GLD --source-root ...`; `report --symbols ... --start ... --end ... --mode ... --market-root ... --source-root ... --output ...`.
- [x] Extend `.gitignore` only for generated source capture data. Document commands in `docs/asset-specific-attribution.md` and link from README.
- [x] Run focused and existing complete offline suite, Python3.12 and3.11; expected all pass, existing live tests remain opt-in.

## Task 4: real-provider evidence and reviewable delivery

- [x] Run sync against all four real issuers; retain full raw files locally only.
- [x] Build report from genuine previously downloaded Yahoo data; verify shapes, hash, dates, weights, and readiness. Do not claim current weights explain past periods.
- [x] Commit summary evidence and report, excluding complete restricted issuer archives.
- [x] Conduct whole-branch review; fix material issues with failing regression tests first.
- [x] Publish a stacked draft PR based on fix/audit-follow-through, attach it; dispatch existing CI workflow on this branch because PR trigger filters master/main.
- [x] Report implemented scope and actual tests, plus concrete next causal-study input requirements.

## Review focus

Malformed issuer responses, response size limits, duplicate security identifiers, negative cash vs negative stock weights, financial units, file corruption, copied snapshot provenance, timezone boundary at NY open, point-in-time versus retrospective modes, corporate actions, nonmatching valuation times, index/fund identity confusion, report paths and no implicit requests.

Plan self-review: producer/consumer signatures align; tests run in writable fresh temporary roots; no runtime dependency changes needed (XLSX read with standard-library ZIP/XML). New isolated clone branch preserves PR7. Scope contains a usable foundation and no claim that a policy-shock model has already been identified.

## Implementation ledger

- Task1 complete: e869a02/6403d61, source tests19 GREEN; actual four issuer payloads parsed after cash/AWAITED edge tests RED→GREEN.
- Task2 complete: 3f3be79, model tests22 GREEN; combined41 GREEN.
- Task3 complete: d882ee8, report/CLI tests9 GREEN after explicit market-file selector RED→GREEN; complete suites180 GREEN in both runtimes before review.
- Final independent review:4 Important,0 Critical,0 Minor; all reproduced with12 red regression cases and fixed in one pass. Focused62 GREEN; complete suites193 passed/3 skipped/11 warnings on Python3.11 and3.12.
- Task4 real verification:4 live official captures succeeded; six actual source/date/coverage guards all true; full raw issuer archives excluded from commits. Sourcechecks use SHA256 and independent CSV duration recomputation.
- Final: Ruling: reviewer left live endpoint stability, full-archive accuracy and later research inputs unjudged. Live sources were verified twice this session, CSV durations independently recalculated, historical cutoffs tested; this does not guarantee future website schemas or historical publication. Licensed benchmark, full curve and external shocks remain explicit later phases. Cost if this boundary is ignored: biased historical or causal claims; outputs retain not_identified and backtest_ready=false.

- Publishing: draft PR #8 created and attached, based on PR #7; initial CI exposed missing installed examples namespace. Isolated external-CWD CLI regression RED→GREEN, examples added to packaging; wheel contents verified; full console pytest193 GREEN in both runtimes. Current-head CI is tracked on the PR and in the canonical project progress file.
