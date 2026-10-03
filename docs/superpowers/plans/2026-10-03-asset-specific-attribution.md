# Asset-specific attribution implementation plan

> Execute inline with superpowers:executing-plans. Base:1de358d. Authoritative project progress stays in the original review workspace `.review` files. This plan records the bounded feature implementation; no competing project plan.

Spec: ../specs/2026-10-03-asset-specific-attribution-design.md

## Shared contracts

`SourceDocument` is a versioned dict produced by official parsers; `capture_source(symbol, root, *, session=None)` downloads only allowlisted official sources and stores raw plus normalized JSON. `load_sources(symbol, root)` checks hash/version. `eligible_snapshot(doc, start, mode)` checks effective day and conservative availability. Roots are caller supplied; report never downloads. All return numbers are decimal fractions except explicitly named yield_pct, premium_pct, and yield_delta_bp.

## Task 1: official source and evidence foundation

Produces `src/asset_sources.py`: source specs, pure `parse_invesco`, `parse_ishares`, `parse_spdr`, `store_source`, `load_sources`, `capture_source`, `eligible_snapshot`. Tests `tests/test_asset_sources.py`.

- [ ] Write synthetic JSON/CSV/XLSX parser and temporal/hash tests; run `.venv/Scripts/python -m pytest tests/test_asset_sources.py -q --basetemp .review/asset-source-red`.
  Expected: missing new module (RED).
- [ ] Implement pure parsers, field/unit validation, fail-closed schema/identity/date checks, conservative available_at, atomic local storage and bounded official fetch.
- [ ] Run source tests with fresh basetemp; expected GREEN; commit source foundation and specification.

## Task 2: asset mechanics and return contracts

Consumes Task1 document format; produces `src/asset_models.py`: asset kinds, `period_return`, `return_summary`, `equity_contributions`, `treasury_profile`, `duration_effect`, `gold_archive_metrics`. Tests `tests/test_asset_models.py`.

- [ ] Write RED tests for incomplete endpoints, adjusted-series absence, units, unsupported assets, future/current weights, coverage without renormalization, +10bp duration, GLD clock labels.
- [ ] Implement pure calculations using explicit input datasets, no network or global cache; QQQ residual only with like-for-like price returns.
- [ ] Run both new test files; expected GREEN; commit mechanical models.

## Task 3: report and usable commands

Consumes Task1/2; produces `src/asset_report.py` and `examples/asset_report.py`; tests `tests/test_asset_report.py`.

- [ ] Write RED integration tests for offline reports, missing input/readiness, historical cutoffs, different index identities and CLI sync/report routing.
- [ ] Implement report using explicit market/source roots, source coverage and source timestamps; optional constituent inputs from local caches; show current structural profile separately from gated historical attribution.
- [ ] CLI: `sync --symbols QQQ IEF TLT GLD --source-root ...`; `report --symbols ... --start ... --end ... --mode ... --market-root ... --source-root ... --output ...`.
- [ ] Extend `.gitignore` only for generated source capture data. Document commands in `docs/asset-specific-attribution.md` and link from README.
- [ ] Run focused and existing complete offline suite, Python3.12 and3.11; expected all pass, existing live tests remain opt-in.

## Task 4: real-provider evidence and reviewable delivery

- [ ] Run sync against all four real issuers; retain full raw files locally only.
- [ ] Build report from genuine previously downloaded Yahoo data; verify shapes, hash, dates, weights, and readiness. Do not claim current weights explain past periods.
- [ ] Commit summary evidence and report, excluding complete restricted issuer archives.
- [ ] Conduct whole-branch review; fix material issues with failing regression tests first. Publish a stacked draft PR based on fix/audit-follow-through, attach it; dispatch existing CI workflow on this branch because PR trigger filters master/main.
- [ ] Report implemented scope and actual tests, plus concrete next causal-study input requirements.

## Review focus

Malformed issuer responses, response size limits, duplicate security identifiers, negative cash vs negative stock weights, financial units, file corruption, copied snapshot provenance, timezone boundary at NY open, point-in-time versus retrospective modes, corporate actions, nonmatching valuation times, index/fund identity confusion, report paths and no implicit requests.

Plan self-review: producer/consumer signatures align; tests run in writable fresh temporary roots; no runtime dependency changes needed (XLSX read with standard-library ZIP/XML). New isolated clone branch preserves PR7. Scope contains a usable foundation and no claim that a policy-shock model has already been identified.
