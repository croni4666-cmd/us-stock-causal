# DAG证伪与平衡支持：执行账本

Spec: ../specs/2026-10-07-dag-skepticism-design.md
Base db2997b; reuse feature branch/PR8. User explicitly requests lower-trust falsifiable hypotheses and confirms support-degree interpretation; inline implementation authorized.

1. Failing tests for registered observable hypothesis checks and balanced support; implement src/hypothesis_review.py plus offline examples/hypothesis_report.py. Dependencies existing statsmodels/pandas only.
2. Failing integration tests for low-trust CausalEffect/SCM/CATE and cautious Markdown; update src/causal.py/src/report.py, retain formal graph status/numerics without empirical-certification claims. No legacy refuter counted as proof.
3. Offline actual historical example with explicit exploratory registration and unit-correct inputs; docs/JSON evidence, complete dual-runtime tests, installed wheel verification.
4. One fresh independent review required by executing-plans; fixes via RED→GREEN, update current PR8 and verify current-head CI.

Pre-flight: hypothesis check outputs statistical constraints, not causal identification; integration uses default insufficient support even when graph formal identification succeeds. Any source text or duplicated input cannot raise default belief. Only explicit locally recomputed results enter support summary.

Ruling: retain untestable assumptions as dependencies; no numeric probability without calibrated model/priors. Directional claim evaluation refers to its declared observable association, not arbitrary economic causal direction. Preregistration timing is a recorded declaration, not cryptographic proof of historical registration.

Status: implementation and local verification complete; current-head GitHub CI pending.

Observed RED→GREEN: 25 original new contract cases and updated existing rendering expectations; fresh technical review found three P2 issues. Added five failing cases reproducing cross-run timestamp selection, three nonfinite threshold variants and hidden Markdown protocol. All five failed before fixes and passed afterward. Aggregation now inspects every duplicate declaration without mutating inputs; invalid nonfinite metadata is preserved as diagnostic markers while numeric validation rejects it; Markdown prints the full actual protocol.

Local final evidence: Python3.11 and3.12 console suites each285 passed,3 skipped,11 warnings. Cache plugin disabled only for host cache ACL restrictions, with explicit project-local temporary directories. Built and installed wheel into a fresh target, removed checkout imports and verified module paths; offline CLI evaluated all four real historical entries successfully. Historical example is explicitly late-registered/exploratory, preserves opposite signs and unsupported causal arrow, and all support assessments remain insufficient. Software/AI technical review is not independent domain certification.
