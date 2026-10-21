# Changelog

## 0.2.0

- Add reusable `Pipeline` definitions. `Pipeline.run()` produces the same
  sequential `Trace` diagnostics as the original filtering API.
- Add `Pipeline.audit()` to evaluate every configured predicate once per input
  occurrence, including predicates after an earlier failure. Inspect all failed
  filters for an occurrence, independent per-filter statistics, and exclusive
  blockers: records that fail only that filter.
- Add `relax()` and `matching_indices()` to inspect the effect of removing
  filters using recorded audit outcomes, without reevaluating predicates.
- Add `suggest_relaxations()` to find exact ways to obtain a nonempty result by
  removing the fewest filters. Suggestions minimize the number of removed
  filters across the audited input, rather than reporting every
  inclusion-minimal removal set.
- Keep audit summaries and relaxation metadata JSON-compatible without
  automatically serializing original records.

## 0.1.0

- Introduce sequential filter tracing with counts, retention, timing, original
  positions for first rejections, readable diagnostics, and JSON summaries.
- Provide atomic stage failure with contextual exceptions and no required
  runtime dependencies.
